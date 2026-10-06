from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PumpFuseState
from .const import ALERTS
from .coordinator import PumpFuseConfigEntry, PumpFuseCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class PumpFuseBinarySensorEntityDescription(BinarySensorEntityDescription):
    value_fn: Callable[[PumpFuseState], bool]
    attributes_fn: Callable[[PumpFuseState], Mapping[str, Any]] | None = None


def _alert(key: str) -> PumpFuseBinarySensorEntityDescription:
    return PumpFuseBinarySensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda state: key in state.sump["alerts"],
    )


DESCRIPTIONS = (
    PumpFuseBinarySensorEntityDescription(
        key="pump_running",
        translation_key="pump_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda state: state.sump["pump_running"],
    ),
    *(_alert(key) for key in ALERTS),
    PumpFuseBinarySensorEntityDescription(
        key="protection_auto_disabled",
        translation_key="protection_auto_disabled",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda state: state.sump["protection_auto_disabled"],
    ),
    PumpFuseBinarySensorEntityDescription(
        key="lockout_active",
        translation_key="lockout_active",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda state: state.sump["lockout_active"],
        attributes_fn=lambda state: {
            "alert": state.sump["lockout_alert"],
            "retries_used": state.sump["lockout_retries_used"],
            "max_retries": state.sump["lockout_max_retries"],
        },
    ),
)


class PumpFuseBinarySensor(CoordinatorEntity[PumpFuseCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    entity_description: PumpFuseBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: PumpFuseCoordinator,
        description: PumpFuseBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.mac}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
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
        PumpFuseBinarySensor(entry.runtime_data, item) for item in DESCRIPTIONS
    )
