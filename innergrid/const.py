"""Constants for the Innergrid client."""

from __future__ import annotations

from enum import StrEnum

DEFAULT_PORT = 1883

# The Milesight LoRaWAN sensors publish under their own fixed prefix.
MILESIGHT_TOPIC = "milesight/uplink"


class Kind(StrEnum):
    """The kinds of data, derived from the topic."""

    SITE = "site"
    CATEGORIES = "categories"
    METER = "meter"
    CIRCUIT = "circuit"
    CHARGE_POINT = "chargepoint"
    ENERGY_MANAGER = "energymanager"
    CHARGE_POINT_EVENT = "chargepointevent"
    SPACE = "space"
    SYSTEM = "system"
    MILESIGHT = "milesight"


# Charge point statuses (OCPP) in which a vehicle is connected.
# THROTTLED_BY_EV: the vehicle charges, but limits the power itself.
CONNECTED_STATUSES = frozenset(
    {
        "PREPARING",
        "CHARGING",
        "THROTTLED_BY_EV",
        "SUSPENDED_BY_EV",
        "SUSPENDED_BY_EVSE",
        "FINISHING",
    }
)

# Ranges outside which a climate value is not plausible. Some sensors report
# impossible values, such as -1001.1 °C or 0% humidity, instead of an error.
TEMPERATURE_RANGE = (-40.0, 80.0)
HUMIDITY_RANGE = (0.1, 100.0)
CO2_RANGE = (1.0, 10000.0)
ILLUMINANCE_RANGE = (0.0, 200000.0)

# CONNACK return codes (MQTT 3.1.1) and reason codes (MQTT 5) for a login
# that the broker rejected.
AUTH_FAILED_CODES = frozenset({4, 5, 134, 135})
