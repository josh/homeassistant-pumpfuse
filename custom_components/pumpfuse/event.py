import json

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import EVENT_TYPES, HistoryEvent
from .coordinator import PumpFuseConfigEntry, PumpFuseCoordinator

PARALLEL_UPDATES = 0


def _key(entry: HistoryEvent) -> str:
    return json.dumps(entry, sort_keys=True)


class PumpFuseEvent(CoordinatorEntity[PumpFuseCoordinator], EventEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "event"
    _attr_event_types = EVENT_TYPES

    def __init__(self, coordinator: PumpFuseCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_event"
        self._attr_device_info = coordinator.device_info
        # The device keeps a ring of recent events. Anything already in it when
        # Home Assistant starts is history, not news.
        self._seen = {_key(entry) for entry in coordinator.data.history}

    @callback
    def _handle_coordinator_update(self) -> None:
        history = self.coordinator.data.history
        fresh = [entry for entry in history if _key(entry) not in self._seen]
        self._seen = {_key(entry) for entry in history}
        fired = False
        for entry in fresh:
            if entry["event"] not in EVENT_TYPES:
                continue
            attributes = {k: v for k, v in entry.items() if k != "event"}
            self._trigger_event(entry["event"], attributes)
            self.async_write_ha_state()
            fired = True
        if not fired:
            super()._handle_coordinator_update()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PumpFuseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PumpFuseEvent(entry.runtime_data)])
