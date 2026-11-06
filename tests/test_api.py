"""Tests for the REST API client."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone

import aiohttp
import pytest
from aresponses import Response, ResponsesMockServer

from innergrid import (
    ChargeStrategy,
    InnergridApi,
    InnergridAuthError,
    InnergridConnectionError,
    InnergridError,
    InnergridTimeoutError,
    SpaceInfo,
)

HOST = "edge.local:31679"
URL = f"http://{HOST}/hook/api"


def json_response(data: object, status: int = 200) -> Response:
    """Return a JSON response."""
    return Response(
        text=json.dumps(data),
        status=status,
        headers={"Content-Type": "application/json"},
    )


def login(aresponses: ResponsesMockServer, token: str = "token-1") -> None:
    """Respond to a login with a token."""
    aresponses.add(HOST, "/hook/api/login", "POST", json_response({"token": token}))


async def test_spaces(aresponses: ResponsesMockServer) -> None:
    """Test logging in and listing the spaces."""
    login(aresponses)
    aresponses.add(
        HOST,
        "/hook/api/spaces",
        "GET",
        json_response(
            [
                {
                    "id": 31196,
                    "name": "Mysite HQ",
                    "type": "building",
                    "parentId": None,
                },
                {"id": 26291, "name": " Kantoor 1 ", "type": "room", "parentId": 31196},
                {"id": 1},
                "not a space",
            ]
        ),
    )
    async with aiohttp.ClientSession() as session:
        api = InnergridApi(URL, "user@example.com", "secret", session=session)
        spaces = await api.spaces()
    assert spaces == [
        SpaceInfo(id="31196", name="Mysite HQ", type="building", parent_id=None),
        SpaceInfo(id="26291", name="Kantoor 1", type="room", parent_id="31196"),
        SpaceInfo(id="1", name="1", type=None, parent_id=None),
    ]


async def test_login_sends_credentials(aresponses: ResponsesMockServer) -> None:
    """Test that the login sends the e-mail address and password."""
    seen = {}

    async def handler(request: aiohttp.web.Request) -> Response:
        seen.update(await request.json())
        return json_response({"token": "t"})

    aresponses.add(HOST, "/hook/api/login", "POST", handler)
    async with InnergridApi(URL + "/", "user@example.com", "secret") as api:
        await api.login()
    assert seen == {"email": "user@example.com", "password": "secret"}


@pytest.mark.parametrize("status", [401, 403])
async def test_login_rejected(aresponses: ResponsesMockServer, status: int) -> None:
    """Test that a rejected login raises an authentication error."""
    aresponses.add(
        HOST, "/hook/api/login", "POST", json_response({"error": True}, status=status)
    )
    async with InnergridApi(URL, "user@example.com", "wrong") as api:
        with pytest.raises(InnergridAuthError):
            await api.login()


async def test_login_server_error(aresponses: ResponsesMockServer) -> None:
    """Test that another HTTP error on login is a connection error."""
    aresponses.add(HOST, "/hook/api/login", "POST", json_response({}, status=500))
    async with InnergridApi(URL, "user@example.com", "secret") as api:
        with pytest.raises(InnergridConnectionError):
            await api.login()


async def test_login_without_token(aresponses: ResponsesMockServer) -> None:
    """Test that a login response without a token is an error."""
    aresponses.add(HOST, "/hook/api/login", "POST", json_response({}))
    async with InnergridApi(URL, "user@example.com", "secret") as api:
        with pytest.raises(InnergridError):
            await api.login()


async def test_login_again_on_401(aresponses: ResponsesMockServer) -> None:
    """Test that a rejected token makes the client log in again once."""
    login(aresponses, "old")
    aresponses.add(HOST, "/hook/api/spaces", "GET", json_response({}, status=401))
    login(aresponses, "new")
    tokens = []

    async def handler(request: aiohttp.web.Request) -> Response:
        tokens.append(request.headers["Authorization"])
        return json_response([])

    aresponses.add(HOST, "/hook/api/spaces", "GET", handler)
    async with InnergridApi(URL, "user@example.com", "secret") as api:
        assert await api.spaces() == []
    assert tokens == ["Bearer new"]


async def test_rejected_twice(aresponses: ResponsesMockServer) -> None:
    """Test that a token that is rejected again raises an error."""
    for _ in range(2):
        login(aresponses)
        aresponses.add(HOST, "/hook/api/spaces", "GET", json_response({}, status=401))
    async with InnergridApi(URL, "user@example.com", "secret") as api:
        with pytest.raises(InnergridConnectionError, match="401"):
            await api.spaces()


async def test_http_error(aresponses: ResponsesMockServer) -> None:
    """Test that another HTTP error is a connection error."""
    login(aresponses)
    aresponses.add(HOST, "/hook/api/spaces", "GET", json_response({}, status=500))
    async with InnergridApi(URL, "user@example.com", "secret") as api:
        with pytest.raises(InnergridConnectionError, match="500"):
            await api.spaces()


async def test_unreachable() -> None:
    """Test that an unreachable API is a connection error."""
    async with InnergridApi("http://127.0.0.1:9/hook/api", "u", "p") as api:
        with pytest.raises(InnergridConnectionError):
            await api.login()


async def test_timeout(aresponses: ResponsesMockServer) -> None:
    """Test that a slow API is a timeout error."""

    async def slow(_request: aiohttp.web.Request) -> Response:
        await asyncio.sleep(1)
        return json_response({"token": "t"})

    aresponses.add(HOST, "/hook/api/login", "POST", slow)
    async with InnergridApi(URL, "u", "p", request_timeout=0.05) as api:
        with pytest.raises(InnergridTimeoutError):
            await api.login()


async def test_set_charge_point_session(aresponses: ResponsesMockServer) -> None:
    """Test changing the session of a charge point."""
    login(aresponses)
    seen = {}

    async def handler(request: aiohttp.web.Request) -> Response:
        seen.update(await request.json())
        return json_response(
            {
                "status": "CHARGING",
                "chargingState": "CHARGING",
                "chargeStrategy": "SOLAR_CHARGING",
                "targetEnergyRequest": 25,
                "departureAt": "2026-11-05T16:30:00Z",
                "username": "Alice",
                "isClaimed": True,
            }
        )

    aresponses.add(HOST, "/hook/api/chargepoints/19463", "POST", handler)
    departure = datetime(
        2026, 11, 5, 17, 30, 15, 123, tzinfo=timezone(timedelta(hours=1))
    )
    async with InnergridApi(URL, "u", "p") as api:
        charge_point = await api.set_charge_point_session(
            "19463",
            charge_strategy=ChargeStrategy.SOLAR_CHARGING,
            target_energy=25,
            departure_at=departure,
            username="Alice",
            claimed=True,
        )
    assert seen == {
        "chargeStrategy": "SOLAR_CHARGING",
        "energyChargeTarget": 25,
        "departureTime": "2026-11-05T16:30:15Z",
        "username": "Alice",
        "isClaimed": True,
    }
    assert charge_point.id == "19463"
    assert charge_point.charge_strategy == "SOLAR_CHARGING"
    assert charge_point.target_energy == 25
    assert charge_point.departure_at == datetime(2026, 11, 5, 16, 30, tzinfo=UTC)
    assert charge_point.current_user == "Alice"
    assert charge_point.claimed is True


async def test_set_charge_point_session_one_value(
    aresponses: ResponsesMockServer,
) -> None:
    """Test that only the given values are sent."""
    login(aresponses)
    seen = {}

    async def handler(request: aiohttp.web.Request) -> Response:
        seen.update(await request.json())
        return json_response("unexpected")

    aresponses.add(HOST, "/hook/api/chargepoints/1", "POST", handler)
    async with InnergridApi(URL, "u", "p") as api:
        charge_point = await api.set_charge_point_session("1", claimed=False)
    assert seen == {"isClaimed": False}
    assert charge_point.status is None


async def test_set_charge_point_session_invalid() -> None:
    """Test that nothing to change, or a naive time, is refused."""
    async with InnergridApi(URL, "u", "p") as api:
        with pytest.raises(ValueError, match="Nothing"):
            await api.set_charge_point_session("1")
        with pytest.raises(ValueError, match="time zone"):
            await api.set_charge_point_session("1", departure_at=datetime(2026, 1, 1))  # noqa: DTZ001


async def test_close_own_session_only() -> None:
    """Test that a session passed in is not closed."""
    async with aiohttp.ClientSession() as session:
        api = InnergridApi(URL, "u", "p", session=session)
        await api.close()
        assert not session.closed
