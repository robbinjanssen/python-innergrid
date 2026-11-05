"""Tests for the Innergrid client."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Self
from unittest.mock import patch

import aiomqtt
import pytest

from innergrid import (
    ElectricityMeter,
    Innergrid,
    InnergridAuthError,
    InnergridConnectionError,
    InnergridTimeoutError,
    Kind,
    MilesightSensor,
    Removal,
    SystemStatus,
    Update,
    parse_data,
    parse_message,
    topic_kind,
    valid_topic_prefix,
)

from . import load_fixture

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class FakeClient:
    """An aiomqtt client that yields the given messages."""

    def __init__(
        self,
        messages: list[tuple[str, Any]],
        *,
        enter_error: Exception | None = None,
        error: Exception | None = None,
        wait: bool = False,
    ) -> None:
        """Initialise the client."""
        self._messages = messages
        self._enter_error = enter_error
        self._error = error
        self._wait = wait
        self.subscriptions: list[str] = []
        self.kwargs: dict[str, Any] = {}

    def __call__(self, *args: Any, **kwargs: Any) -> FakeClient:
        """Return the client, as aiomqtt.Client would create one."""
        self.kwargs = {"args": args, **kwargs}
        return self

    async def __aenter__(self) -> Self:
        """Connect."""
        if self._enter_error is not None:
            raise self._enter_error
        return self

    async def __aexit__(self, *args: object) -> None:
        """Disconnect."""

    async def subscribe(self, topic: str) -> None:
        """Subscribe to a topic."""
        self.subscriptions.append(topic)

    @property
    def messages(self) -> AsyncIterator[Any]:
        """Return the messages."""
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        for topic, payload in self._messages:
            yield SimpleNamespace(topic=SimpleNamespace(value=topic), payload=payload)
        if self._error is not None:
            raise self._error
        if self._wait:
            await asyncio.sleep(10)


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("mysite/customersites/34901/live", (Kind.SITE, "34901")),
        ("mysite/categories/34901/live", (Kind.CATEGORIES, "34901")),
        ("mysite/electricitymeters/10005", (Kind.METER, "10005")),
        ("mysite/circuits/10239/live", (Kind.CIRCUIT, "10239")),
        ("mysite/chargepoints/19463", (Kind.CHARGE_POINT, "19463")),
        ("mysite/energymanagers/11376/state", (Kind.ENERGY_MANAGER, "11376")),
        ("mysite/spaces/11468/live", (Kind.SPACE, "11468")),
        ("mysite/system", (Kind.SYSTEM, "system")),
        (
            "mysite/events/chargepoints/30657/sessionchanged",
            (Kind.CHARGE_POINT_EVENT, "30657"),
        ),
        ("milesight/uplink/A81758FFFE054F0D", (Kind.MILESIGHT, "a81758fffe054f0d")),
        ("mysite/unknown", None),
        ("mysite/electricitymeters/10005/extra", None),
        ("other/system", None),
    ],
)
def test_topic_kind(topic: str, expected: tuple[Kind, str] | None) -> None:
    """Test which topics are used."""
    assert topic_kind("mysite", topic) == expected


def test_parse_message() -> None:
    """Test parsing a message."""
    update = parse_message(
        "mysite",
        "mysite/electricitymeters/10005",
        load_fixture("meter_single_phase.json").encode(),
    )
    assert isinstance(update, Update)
    assert update.key == "meter/10005"
    assert isinstance(update.data, ElectricityMeter)
    assert update.raw["id"] == 10005


def test_parse_data() -> None:
    """Test parsing a stored payload again, with the kind as a string."""
    update = parse_data("space", "11468", json.loads(load_fixture("space.json")))
    assert update.kind is Kind.SPACE
    assert update.key == "space/11468"
    assert update.data.temperature == 21.3  # type: ignore[union-attr]


@pytest.mark.parametrize("payload", [b"", "", None])
def test_parse_removal(payload: Any) -> None:
    """Test that an empty message means that the instance is gone."""
    removal = parse_message("mysite", "mysite/chargepoints/19463", payload)
    assert removal == Removal(kind=Kind.CHARGE_POINT, id="19463")
    assert removal.key == "chargepoint/19463"


def test_parse_removal_of_unused_topic() -> None:
    """Test that an empty message on a topic that is not used is ignored."""
    assert parse_message("mysite", "mysite/unknown", b"") is None


@pytest.mark.parametrize("payload", [b"not json", b"[1, 2]"])
def test_parse_invalid_message(payload: Any) -> None:
    """Test that a payload that is not a JSON object is ignored."""
    assert parse_message("mysite", "mysite/system", payload) is None


def test_parse_nan() -> None:
    """Test that a payload with NaN, which json.loads accepts, does not raise."""
    update = parse_message("mysite", "mysite/circuits/1/live", b'{"warnings": NaN}')
    assert update is not None
    assert update.data.warnings is None  # type: ignore[union-attr]


def test_parse_unused_topic() -> None:
    """Test that a topic that is not used is ignored."""
    assert parse_message("mysite", "mysite/unknown", b"{}") is None


@pytest.mark.parametrize("prefix", ["", " / ", "mysite/#", "a+b"])
def test_invalid_topic_prefix(prefix: str) -> None:
    """Test that a prefix that is empty or has wildcards is rejected."""
    assert not valid_topic_prefix(prefix)
    with pytest.raises(ValueError, match="Invalid topic prefix"):
        Innergrid("broker", topic_prefix=prefix)


def test_client_settings() -> None:
    """Test that the prefix is cleaned up and the login is passed on."""
    fake = FakeClient([])
    client = Innergrid(
        "broker", 1884, username="user", password="pw", topic_prefix=" mysite/ "
    )
    assert client.topic_prefix == "mysite"
    with patch("aiomqtt.Client", fake):
        client._client()  # pylint: disable=protected-access
    assert fake.kwargs["args"] == ("broker", 1884)
    assert fake.kwargs["username"] == "user"
    assert fake.kwargs["password"] == "pw"


async def test_listen() -> None:
    """Test that messages are parsed until the connection closes."""
    fake = FakeClient(
        [
            ("mysite/system", load_fixture("system.json")),
            ("mysite/unknown", "{}"),
            ("milesight/uplink/a81758fffe054f0d", load_fixture("milesight.json")),
            ("mysite/spaces/1/live", b""),
        ]
    )
    updates: list[Update | Removal] = []
    connected: list[bool] = []
    with (
        patch("aiomqtt.Client", fake),
        pytest.raises(InnergridConnectionError, match="was closed"),
    ):
        await Innergrid("broker", topic_prefix="mysite").listen(
            updates.append, lambda: connected.append(True)
        )
    assert fake.subscriptions == ["mysite/#", "milesight/uplink/#"]
    assert connected == [True]
    assert [type(u.data) for u in updates[:2] if isinstance(u, Update)] == [
        SystemStatus,
        MilesightSensor,
    ]
    assert updates[2] == Removal(kind=Kind.SPACE, id="1")


async def test_listen_without_on_connect() -> None:
    """Test listening without a connect callback."""
    with (
        patch("aiomqtt.Client", FakeClient([])),
        pytest.raises(InnergridConnectionError),
    ):
        await Innergrid("broker", topic_prefix="mysite").listen(lambda _update: None)


async def test_listen_connection_lost() -> None:
    """Test that a lost connection raises a connection error."""
    fake = FakeClient([], error=aiomqtt.MqttError("Disconnected"))
    with (
        patch("aiomqtt.Client", fake),
        pytest.raises(InnergridConnectionError, match="Disconnected"),
    ):
        await Innergrid("broker", topic_prefix="mysite").listen(lambda _update: None)


@pytest.mark.parametrize("code", [4, 5, 134, 135])
async def test_listen_auth_failed(code: int) -> None:
    """Test that a rejected login raises an authentication error."""
    fake = FakeClient([], enter_error=aiomqtt.MqttCodeError(code))
    with (
        patch("aiomqtt.Client", fake),
        pytest.raises(InnergridAuthError),
    ):
        await Innergrid("broker", topic_prefix="mysite").listen(lambda _update: None)


async def test_listen_other_code() -> None:
    """Test that another error code raises a connection error."""
    fake = FakeClient([], enter_error=aiomqtt.MqttCodeError(3))
    with (
        patch("aiomqtt.Client", fake),
        pytest.raises(InnergridConnectionError) as err,
    ):
        await Innergrid("broker", topic_prefix="mysite").listen(lambda _update: None)
    assert not isinstance(err.value, InnergridAuthError)


async def test_wait_for_data() -> None:
    """Test waiting for the first message with data, skipping removals."""
    fake = FakeClient(
        [
            ("mysite/unknown", "{}"),
            ("mysite/chargepoints/1", b""),
            ("mysite/system", load_fixture("system.json")),
        ]
    )
    with patch("aiomqtt.Client", fake):
        update = await Innergrid("broker", topic_prefix="mysite").wait_for_data()
    assert fake.subscriptions == ["mysite/#"]
    assert update.kind is Kind.SYSTEM


async def test_wait_for_data_timeout() -> None:
    """Test that no data within the timeout raises a timeout error."""
    with (
        patch("aiomqtt.Client", FakeClient([], wait=True)),
        pytest.raises(InnergridTimeoutError),
    ):
        await Innergrid("broker", topic_prefix="mysite").wait_for_data(
            wait_seconds=0.01
        )


async def test_wait_for_data_closed() -> None:
    """Test that a closed connection raises a connection error."""
    with (
        patch("aiomqtt.Client", FakeClient([])),
        pytest.raises(InnergridConnectionError),
    ):
        await Innergrid("broker", topic_prefix="mysite").wait_for_data()


async def test_wait_for_data_connection_failed() -> None:
    """Test that a failed connection raises a connection error."""
    fake = FakeClient([], enter_error=aiomqtt.MqttError("Connection refused"))
    with (
        patch("aiomqtt.Client", fake),
        pytest.raises(InnergridConnectionError, match="Connection refused"),
    ):
        await Innergrid("broker", topic_prefix="mysite").wait_for_data()
