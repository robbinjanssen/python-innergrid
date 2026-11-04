"""Asynchronous client for the data that Innergrid publishes over MQTT."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import aiomqtt

from .const import (
    AUTH_FAILED_CODES,
    DEFAULT_PORT,
    MILESIGHT_TOPIC,
    Kind,
)
from .exceptions import (
    InnergridAuthError,
    InnergridConnectionError,
    InnergridTimeoutError,
)
from .models import (
    Categories,
    ChargePoint,
    ChargePointEvent,
    Circuit,
    ElectricityMeter,
    EnergyManager,
    MilesightSensor,
    Site,
    Space,
    SystemStatus,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from .models import Model

_LOGGER = logging.getLogger(__name__)

# Topics below the prefix and the kind of data they carry. The first group
# is the ID of the device or site.
TOPIC_KINDS: list[tuple[re.Pattern[str], Kind]] = [
    (re.compile(r"customersites/(\d+)/live"), Kind.SITE),
    (re.compile(r"categories/(\d+)/live"), Kind.CATEGORIES),
    (re.compile(r"electricitymeters/(\d+)"), Kind.METER),
    (re.compile(r"circuits/(\d+)/live"), Kind.CIRCUIT),
    (re.compile(r"chargepoints/(\d+)"), Kind.CHARGE_POINT),
    (re.compile(r"energymanagers/(\d+)/state"), Kind.ENERGY_MANAGER),
    (re.compile(r"events/chargepoints/(\d+)/\w+"), Kind.CHARGE_POINT_EVENT),
    (re.compile(r"spaces/(\d+)/live"), Kind.SPACE),
    (re.compile(r"(system)"), Kind.SYSTEM),
]
MILESIGHT_PATTERN = re.compile(re.escape(MILESIGHT_TOPIC) + r"/([0-9a-fA-F]+)")

PARSERS: dict[Kind, Callable[[dict[str, Any], str], Model]] = {
    Kind.SITE: Site.from_dict,
    Kind.CATEGORIES: Categories.from_dict,
    Kind.METER: ElectricityMeter.from_dict,
    Kind.CIRCUIT: Circuit.from_dict,
    Kind.CHARGE_POINT: ChargePoint.from_dict,
    Kind.ENERGY_MANAGER: EnergyManager.from_dict,
    Kind.CHARGE_POINT_EVENT: ChargePointEvent.from_dict,
    Kind.SPACE: Space.from_dict,
    Kind.SYSTEM: SystemStatus.from_dict,
    Kind.MILESIGHT: MilesightSensor.from_dict,
}


@dataclass(frozen=True)
class Update:
    """The data of a message.

    The key ("<kind>/<id>", for example "meter/10005") identifies the topic;
    the latest update of a key replaces the earlier ones.
    """

    kind: Kind
    id: str
    data: Model
    raw: dict[str, Any]

    @property
    def key(self) -> str:
        """Return the key of the topic."""
        return f"{self.kind}/{self.id}"


def valid_topic_prefix(prefix: str) -> bool:
    """Return whether a topic prefix is valid: not empty, without wildcards."""
    prefix = prefix.strip().strip("/")
    return bool(prefix) and "#" not in prefix and "+" not in prefix


def topic_kind(prefix: str, topic: str) -> tuple[Kind, str] | None:
    """Return the kind and ID of a topic, or None for topics that are not used."""
    if match := MILESIGHT_PATTERN.fullmatch(topic):
        return Kind.MILESIGHT, match.group(1).lower()
    if not topic.startswith(f"{prefix}/"):
        return None
    subtopic = topic.removeprefix(f"{prefix}/")
    for pattern, kind in TOPIC_KINDS:
        if match := pattern.fullmatch(subtopic):
            return kind, match.group(1)
    return None


def parse_message(prefix: str, topic: str, payload: Any) -> Update | None:
    """Parse a message, or return None if it is not used or not valid.

    Args:
    ----
        prefix: The topic prefix, for example mysite.
        topic: The topic the message was published on.
        payload: The payload of the message, a JSON object.

    Returns:
    -------
        The parsed data, or None.

    """
    if (kind_id := topic_kind(prefix, topic)) is None:
        return None
    kind, idx = kind_id
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        _LOGGER.debug("Ignoring message on %s that is not JSON", topic)
        return None
    if not isinstance(data, dict):
        _LOGGER.debug("Ignoring message on %s that is not a JSON object", topic)
        return None
    return parse_data(kind, idx, data)


def parse_data(kind: Kind | str, idx: str, data: dict[str, Any]) -> Update:
    """Parse the payload of a topic, for example one that was stored earlier.

    Args:
    ----
        kind: The kind of data, as in Update.kind.
        idx: The ID from the topic, as in Update.id.
        data: The payload, as in Update.raw.

    Returns:
    -------
        The parsed data.

    """
    kind = Kind(kind)
    return Update(kind=kind, id=idx, data=PARSERS[kind](data, idx), raw=data)


class Innergrid:
    """Receive the energy and building data that Innergrid publishes over MQTT."""

    def __init__(  # noqa: PLR0913 # pylint: disable=too-many-arguments
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        username: str | None = None,
        password: str | None = None,
        topic_prefix: str,
        timeout: float = 10.0,
    ) -> None:
        """Initialise the client.

        Args:
        ----
            host: The MQTT broker.
            port: The port of the MQTT broker.
            username: The username, if the broker requires a login.
            password: The password, if the broker requires a login.
            topic_prefix: The first part of the topics: the customer site, for
                example mysite.
            timeout: Seconds to wait for the broker to respond.

        Raises:
        ------
            ValueError: The topic prefix is empty or has MQTT wildcards.

        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix.strip().strip("/")
        if not valid_topic_prefix(self.topic_prefix):
            msg = f"Invalid topic prefix: {topic_prefix!r}"
            raise ValueError(msg)
        self.timeout = timeout

    def _client(self) -> aiomqtt.Client:
        """Create an MQTT client."""
        return aiomqtt.Client(
            self.host,
            self.port,
            username=self.username or None,
            password=self.password or None,
            timeout=self.timeout,
        )

    def _connection_error(self, err: aiomqtt.MqttError) -> InnergridConnectionError:
        """Return the exception for an MQTT error."""
        if isinstance(err, aiomqtt.MqttCodeError):
            code = getattr(err.rc, "value", err.rc)
            if code in AUTH_FAILED_CODES:
                return InnergridAuthError(
                    f"{self.host} rejected the username or password"
                )
        return InnergridConnectionError(f"Connection to {self.host} failed: {err}")

    async def listen(
        self,
        callback: Callable[[Update], None],
        on_connect: Callable[[], None] | None = None,
    ) -> None:
        """Connect and call the callback with the data of every message.

        Runs until the connection fails or is lost, or the task is cancelled.

        Args:
        ----
            callback: Called with the data of every message.
            on_connect: Called after connecting and subscribing.

        Raises:
        ------
            InnergridAuthError: The broker rejected the login.
            InnergridConnectionError: The connection failed or was lost.

        """
        try:
            async with self._client() as client:
                await client.subscribe(f"{self.topic_prefix}/#")
                await client.subscribe(f"{MILESIGHT_TOPIC}/#")
                if on_connect is not None:
                    on_connect()
                async for message in client.messages:
                    update = parse_message(
                        self.topic_prefix, message.topic.value, message.payload
                    )
                    if update is not None:
                        callback(update)
        except aiomqtt.MqttError as err:
            raise self._connection_error(err) from err
        # The broker closed the connection without an error.
        msg = f"Connection to {self.host} was closed"
        raise InnergridConnectionError(msg)

    async def wait_for_data(self, wait_seconds: float = 30.0) -> Update:
        """Connect and wait for the first message below the topic prefix.

        Use this to check the settings.

        Args:
        ----
            wait_seconds: Seconds to wait for a message.

        Returns:
        -------
            The data of the first message.

        Raises:
        ------
            InnergridAuthError: The broker rejected the login.
            InnergridConnectionError: The connection failed.
            InnergridTimeoutError: No message arrived in time.

        """
        try:
            async with self._client() as client:
                await client.subscribe(f"{self.topic_prefix}/#")
                async with asyncio.timeout(wait_seconds):
                    async for message in client.messages:
                        update = parse_message(
                            self.topic_prefix, message.topic.value, message.payload
                        )
                        if update is not None:
                            return update
        except aiomqtt.MqttError as err:
            raise self._connection_error(err) from err
        except TimeoutError as err:
            msg = f"No data below {self.topic_prefix}/ within {wait_seconds} seconds"
            raise InnergridTimeoutError(msg) from err
        msg = f"Connection to {self.host} was closed"
        raise InnergridConnectionError(msg)
