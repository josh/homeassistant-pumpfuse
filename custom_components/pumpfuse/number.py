from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PumpFuseState
from .coordinator import PumpFuseConfigEntry, PumpFuseCoordinator

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class PumpFuseNumberEntityDescription(NumberEntityDescription):
    field: str
    value_fn: Callable[[PumpFuseState], int]


DESCRIPTIONS = (
    PumpFuseNumberEntityDescription(
        key="inactivity_window",
        translation_key="inactivity_window",
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        native_min_value=1,
        native_max_value=43200,
        native_step=1,
        mode=NumberMode.BOX,
        field="inactivity_alert_min",
        value_fn=lambda state: state.sump["inactivity_alert_min"],
    ),
    PumpFuseNumberEntityDescription(
        key="lockout_duration",
        translation_key="lockout_duration",
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        native_min_value=1,
        native_max_value=480,
        native_step=1,
        mode=NumberMode.BOX,
        field="anomaly_lockout_min",
        value_fn=lambda state: state.sump["anomaly_lockout_min"],
    ),
    PumpFuseNumberEntityDescription(
        key="max_retries",
        translation_key="max_retries",
        entity_category=EntityCategory.CONFIG,
        native_min_value=1,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.BOX,
        field="lockout_max_retries",
        value_fn=lambda state: state.sump["lockout_max_retries"],
    ),
)


class PumpFuseNumber(CoordinatorEntity[PumpFuseCoordinator], NumberEntity):
    _attr_has_entity_name = True
    entity_description: PumpFuseNumberEntityDescription

    def __init__(
        self,
        coordinator: PumpFuseCoordinator,
        description: PumpFuseNumberEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.mac}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> int:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        description = self.entity_description
        target = int(value)
        await self.coordinator.async_command(
            f"set {description.field} to {target}",
            lambda client, state: client.set_sump_config({description.field: target}),
            lambda state: description.value_fn(state) == target,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PumpFuseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        PumpFuseNumber(entry.runtime_data, item) for item in DESCRIPTIONS
    )
