from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PumpFuseClient
from .coordinator import PumpFuseConfigEntry, PumpFuseCoordinator

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class PumpFuseButtonEntityDescription(ButtonEntityDescription):
    press_fn: Callable[[PumpFuseClient], Awaitable[None]]


DESCRIPTIONS = (
    PumpFuseButtonEntityDescription(
        key="reset_lockout",
        translation_key="reset_lockout",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda client: client.reset_lockout(),
    ),
    PumpFuseButtonEntityDescription(
        key="reset_stats",
        translation_key="reset_stats",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda client: client.reset_stats(),
    ),
)


class PumpFuseButton(CoordinatorEntity[PumpFuseCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    entity_description: PumpFuseButtonEntityDescription

    def __init__(
        self,
        coordinator: PumpFuseCoordinator,
        description: PumpFuseButtonEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.mac}_{description.key}"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        description = self.entity_description
        await self.coordinator.async_command(
            description.key.replace("_", " "),
            lambda client, state: description.press_fn(client),
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PumpFuseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        PumpFuseButton(entry.runtime_data, item) for item in DESCRIPTIONS
    )
