from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PumpFuseState
from .const import PROTECTION_MODES
from .coordinator import PumpFuseConfigEntry, PumpFuseCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class PumpFuseSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[PumpFuseState], StateType | datetime]
    attributes_fn: Callable[[PumpFuseState], Mapping[str, Any]] | None = None


def _timestamp(ms: int | None) -> datetime | None:
    return datetime.fromtimestamp(ms / 1000, UTC) if ms else None


def _protection_mode(state: PumpFuseState) -> str | None:
    mode = state.sump["protection_mode"]
    return mode if mode in PROTECTION_MODES else None


def _last_run_attributes(state: PumpFuseState) -> Mapping[str, Any]:
    last_run = state.last_run
    if last_run is None or last_run["end_ms"] != state.sump["last_run_end_ms"]:
        return {}
    return {
        "start": _timestamp(last_run["start_ms"]),
        "power_std_dev": last_run["std_w"],
        "power_samples": last_run["samples"],
    }


def _power(
    key: str, value_fn: Callable[[PumpFuseState], float | None], **kwargs: Any
) -> PumpFuseSensorEntityDescription:
    return PumpFuseSensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=value_fn,
        **{
            "state_class": SensorStateClass.MEASUREMENT,
            "suggested_display_precision": 1,
            **kwargs,
        },
    )


def _duration(
    key: str, value_fn: Callable[[PumpFuseState], float | None], **kwargs: Any
) -> PumpFuseSensorEntityDescription:
    return PumpFuseSensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=value_fn,
        **{
            "state_class": SensorStateClass.MEASUREMENT,
            "suggested_display_precision": 0,
            **kwargs,
        },
    )


DESCRIPTIONS = (
    _power("power", lambda state: state.sump["current_power_w"]),
    PumpFuseSensorEntityDescription(
        key="protection_mode",
        translation_key="protection_mode",
        device_class=SensorDeviceClass.ENUM,
        options=PROTECTION_MODES,
        value_fn=_protection_mode,
    ),
    _duration("current_run", lambda state: state.sump["current_run_s"]),
    _duration("last_run_duration", lambda state: state.sump["last_run_dur_s"]),
    PumpFuseSensorEntityDescription(
        key="last_run_time",
        translation_key="last_run_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda state: _timestamp(state.sump["last_run_end_ms"]),
        attributes_fn=_last_run_attributes,
    ),
    PumpFuseSensorEntityDescription(
        key="total_runs",
        translation_key="total_runs",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda state: state.sump["run_count_total"],
    ),
    PumpFuseSensorEntityDescription(
        key="runs_last_24h",
        translation_key="runs_last_24h",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.sump["runs_last_24h"],
    ),
    _duration(
        "average_run_duration",
        lambda state: state.learn["runtime_mean"],
        suggested_display_precision=1,
    ),
    _power("baseline_power", lambda state: state.learn["wattage_mean"]),
    _duration("last_outage", lambda state: state.sump["last_outage_s"]),
    _duration(
        "total_runtime",
        lambda state: state.sump["total_runtime_s"],
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
    ),
    _power("last_run_average_power", lambda state: state.sump["last_run_avg_w"]),
    _power("last_run_peak_power", lambda state: state.sump["last_run_peak_w"]),
    _duration("lockout_remaining", lambda state: state.sump["lockout_remaining_s"]),
    _duration("inter_run_gap", lambda state: state.sump["inter_run_gap_mean"]),
    _power(
        "on_threshold",
        lambda state: state.sump["on_threshold_w"],
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    _power(
        "idle_power",
        lambda state: state.sump["idle_w"],
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    PumpFuseSensorEntityDescription(
        key="learned_cycles",
        translation_key="learned_cycles",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.learn["cycle_count"],
    ),
    PumpFuseSensorEntityDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.status["wifi_rssi"],
    ),
    _duration(
        "uptime",
        lambda state: state.status["uptime"],
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


class PumpFuseSensor(CoordinatorEntity[PumpFuseCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({"power_samples"})
    entity_description: PumpFuseSensorEntityDescription

    def __init__(
        self,
        coordinator: PumpFuseCoordinator,
        description: PumpFuseSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.mac}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        attributes_fn = self.entity_description.attributes_fn
        return attributes_fn(self.coordinator.data) if attributes_fn else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PumpFuseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        PumpFuseSensor(entry.runtime_data, item) for item in DESCRIPTIONS
    )
