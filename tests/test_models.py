"""Tests for the models of the Innergrid client."""

from datetime import UTC, datetime, timedelta

from innergrid import (
    Categories,
    ChargePoint,
    ChargePointEvent,
    Circuit,
    ElectricityMeter,
    EnergyManager,
    MilesightSensor,
    Quantity,
    Site,
    Space,
    SystemStatus,
)
from innergrid.models import plausible

from . import load_json


def test_site() -> None:
    """Test the overview of a site."""
    site = Site.from_dict(load_json("site.json"), "34901")
    assert site.id == "34901"
    assert site.grid is not None
    assert site.grid.name == "Hoofdaansluiting"
    assert site.grid.active_power == 10802
    assert site.grid.energy_imported_24h == 305.93
    assert site.grid.continuous_import_limit == 50000
    assert site.production is not None
    assert site.production.active_power == -3200
    assert site.production.energy_imported_24h is None
    assert site.consumption is not None
    assert site.consumption.energy_imported_24h == 394.95
    assert site.battery_storage is None
    assert site.expense_24h == 92.35
    assert site.energy_price_import == 0.3
    assert site.energy_price_export == 0.25
    assert site.main_circuit_load_factor == 0.08


def test_site_empty() -> None:
    """Test a site without data; the ID comes from the topic."""
    site = Site.from_dict({}, "1")
    assert site.id == "1"
    assert site.grid is None
    assert site.expense_24h is None


def test_categories() -> None:
    """Test the energy categories of a site."""
    categories = Categories.from_dict(load_json("categories.json"), "34901")
    assert categories.site_id == "34901"
    assert list(categories.categories) == [
        "baseload",
        "chargePoint",
        "climate",
        "kitchen",
        "lighting",
        "solarInverter",
        "workspaces",
    ]
    kitchen = categories.categories["kitchen"]
    assert kitchen.name == "Keuken"
    assert kitchen.active_power == 311
    assert kitchen.energy_imported_24h == 7.79
    assert kitchen.revenue_24h == 0.3


def test_categories_invalid() -> None:
    """Test categories that are missing or not objects."""
    assert not Categories.from_dict({}, "1").categories
    categories = Categories.from_dict({"categories": {"a": 1, "b": {}}}, "1")
    assert list(categories.categories) == ["b"]
    assert categories.categories["b"].name == "b"


def test_meter_single_phase() -> None:
    """Test a single-phase meter."""
    meter = ElectricityMeter.from_dict(load_json("meter_single_phase.json"), "x")
    assert meter.id == "10005"
    assert meter.name == "Groep 14"
    assert meter.module_name == "Eastron SDM630MCTML 1P"
    assert meter.manufacturer == "Eastron"
    assert meter.circuit_id == "32128"
    assert meter.is_three_phase is False
    assert meter.measurements["activePower"] == -22
    assert meter.measurements["voltage"] == 226.8
    assert meter.quantities["activePower"] == Quantity("Active power", "power.watt")
    assert "activePowerL1" not in meter.quantities


def test_meter_three_phase() -> None:
    """Test a three-phase meter, which measures each phase."""
    meter = ElectricityMeter.from_dict(load_json("meter_three_phase.json"), "x")
    assert meter.is_three_phase is True
    assert meter.quantities["activePowerL1"] == Quantity(
        "L1 Active power", "power.watt"
    )
    assert meter.measurements["activePowerL1"] is not None


def test_meter_without_data() -> None:
    """Test a meter without measurements; the name falls back to the ID."""
    meter = ElectricityMeter.from_dict({"name": " ", "circuitId": None}, "7")
    assert meter.id == "7"
    assert meter.name == "7"
    assert meter.manufacturer is None
    assert meter.circuit_id is None
    assert not meter.measurements
    assert not meter.quantities


def test_circuit() -> None:
    """Test a circuit."""
    circuit = Circuit.from_dict(load_json("circuit.json"), "x")
    assert circuit.id == "19923"
    assert circuit.electricity_meter_id == "37373"
    assert circuit.current_l1 == 0.058
    assert circuit.load_factor_15m == 0
    assert circuit.average_power_import_15m == 16
    assert circuit.current_limit == 20
    assert circuit.warnings == 0


def test_charge_point_connected() -> None:
    """Test a charge point with a vehicle that is connected."""
    charge_point = ChargePoint.from_dict(load_json("chargepoint_connected.json"))
    assert charge_point.id == "19463"
    assert charge_point.name == "Lader 06"
    assert charge_point.status == "SUSPENDED_BY_EV"
    assert charge_point.is_plugged_in is True
    assert charge_point.is_charging is False
    assert charge_point.current_user == "Alice"
    assert charge_point.started_at == datetime(2026, 11, 4, 6, 41, 24, tzinfo=UTC)
    # The end time is of the previous session.
    assert charge_point.finished_at is not None
    assert charge_point.session_finished_at is None
    assert charge_point.energy_charged == 33.06
    assert charge_point.charge_current == 16
    assert charge_point.phases_enabled == 3


def test_charge_point_available() -> None:
    """Test a charge point without a vehicle; the last user is kept."""
    charge_point = ChargePoint.from_dict(load_json("chargepoint_available.json"))
    assert charge_point.status == "AVAILABLE"
    assert charge_point.is_plugged_in is False
    assert charge_point.username == "Bob"
    assert charge_point.current_user is None
    assert charge_point.session_finished_at == charge_point.finished_at


def test_charge_point_without_session() -> None:
    """Test a charge point without session data."""
    charge_point = ChargePoint.from_dict({"session": {"startedAt": "nonsense"}}, "3")
    assert charge_point.name == "3"
    assert charge_point.is_plugged_in is None
    assert charge_point.is_charging is None
    assert charge_point.started_at is None
    assert charge_point.session_finished_at is None


def test_charge_point_naive_timestamp() -> None:
    """Test that timestamps without a time zone are in UTC."""
    charge_point = ChargePoint.from_dict(
        {"session": {"startedAt": "2026-11-04T06:41:24"}}
    )
    assert charge_point.started_at == datetime(2026, 11, 4, 6, 41, 24, tzinfo=UTC)


def test_energy_manager() -> None:
    """Test the state of the energy manager."""
    manager = EnergyManager.from_dict(load_json("energy_manager.json"), "x")
    assert manager.id == "11376"
    assert manager.name == "Energy Manager"
    assert manager.is_abnormal_condition is False
    assert manager.grid_power is not None
    assert manager.solar_power is not None
    assert manager.optimization_goal == "SCHEDULED_CHARGING"
    assert manager.binding_limit == "OPTIMAL_LIMIT"
    assert manager.cheapest_period_start is not None
    assert manager.cheapest_period_price is not None
    assert manager.baseline_price is not None


def test_energy_manager_empty() -> None:
    """Test the energy manager without data."""
    manager = EnergyManager.from_dict({}, "5")
    assert manager.id == "5"
    assert manager.name == "5"
    assert manager.grid_power is None


def test_space() -> None:
    """Test a space with plausible values."""
    space = Space.from_dict(load_json("space.json"), "x")
    assert space.id == "45472"
    assert space.temperature == 21.3
    assert space.humidity == 42
    assert space.co2 == 713
    assert space.illuminance == 897
    assert space.air_quality == "good"
    assert space.presence is None
    assert space.measured == frozenset(
        {"temperature", "humidity", "co2", "illuminance", "air_quality"}
    )


def test_space_invalid() -> None:
    """Test that impossible values of a space are None."""
    space = Space.from_dict(load_json("space_invalid.json"), "x")
    assert space.temperature is None
    assert space.humidity is None
    assert space.co2 == 409
    assert "temperature" in space.measured


def test_space_stale() -> None:
    """Test that stale values of a space are None."""
    space = Space.from_dict(
        {
            "values": {
                "temperature": {"value": 21, "isStale": True, "updatedAt": "x"},
                "presence": {"value": True, "isStale": False, "updatedAt": "x"},
                "airQuality": {"value": None, "label": "good", "updatedAt": "x"},
            }
        },
        "9",
    )
    assert space.id == "9"
    assert space.temperature is None
    assert space.presence is True
    assert space.air_quality is None


def test_system() -> None:
    """Test the status of the server."""
    system = SystemStatus.from_dict(load_json("system.json"))
    assert system.cpu_usage == 18
    assert system.memory_available == 8000
    assert system.disk_free == 250000
    assert system.last_backup_at == datetime.fromtimestamp(1793750400, tz=UTC)
    assert system.system_uptime == timedelta(seconds=864000)
    assert system.symcon_version == "1.0 / 2026.01.01"
    assert system.io_connection_faults == 1


def test_system_never_backed_up() -> None:
    """Test that a backup time of 0 means never."""
    assert SystemStatus.from_dict({"lastBackupAt": 0}).last_backup_at is None


def test_milesight() -> None:
    """Test a Milesight sensor."""
    sensor = MilesightSensor.from_dict(load_json("milesight.json"), "a81758fffe054f0d")
    assert sensor.eui == "a81758fffe054f0d"
    assert sensor.temperature == 21.3
    assert sensor.co2 == 713
    assert sensor.motion is False
    assert sensor.battery_voltage == 3629
    assert sensor.measured == frozenset(
        {"temperature", "humidity", "co2", "motion", "battery_voltage"}
    )


def test_plausible() -> None:
    """Test the plausibility check."""
    assert plausible(20, (0, 30)) == 20
    assert plausible(-1001.1, (-40, 80)) is None
    assert plausible(True, (0, 30)) is None  # noqa: FBT003
    assert plausible("20", (0, 30)) is None


def test_charge_point_throttled() -> None:
    """Test that a vehicle that limits the power is connected and charging."""
    charge_point = ChargePoint.from_dict(
        {"session": {"status": "THROTTLED_BY_EV", "chargingState": "CHARGING"}}
    )
    assert charge_point.is_plugged_in is True
    assert charge_point.is_charging is True


def test_charge_point_charging_without_state() -> None:
    """Test that the status tells whether it charges without a charging state."""
    charge_point = ChargePoint.from_dict({"session": {"status": "CHARGING"}})
    assert charge_point.is_charging is True


def test_charge_point_event() -> None:
    """Test an event of a charge point whose session changed."""
    event = ChargePointEvent.from_dict(load_json("chargepoint_event.json"), "30657")
    assert event.charge_point_id == "30657"
    assert event.event == "sessionchanged"
    assert event.time == datetime(2026, 11, 4, 16, 38, 44, tzinfo=UTC)
    assert event.charge_point.id == "30657"
    assert event.charge_point.status == "THROTTLED_BY_EV"
    assert event.charge_point.is_plugged_in is True
    assert event.charge_point.current_user == "Alice"


def test_charge_point_event_empty() -> None:
    """Test an event without a payload."""
    event = ChargePointEvent.from_dict({}, "1")
    assert event.event == ""
    assert event.time is None
    assert event.charge_point.status is None


def test_milesight_light() -> None:
    """Test a Milesight sensor that measures light and counts motion."""
    sensor = MilesightSensor.from_dict(load_json("milesight_light.json"), "x")
    assert sensor.illuminance == 503
    assert sensor.motion is True
    assert "illuminance" in sensor.measured
    assert "battery_voltage" not in sensor.measured


def test_invalid_numbers() -> None:
    """Test that numbers that JSON allows but are not valid values are None."""
    circuit = Circuit.from_dict({"warnings": float("nan"), "currentL1": float("inf")})
    assert circuit.warnings is None
    assert circuit.current_l1 is None
    system = SystemStatus.from_dict(
        {"lastBackupAt": 1e20, "systemUptimeSeconds": 1e300, "cpuUsage": float("nan")}
    )
    assert system.last_backup_at is None
    assert system.system_uptime is None
    assert system.cpu_usage is None
