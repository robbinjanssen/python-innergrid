# pylint: disable=too-many-instance-attributes
"""Models of the data that Innergrid publishes."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Self, TypeAlias

from .const import (
    CO2_RANGE,
    CONNECTED_STATUSES,
    HUMIDITY_RANGE,
    ILLUMINANCE_RANGE,
    TEMPERATURE_RANGE,
)


def get_path(data: Any, path: str) -> Any:
    """Return the value at a dotted path, or None if a part is missing."""
    value = data
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _number(value: Any) -> float | None:
    """Return the value if it is a finite number.

    JSON payloads can hold NaN and Infinity, which are not valid values.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value if math.isfinite(value) else None


def _int(value: Any) -> int | None:
    """Return the value if it is a whole number."""
    number = _number(value)
    return None if number is None else int(number)


def _text(value: Any) -> str | None:
    """Return a non-empty string, without surrounding whitespace."""
    if not isinstance(value, str) or not (text := value.strip()):
        return None
    return text


def _bool(value: Any) -> bool | None:
    """Return a boolean, or a 0/1 number, as a boolean."""
    if isinstance(value, bool | int):
        return bool(value)
    return None


def _timestamp(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _epoch(value: Any) -> datetime | None:
    """Return a Unix timestamp as a datetime; 0 means never."""
    if not (seconds := _number(value)):
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _seconds(value: Any) -> timedelta | None:
    """Return a number of seconds as a timedelta."""
    if (seconds := _number(value)) is None:
        return None
    try:
        return timedelta(seconds=seconds)
    except OverflowError:
        return None


def plausible(value: Any, valid_range: tuple[float, float]) -> float | None:
    """Return the value if it is a number within the range, otherwise None."""
    number = _number(value)
    if number is None or not valid_range[0] <= number <= valid_range[1]:
        return None
    return number


def _id(data: dict[str, Any], default: str) -> str:
    """Return the ID in the data, or the default (the ID from the topic)."""
    value = data.get("id")
    return default if value is None else str(value)


@dataclass
class SiteMeter:
    """A meter of a site: the grid connection, production or consumption."""

    id: str | None
    name: str | None
    active_power: float | None
    energy_imported_24h: float | None
    energy_exported_24h: float | None
    max_power_quarter_hour_import: float | None
    max_power_quarter_hour_export: float | None
    continuous_import_limit: float | None
    continuous_export_limit: float | None

    @classmethod
    def from_dict(cls, data: Any) -> SiteMeter | None:
        """Return the meter, or None if the site does not have it."""
        if not isinstance(data, dict):
            return None
        meter_id = data.get("id")
        return cls(
            id=None if meter_id is None else str(meter_id),
            name=_text(data.get("name")),
            active_power=_number(data.get("activePower")),
            energy_imported_24h=_number(data.get("energyImported24h")),
            energy_exported_24h=_number(data.get("energyExported24h")),
            max_power_quarter_hour_import=_number(
                data.get("maxActivePowerQuarterHourImport")
            ),
            max_power_quarter_hour_export=_number(
                data.get("maxActivePowerQuarterHourExport")
            ),
            continuous_import_limit=_number(
                data.get("continuousActivePowerImportLimit")
            ),
            continuous_export_limit=_number(
                data.get("continuousActivePowerExportLimit")
            ),
        )


@dataclass
class Site:
    """The overview of a customer site (customersites/<id>/live).

    Energy and money are totals of the last 24 hours, which go up and down.
    """

    id: str
    grid: SiteMeter | None
    production: SiteMeter | None
    consumption: SiteMeter | None
    battery_storage: SiteMeter | None
    expense_24h: float | None
    revenue_24h: float | None
    energy_price_import: float | None
    energy_price_export: float | None
    main_circuit_load_factor: float | None

    @classmethod
    def from_dict(cls, data: dict[str, Any], site_id: str = "") -> Self:
        """Parse the payload of a site."""
        return cls(
            id=_id(data, site_id),
            grid=SiteMeter.from_dict(get_path(data, "electricityMeters.main")),
            production=SiteMeter.from_dict(
                get_path(data, "electricityMeters.production")
            ),
            consumption=SiteMeter.from_dict(
                get_path(data, "electricityMeters.consumption")
            ),
            battery_storage=SiteMeter.from_dict(
                get_path(data, "electricityMeters.batteryStorage")
            ),
            expense_24h=_number(data.get("expense24h")),
            revenue_24h=_number(data.get("revenue24h")),
            energy_price_import=_number(get_path(data, "energyPrices.import")),
            energy_price_export=_number(get_path(data, "energyPrices.export")),
            main_circuit_load_factor=_number(
                get_path(data, "mainCircuit.currentLoadFactor1Minute")
            ),
        )


@dataclass
class Category:
    """The energy of a category of a site, such as lighting or the kitchen."""

    key: str
    name: str
    active_power: float | None
    energy_imported_24h: float | None
    energy_exported_24h: float | None
    expense_24h: float | None
    revenue_24h: float | None

    @classmethod
    def from_dict(cls, key: str, data: dict[str, Any]) -> Self:
        """Parse a category."""
        return cls(
            key=key,
            name=_text(data.get("name")) or key,
            active_power=_number(data.get("activePower")),
            energy_imported_24h=_number(data.get("energyImported24h")),
            energy_exported_24h=_number(data.get("energyExported24h")),
            expense_24h=_number(data.get("expense24h")),
            revenue_24h=_number(data.get("revenue24h")),
        )


@dataclass
class Categories:
    """The energy categories of a site (categories/<id>/live)."""

    site_id: str
    categories: dict[str, Category]

    @classmethod
    def from_dict(cls, data: dict[str, Any], site_id: str = "") -> Self:
        """Parse the payload of the categories of a site."""
        categories = data.get("categories")
        if not isinstance(categories, dict):
            categories = {}
        return cls(
            site_id=site_id,
            categories={
                key: Category.from_dict(key, values)
                for key, values in categories.items()
                if isinstance(values, dict)
            },
        )


@dataclass(frozen=True)
class Quantity:
    """A quantity that a meter measures, with its name and unit.

    The unit is as the platform names it, for example power.watt.
    """

    name: str
    unit: str


@dataclass
class ElectricityMeter:
    """An electricity meter (electricitymeters/<id>).

    The measurements are by quantity, for example activePower or
    activePowerL1; the quantities describe their names and units.
    """

    id: str
    name: str
    module_name: str | None
    location: str | None
    circuit_id: str | None
    is_three_phase: bool | None
    measurements: dict[str, float | None]
    quantities: dict[str, Quantity]

    @property
    def manufacturer(self) -> str | None:
        """Return the manufacturer: the first word of the module name."""
        return self.module_name.split()[0] if self.module_name else None

    @classmethod
    def from_dict(cls, data: dict[str, Any], meter_id: str = "") -> Self:
        """Parse the payload of an electricity meter."""
        measurements = data.get("measurements")
        if not isinstance(measurements, dict):
            measurements = {}
        quantities = data.get("loggedQuantities")
        if not isinstance(quantities, dict):
            quantities = {}
        circuit_id = data.get("circuitId")
        meter_id = _id(data, meter_id)
        return cls(
            id=meter_id,
            name=_text(data.get("name")) or meter_id,
            module_name=_text(data.get("moduleName")),
            location=_text(data.get("location")),
            circuit_id=None if circuit_id is None else str(circuit_id),
            is_three_phase=_bool(data.get("isThreePhase")),
            measurements={key: _number(value) for key, value in measurements.items()},
            quantities={
                key: Quantity(
                    name=_text(quantity.get("name")) or key,
                    unit=str(quantity.get("unit") or ""),
                )
                for key, quantity in quantities.items()
                if isinstance(quantity, dict) and key in measurements
            },
        )


@dataclass
class Circuit:
    """A circuit, measured by an electricity meter (circuits/<id>/live).

    Load factors are fractions of the circuit's limit, for example 0.25.
    """

    id: str
    name: str
    electricity_meter_id: str | None
    is_three_phase: bool | None
    active_power: float | None
    current_l1: float | None
    current_l2: float | None
    current_l3: float | None
    load_factor_1m: float | None
    load_factor_5m: float | None
    load_factor_15m: float | None
    average_power_import_15m: float | None
    average_power_export_15m: float | None
    current_limit: float | None
    warnings: int | None

    @classmethod
    def from_dict(cls, data: dict[str, Any], circuit_id: str = "") -> Self:
        """Parse the payload of a circuit."""
        meter_id = data.get("electricityMeterId")
        circuit_id = _id(data, circuit_id)
        return cls(
            id=circuit_id,
            name=_text(data.get("name")) or circuit_id,
            electricity_meter_id=None if meter_id is None else str(meter_id),
            is_three_phase=_bool(data.get("isThreePhase")),
            active_power=_number(data.get("activePower")),
            current_l1=_number(data.get("currentL1")),
            current_l2=_number(data.get("currentL2")),
            current_l3=_number(data.get("currentL3")),
            load_factor_1m=_number(get_path(data, "currentLoadFactor.1-minute")),
            load_factor_5m=_number(get_path(data, "currentLoadFactor.5-minute")),
            load_factor_15m=_number(get_path(data, "currentLoadFactor.15-minute")),
            average_power_import_15m=_number(
                get_path(data, "averageActivePower.15-minute.import")
            ),
            average_power_export_15m=_number(
                get_path(data, "averageActivePower.15-minute.export")
            ),
            current_limit=_number(get_path(data, "instantaneousLimits.current")),
            warnings=_int(data.get("warnings")),
        )


@dataclass
class ChargePoint:
    """A charge point and its (last) session (chargepoints/<id>).

    The session fields keep the values of the last session after it ended.
    """

    id: str
    name: str
    status: str | None
    charging_state: str | None
    charge_strategy: str | None
    username: str | None
    started_at: datetime | None
    finished_at: datetime | None
    departure_at: datetime | None
    target_energy: float | None
    minimum_power: float | None
    active_power: float | None
    energy_charged: float | None
    charge_current: float | None
    phases_enabled: int | None
    power_instruction: float | None

    @property
    def is_plugged_in(self) -> bool | None:
        """Return whether a vehicle is connected."""
        return None if self.status is None else self.status in CONNECTED_STATUSES

    @property
    def is_charging(self) -> bool | None:
        """Return whether the vehicle is charging.

        The charging state is CHARGING also while the vehicle limits the power
        (status THROTTLED_BY_EV); without it, the status tells.
        """
        if self.charging_state is not None:
            return self.charging_state == "CHARGING"
        return None if self.status is None else self.status == "CHARGING"

    @property
    def current_user(self) -> str | None:
        """Return who is charging; None when no vehicle is connected."""
        return self.username if self.is_plugged_in else None

    @property
    def session_finished_at(self) -> datetime | None:
        """Return the end of the session, unless a newer session started."""
        if self.finished_at is None or (
            self.started_at is not None and self.finished_at < self.started_at
        ):
            return None
        return self.finished_at

    @classmethod
    def from_dict(cls, data: dict[str, Any], charge_point_id: str = "") -> Self:
        """Parse the payload of a charge point."""
        charge_point_id = _id(data, charge_point_id)
        return cls(
            id=charge_point_id,
            name=_text(data.get("name")) or charge_point_id,
            status=_text(get_path(data, "session.status")),
            charging_state=_text(get_path(data, "session.chargingState")),
            charge_strategy=_text(get_path(data, "session.chargeStrategy")),
            username=_text(get_path(data, "session.username")),
            started_at=_timestamp(get_path(data, "session.startedAt")),
            finished_at=_timestamp(get_path(data, "session.finishedAt")),
            departure_at=_timestamp(get_path(data, "session.departureAt")),
            target_energy=_number(get_path(data, "session.targetEnergyRequest")),
            minimum_power=_number(get_path(data, "session.minimumPower")),
            active_power=_number(get_path(data, "measurements.activePower")),
            energy_charged=_number(get_path(data, "measurements.energyCharged")),
            charge_current=_number(get_path(data, "powerManagement.chargeCurrent")),
            phases_enabled=_int(get_path(data, "powerManagement.phasesEnabled")),
            power_instruction=_number(
                get_path(data, "powerManagement.powerInstruction")
            ),
        )


@dataclass
class EnergyManager:
    """The state of the energy manager (energymanagers/<id>/state)."""

    id: str
    name: str
    is_abnormal_condition: bool | None
    is_temporary_over_limit_applied: bool | None
    is_solar_charging_only: bool | None
    grid_power: float | None
    solar_power: float | None
    charge_point_power: float | None
    climate_power: float | None
    baseload_power: float | None
    inflexible_power: float | None
    battery_power: float | None
    optimized_import_power: float | None
    flexible_power: float | None
    continuous_import_limit: float | None
    instantaneous_import_limit: float | None
    continuous_export_limit: float | None
    instantaneous_export_limit: float | None
    peak_shaving_limit: float | None
    optimization_goal: str | None
    binding_limit: str | None
    strategy: str | None
    cheapest_period_start: datetime | None
    cheapest_period_price: float | None
    baseline_price: float | None
    export_price: float | None

    @classmethod
    def from_dict(cls, data: dict[str, Any], manager_id: str = "") -> Self:
        """Parse the payload of the energy manager's state."""
        manager = data.get("energyManager")
        if not isinstance(manager, dict):
            manager = {}
        manager_id = _id(manager, manager_id)

        def power(name: str) -> float | None:
            return _number(get_path(manager, f"powerValues.{name}"))

        def strategy(path: str) -> Any:
            return get_path(manager, f"strategy.{path}")

        return cls(
            id=manager_id,
            name=_text(manager.get("name")) or manager_id,
            is_abnormal_condition=_bool(manager.get("isAbnormalCondition")),
            is_temporary_over_limit_applied=_bool(
                manager.get("isTemporaryOverLimitApplied")
            ),
            is_solar_charging_only=_bool(manager.get("isSolarChargingOnly")),
            grid_power=power("gridActivePower"),
            solar_power=power("solarPower"),
            charge_point_power=power("chargePointPower"),
            climate_power=power("climatePower"),
            baseload_power=power("baseloadPower"),
            inflexible_power=power("inflexiblePower"),
            battery_power=power("batteryPower"),
            optimized_import_power=power("optimizedImportPower"),
            flexible_power=power("appliedFlexibleResourcePower"),
            continuous_import_limit=power("continuousActivePowerImportLimit"),
            instantaneous_import_limit=power("instantaneousActivePowerImportLimit"),
            continuous_export_limit=power("continuousActivePowerExportLimit"),
            instantaneous_export_limit=power("instantaneousActivePowerExportLimit"),
            peak_shaving_limit=power("peakShavingResourcePowerLimit"),
            optimization_goal=_text(strategy("optimizationGoal")),
            binding_limit=_text(strategy("bindingLimit")),
            strategy=_text(strategy("description")),
            cheapest_period_start=_timestamp(
                strategy("optimizationStrategy.cheapestPeriodStart")
            ),
            cheapest_period_price=_number(
                strategy("optimizationStrategy.cheapestPeriodPrice")
            ),
            baseline_price=_number(strategy("optimizationStrategy.baselinePrice")),
            export_price=_number(strategy("optimizationStrategy.currentExportPrice")),
        )


# The values of a space, by attribute name and name in the payload.
SPACE_VALUES = {
    "temperature": "temperature",
    "humidity": "relativeHumidity",
    "co2": "co2Concentration",
    "illuminance": "illuminance",
    "air_quality": "airQuality",
    "presence": "presence",
    "occupancy": "occupancy",
}


@dataclass
class Space:
    """The climate and presence of a space (spaces/<id>/live).

    The payload does not include the space's name. Values that are stale or
    not plausible (for example -1001.1 °C) are None. `measured` holds the
    names of the values that the space has sensors for.
    """

    id: str
    temperature: float | None
    humidity: float | None
    co2: float | None
    illuminance: float | None
    air_quality: str | None
    presence: bool | None
    occupancy: bool | None
    low_battery_count: int | None
    measured: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_dict(cls, data: dict[str, Any], space_id: str = "") -> Self:
        """Parse the payload of a space."""
        values = data.get("values")
        if not isinstance(values, dict):
            values = {}

        def value(name: str, key: str = "value") -> Any:
            entry = values.get(SPACE_VALUES[name])
            if not isinstance(entry, dict) or entry.get("isStale"):
                return None
            return entry.get(key)

        return cls(
            id=_id(data, space_id),
            temperature=plausible(value("temperature"), TEMPERATURE_RANGE),
            humidity=plausible(value("humidity"), HUMIDITY_RANGE),
            co2=plausible(value("co2"), CO2_RANGE),
            illuminance=plausible(value("illuminance"), ILLUMINANCE_RANGE),
            air_quality=(
                None
                if value("air_quality") is None
                else _text(value("air_quality", "label"))
            ),
            presence=_bool(value("presence")),
            occupancy=_bool(value("occupancy")),
            low_battery_count=_int(data.get("lowBatteryCount")),
            measured=frozenset(
                name
                for name, key in SPACE_VALUES.items()
                if get_path(values, f"{key}.updatedAt") is not None
            ),
        )


@dataclass
class SystemStatus:
    """The status of the server that publishes the data (system).

    Memory and disk sizes are in MiB.
    """

    cpu_usage: float | None
    memory_available: float | None
    memory_total: float | None
    disk_free: float | None
    disk_total: float | None
    last_backup_at: datetime | None
    backup_file_count: int | None
    system_uptime: timedelta | None
    symcon_uptime: timedelta | None
    symcon_version: str | None
    module_library_version: str | None
    io_connection_faults: int | None
    instances_not_active: int | None
    overdue_timers: int | None
    api_request_count: int | None

    @classmethod
    def from_dict(cls, data: dict[str, Any], _system_id: str = "") -> Self:
        """Parse the payload of the system status."""
        return cls(
            cpu_usage=_number(data.get("cpuUsage")),
            memory_available=_number(data.get("availableMemory")),
            memory_total=_number(data.get("totalMemory")),
            disk_free=_number(data.get("filesystemFreeSpace")),
            disk_total=_number(data.get("filesystemTotalSpace")),
            last_backup_at=_epoch(data.get("lastBackupAt")),
            backup_file_count=_int(data.get("backupFileCount")),
            system_uptime=_seconds(data.get("systemUptimeSeconds")),
            symcon_uptime=_seconds(data.get("symconUptimeSeconds")),
            symcon_version=_text(data.get("symconVersion")),
            module_library_version=_text(data.get("moduleLibraryVersion")),
            io_connection_faults=_int(data.get("ioConnectionFaults")),
            instances_not_active=_int(data.get("instancesNotActive")),
            overdue_timers=_int(data.get("overdueTimers")),
            api_request_count=_int(data.get("apiRequestCount")),
        )


# The values of a Milesight sensor, by attribute name and name in the payload.
MILESIGHT_VALUES = {
    "temperature": "temperature",
    "humidity": "humidity",
    "co2": "co2",
    "illuminance": "light",
    "motion": "motion",
    "battery_voltage": "vdd",
}


@dataclass
class MilesightSensor:
    """A Milesight LoRaWAN sensor (milesight/uplink/<devEUI>).

    Values that are not plausible are None. `measured` holds the names of
    the values in the payload, which depend on the sensor's model. The
    illuminance is in lux and the battery voltage in mV. Motion is true when
    the sensor counted any motion (the count can be higher than 1).
    """

    eui: str
    temperature: float | None
    humidity: float | None
    co2: float | None
    illuminance: float | None
    motion: bool | None
    battery_voltage: float | None
    measured: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_dict(cls, data: dict[str, Any], eui: str = "") -> Self:
        """Parse the payload of a Milesight sensor."""
        return cls(
            eui=eui,
            temperature=plausible(data.get("temperature"), TEMPERATURE_RANGE),
            humidity=plausible(data.get("humidity"), HUMIDITY_RANGE),
            co2=plausible(data.get("co2"), CO2_RANGE),
            illuminance=plausible(data.get("light"), ILLUMINANCE_RANGE),
            motion=_bool(data.get("motion")),
            battery_voltage=_number(data.get("vdd")),
            measured=frozenset(
                name for name, key in MILESIGHT_VALUES.items() if key in data
            ),
        )


@dataclass
class ChargePointEvent:
    """An event of a charge point (events/chargepoints/<id>/<event>).

    The charge point publishes `sessionchanged` when its session changes, for
    example when charging starts or stops. `charge_point` holds the session
    after the change; its other fields are None.
    """

    charge_point_id: str
    event: str
    time: datetime | None
    charge_point: ChargePoint

    @classmethod
    def from_dict(cls, data: dict[str, Any], charge_point_id: str = "") -> Self:
        """Parse the payload of a charge point event."""
        payload = data.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        return cls(
            charge_point_id=charge_point_id,
            event=_text(data.get("name")) or "",
            time=_timestamp(data.get("time")),
            charge_point=ChargePoint.from_dict(
                {"session": payload.get("session")}, charge_point_id
            ),
        )


# Python 3.11 does not support the type statement.
Model: TypeAlias = (
    Site
    | Categories
    | ElectricityMeter
    | Circuit
    | ChargePoint
    | ChargePointEvent
    | EnergyManager
    | Space
    | SystemStatus
    | MilesightSensor
)
