import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PumpFuseClient, PumpFuseError, PumpFuseState
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, MANUFACTURER, MODEL

_LOGGER = logging.getLogger(__name__)

FULL_REFRESH_INTERVAL = 60.0

type Command = Callable[[PumpFuseClient, PumpFuseState], Awaitable[None]]


class PumpFuseCoordinator(DataUpdateCoordinator[PumpFuseState]):
    def __init__(
        self, hass: HomeAssistant, entry: PumpFuseConfigEntry, client: PumpFuseClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(
                seconds=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
            always_update=False,
        )
        self._operation_lock = asyncio.Lock()
        self.client = client
        self.device_name = entry.data.get(CONF_NAME) or MODEL
        self.mac = str(entry.unique_id)
        self._next_full_refresh = 0.0

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.mac)},
            connections={(CONNECTION_NETWORK_MAC, self.mac)},
            name=self.device_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=self.data.firmware,
        )

    async def _async_fetch(self, full: bool = False) -> PumpFuseState:
        # Most polls read only the two status endpoints. A full refresh also
        # re-checks the device identity and rereads learn and history.
        full = full or time.monotonic() >= self._next_full_refresh
        try:
            if full:
                info = await self.client.fetch_info()
                if info["mac"].lower() != self.mac:
                    raise UpdateFailed(
                        "The address now belongs to a different PumpFuse"
                    )
            state = await self.client.fetch(self.data, full)
        except PumpFuseError as err:
            self._next_full_refresh = 0.0
            raise UpdateFailed(str(err)) from err
        if full:
            self._next_full_refresh = time.monotonic() + FULL_REFRESH_INTERVAL
        return state

    async def _async_update_data(self) -> PumpFuseState:
        async with self._operation_lock:
            return await self._async_fetch()

    async def async_command(
        self,
        action: str,
        command: Command,
        expect: Callable[[PumpFuseState], bool] = lambda state: True,
    ) -> None:
        # Commands receive the latest state under the lock so bitmask writes
        # never race a concurrent change to the same mask.
        async with self._operation_lock:
            try:
                await command(self.client, self.data)
            except PumpFuseError as err:
                raise HomeAssistantError(f"Could not {action}: {err}") from err
            try:
                state = await self._async_fetch(full=True)
            except UpdateFailed as err:
                self.async_set_update_error(err)
                raise HomeAssistantError(
                    f"Could not verify {action}: {err}. "
                    "Check the pump monitor before retrying"
                ) from err
            self.async_set_updated_data(state)
            if not expect(state):
                raise HomeAssistantError(
                    f"The pump monitor accepted {action} but did not apply it"
                )


type PumpFuseConfigEntry = ConfigEntry[PumpFuseCoordinator]
