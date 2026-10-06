from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .api import (
    PumpFuseClient,
    PumpFuseError,
    PumpFuseIdentity,
    UnsupportedModel,
    validate_host,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, MODEL


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=2, max=3600)),
        }
    )


class PumpFuseConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    async def _probe(self, host: str) -> PumpFuseIdentity:
        client = PumpFuseClient(async_get_clientsession(self.hass), host)
        return await client.fetch_identity()

    async def _configure(
        self, step: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry() if step == "reconfigure" else None
        defaults = dict(entry.data) if entry else {}
        errors = {}
        if user_input is not None:
            defaults.update(user_input)
            try:
                data = dict(user_input)
                data[CONF_HOST] = validate_host(data[CONF_HOST])
                identity = await self._probe(data[CONF_HOST])
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
            except UnsupportedModel:
                errors["base"] = "unsupported_model"
            except PumpFuseError:
                errors["base"] = "cannot_connect"
            else:
                data[CONF_NAME] = identity.name or MODEL
                if entry is not None:
                    if identity.mac != entry.unique_id:
                        return self.async_abort(reason="wrong_device")
                    return self.async_update_reload_and_abort(entry, data_updates=data)
                await self.async_set_unique_id(identity.mac)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data[CONF_NAME], data=data)
        return self.async_show_form(
            step_id=step, data_schema=_schema(defaults), errors=errors
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._configure("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._configure("reconfigure", user_input)

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        host = discovery_info.ip
        try:
            identity = await self._probe(host)
        except UnsupportedModel:
            return self.async_abort(reason="not_supported")
        except PumpFuseError:
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(identity.mac)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        name = identity.name or MODEL
        self._discovered = {
            CONF_HOST: host,
            CONF_NAME: name,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        }
        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        name = self._discovered[CONF_NAME]
        if user_input is not None:
            return self.async_create_entry(title=name, data=self._discovered)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "name": name,
                "host": self._discovered[CONF_HOST],
            },
        )
