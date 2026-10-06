from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PumpFuseClient, PumpFuseState
from .const import ALERTS, RELAY_CUT_ALERTS
from .coordinator import PumpFuseConfigEntry, PumpFuseCoordinator

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class PumpFuseSwitchEntityDescription(SwitchEntityDescription):
    value_fn: Callable[[PumpFuseState], bool]
    command_fn: Callable[[PumpFuseClient, PumpFuseState, bool], Awaitable[None]]


def _mask_switch(
    prefix: str,
    field: str,
    mask_fn: Callable[[PumpFuseState], int],
    bit: int,
    key: str,
) -> PumpFuseSwitchEntityDescription:
    def value_fn(state: PumpFuseState) -> bool:
        return bool(mask_fn(state) & (1 << bit))

    async def command_fn(
        client: PumpFuseClient, state: PumpFuseState, on: bool
    ) -> None:
        mask = mask_fn(state)
        await client.set_sump_config(
            {field: mask | (1 << bit) if on else mask & ~(1 << bit)}
        )

    return PumpFuseSwitchEntityDescription(
        key=f"{prefix}_{key}",
        translation_key=f"{prefix}_{key}",
        entity_category=EntityCategory.CONFIG,
        value_fn=value_fn,
        command_fn=command_fn,
    )


DESCRIPTIONS = (
    PumpFuseSwitchEntityDescription(
        key="relay",
        translation_key="relay",
        device_class=SwitchDeviceClass.OUTLET,
        value_fn=lambda state: state.status["relay"],
        command_fn=lambda client, state, on: client.set_relay(on),
    ),
    *(
        _mask_switch(
            "alert",
            "alert_enable_mask",
            lambda state: state.sump["alert_enable_mask"],
            bit,
            key,
        )
        for bit, key in enumerate(ALERTS)
    ),
    *(
        _mask_switch(
            "relay_cut",
            "relay_cut_mask",
            lambda state: state.sump["relay_cut_mask"],
            bit,
            key,
        )
        for bit, key in enumerate(RELAY_CUT_ALERTS)
    ),
)


class PumpFuseSwitch(CoordinatorEntity[PumpFuseCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    entity_description: PumpFuseSwitchEntityDescription

    def __init__(
        self,
        coordinator: PumpFuseCoordinator,
        description: PumpFuseSwitchEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.mac}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data)

    async def _async_set(self, on: bool) -> None:
        description = self.entity_description
        await self.coordinator.async_command(
            f"turn {'on' if on else 'off'} {description.key}",
            lambda client, state: description.command_fn(client, state, on),
            lambda state: description.value_fn(state) is on,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PumpFuseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        PumpFuseSwitch(entry.runtime_data, item) for item in DESCRIPTIONS
    )
