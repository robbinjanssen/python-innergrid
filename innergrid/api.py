"""Asynchronous client for the REST API of the Loqio edge server."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self

from aiohttp import ClientError, ClientResponseError, ClientSession, hdrs

from .exceptions import (
    InnergridAuthError,
    InnergridConnectionError,
    InnergridError,
    InnergridTimeoutError,
)
from .models import ChargePoint

if TYPE_CHECKING:
    from types import TracebackType


class ChargeStrategy(StrEnum):
    """The charging strategy of a charge point session."""

    SMART_CHARGING = "SMART_CHARGING"
    """Charge towards the target energy by the departure time."""
    DIRECT_CHARGING = "DIRECT_CHARGING"
    """Charge at maximum power."""
    SOLAR_CHARGING = "SOLAR_CHARGING"
    """Charge with surplus (solar) power."""


@dataclass(frozen=True)
class SpaceInfo:
    """A space of the building, such as a room or a floor."""

    id: str
    name: str
    type: str | None
    parent_id: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Parse a space of GET /spaces."""
        parent = data.get("parentId")
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]).strip(),
            type=data.get("type"),
            parent_id=None if parent is None else str(parent),
        )


class InnergridApi:
    """The REST API of a Loqio edge server.

    Logs in with an e-mail address and password, and logs in again when the
    API rejects the token. Most data is also published over MQTT; the REST API
    adds what MQTT lacks, such as the names of the spaces, and lets the
    charge point sessions be changed.
    """

    def __init__(
        self,
        url: str,
        email: str,
        password: str,
        *,
        session: ClientSession | None = None,
        request_timeout: float = 10.0,
    ) -> None:
        """Initialise the client.

        Args:
        ----
            url: The base URL of the API, for example
                http://10.50.20.150:31679/hook/api.
            email: The e-mail address of a user of the edge server.
            password: The password of the user.
            session: The aiohttp session to use, or a new one is created.
            request_timeout: Seconds to wait for a response.

        """
        self.url = url.rstrip("/")
        self.email = email
        self.password = password
        self.request_timeout = request_timeout
        self._session = session
        self._close_session = False
        self._token: str | None = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> Any:
        """Send a request and return the JSON of the response.

        Raises
        ------
            ClientResponseError: The API returned an HTTP error.
            InnergridTimeoutError: The API did not respond in time.
            InnergridConnectionError: The API could not be reached.

        """
        if self._session is None:
            self._session = ClientSession()
            self._close_session = True
        headers = {"Accept": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with asyncio.timeout(self.request_timeout):
                response = await self._session.request(
                    method, f"{self.url}{path}", json=body, headers=headers
                )
                response.raise_for_status()
                return await response.json(content_type=None)
        except ClientResponseError:
            raise
        except TimeoutError as err:
            msg = f"Timeout while connecting to {self.url}"
            raise InnergridTimeoutError(msg) from err
        except (ClientError, ValueError) as err:
            msg = f"Error while connecting to {self.url}: {err}"
            raise InnergridConnectionError(msg) from err

    async def login(self) -> None:
        """Log in and keep the token.

        Raises
        ------
            InnergridAuthError: The e-mail address or password is wrong.
            InnergridConnectionError: The API could not be reached.

        """
        try:
            result = await self._request(
                hdrs.METH_POST,
                "/login",
                body={"email": self.email, "password": self.password},
            )
        except ClientResponseError as err:
            if err.status in (401, 403):
                msg = "The edge server rejected the e-mail address or password"
                raise InnergridAuthError(msg) from err
            msg = f"Login failed: HTTP {err.status}"
            raise InnergridConnectionError(msg) from err
        if not isinstance(result, dict) or not result.get("token"):
            msg = "The edge server returned no token"
            raise InnergridError(msg)
        self._token = result["token"]

    async def request(
        self, method: str, path: str, *, body: dict[str, Any] | None = None
    ) -> Any:
        """Send an authenticated request, logging in (again) when needed.

        Raises
        ------
            InnergridAuthError: The login was rejected.
            InnergridConnectionError: The API could not be reached or
                returned an error.

        """
        for attempt in (1, 2):
            if self._token is None:
                await self.login()
            try:
                return await self._request(method, path, body=body, token=self._token)
            except ClientResponseError as err:
                if err.status == 401 and attempt == 1:
                    # The token expired or was revoked; log in again once.
                    self._token = None
                    continue
                msg = f"{method} {path} failed: HTTP {err.status} {err.message}"
                raise InnergridConnectionError(msg) from err
        msg = "The edge server rejected the token after logging in again"
        raise InnergridAuthError(msg)

    async def spaces(self) -> list[SpaceInfo]:
        """Return the spaces of the building, parents before their children."""
        result = await self.request(hdrs.METH_GET, "/spaces")
        items = result if isinstance(result, list) else []
        return [SpaceInfo.from_dict(item) for item in items if isinstance(item, dict)]

    async def set_charge_point_session(  # noqa: PLR0913 # pylint: disable=too-many-arguments
        self,
        charge_point_id: str,
        *,
        charge_strategy: ChargeStrategy | None = None,
        target_energy: int | None = None,
        departure_at: datetime | None = None,
        username: str | None = None,
        claimed: bool | None = None,
    ) -> ChargePoint:
        """Change the session of a charge point; only the given values change.

        Args:
        ----
            charge_point_id: The ID of the charge point.
            charge_strategy: The charging strategy.
            target_energy: The energy to charge in the session, in kWh.
            departure_at: The planned departure time.
            username: The user of the session.
            claimed: Whether a user claimed the session.

        Returns:
        -------
            The charge point with the updated session; its other values are
            not known (None).

        """
        body: dict[str, Any] = {}
        if charge_strategy is not None:
            body["chargeStrategy"] = ChargeStrategy(charge_strategy).value
        if target_energy is not None:
            body["energyChargeTarget"] = int(target_energy)
        if departure_at is not None:
            if departure_at.tzinfo is None:
                msg = "The departure time needs a time zone"
                raise ValueError(msg)
            utc = departure_at.astimezone(UTC).replace(microsecond=0)
            body["departureTime"] = utc.isoformat().replace("+00:00", "Z")
        if username is not None:
            body["username"] = username
        if claimed is not None:
            body["isClaimed"] = claimed
        if not body:
            msg = "Nothing to change"
            raise ValueError(msg)
        session = await self.request(
            hdrs.METH_POST, f"/chargepoints/{charge_point_id}", body=body
        )
        return ChargePoint.from_dict(
            {"session": session if isinstance(session, dict) else {}},
            str(charge_point_id),
        )

    async def close(self) -> None:
        """Close the session, when the client created it."""
        if self._session is not None and self._close_session:
            await self._session.close()

    async def __aenter__(self) -> Self:
        """Return the client for use as a context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the session."""
        await self.close()
