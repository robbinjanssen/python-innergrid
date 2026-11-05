# Python: Innergrid

Asynchronous Python client that reads the energy and building data that the
Innergrid energy management platform publishes over MQTT for a customer site:
the grid connection, energy categories, electricity meters and circuits,
charge points, the energy manager, spaces, the server and Milesight LoRaWAN
sensors.

## Installation

```sh
pip install innergrid
```

## Usage

```python
import asyncio

from innergrid import Innergrid, Update


def on_update(update: Update) -> None:
    print(update.key, update.data)


async def main() -> None:
    client = Innergrid("192.0.2.10", 1883, topic_prefix="mysite")
    # Check the settings: wait for the first message below the prefix.
    await client.wait_for_data()
    # Runs until the connection is lost; connect again to continue.
    await client.listen(on_update)


asyncio.run(main())
```

The callback of `listen()` gets an `Update` with the data of a topic, or a
`Removal` when the instance of a topic is gone (the platform then publishes an
empty message on its topic).

`listen()` and `wait_for_data()` raise `InnergridAuthError` when the
broker rejects the login and `InnergridConnectionError` when the connection
fails or is lost. `wait_for_data()` raises `InnergridTimeoutError` when no
data arrives in time.

## REST API

The edge server also has a REST API, with what MQTT lacks: the names of the
spaces, and changing the session of a charge point. `InnergridApi` logs in
with an e-mail address and password of a user of the edge server, and logs in
again when the API rejects the token.

```python
from innergrid import ChargeStrategy, InnergridApi

async with InnergridApi("http://192.0.2.10:31679/hook/api", email, password) as api:
    spaces = await api.spaces()
    await api.set_charge_point_session(
        "19463", charge_strategy=ChargeStrategy.DIRECT_CHARGING, target_energy=30
    )
```

`set_charge_point_session` changes only the values that are given: the
charging strategy, the target energy (kWh), the departure time, the user and
whether the session is claimed.

## Topics

| Topic | Model |
| --- | --- |
| `<prefix>/customersites/<id>/live` | `Site` |
| `<prefix>/categories/<id>/live` | `Categories` |
| `<prefix>/electricitymeters/<id>` | `ElectricityMeter` |
| `<prefix>/circuits/<id>/live` | `Circuit` |
| `<prefix>/chargepoints/<id>` | `ChargePoint` |
| `<prefix>/energymanagers/<id>/state` | `EnergyManager` |
| `<prefix>/spaces/<id>/live` | `Space` |
| `<prefix>/system` | `SystemStatus` |
| `<prefix>/events/chargepoints/<id>/<event>` | `ChargePointEvent` |
| `milesight/uplink/<devEUI>` | `MilesightSensor` |

`<prefix>` is the slug of the customer site. Every update and removal has a
key (`<kind>/<id>`, for example `meter/10005`); the latest update of a key
replaces the earlier ones. The platform's topics are retained, so the current
state of every topic arrives right after subscribing; after that, a topic is
published when it changes and every refresh interval (60 seconds by default).
The Milesight sensors are not retained and publish every few minutes.

`parse_data(kind, id, raw)` parses a payload that was stored earlier, for
example `update.raw`, into an `Update` again.

Climate values that are not plausible, such as -1001.1 °C or 0% humidity,
are `None`; some sensors report those instead of an error.

## Development

The project uses [uv](https://docs.astral.sh/uv/) and
[prek](https://github.com/j178/prek).

```sh
uv sync
uv run prek install
uv run pytest
```

## License

MIT, see [LICENSE](LICENSE).
