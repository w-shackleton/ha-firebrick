"""Config flow for the FireBrick integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FirebrickAuthError, FirebrickClient, FirebrickError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, MIN_SCAN_INTERVAL
from .coordinator import FirebrickConfigEntry

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_VERIFY_SSL, default=True): bool,
    }
)
REAUTH_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)


async def _async_validate(hass: HomeAssistant, data: Mapping[str, Any]) -> str:
    """Check credentials and connectivity; return the unit serial number."""
    client = FirebrickClient(
        async_get_clientsession(hass, verify_ssl=data[CONF_VERIFY_SSL]),
        data[CONF_URL],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
    )
    serial = await client.async_get_serial()
    # Make sure every endpoint we poll is readable by this user.
    await client.async_get_status()
    return serial


def _normalise_url(url: str) -> str:
    url = url.strip().rstrip("/")
    return url if "://" in url else f"https://{url}"


class FirebrickConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FireBrick."""

    VERSION = 1

    async def _async_try(
        self, data: Mapping[str, Any], errors: dict[str, str]
    ) -> str | None:
        try:
            return await _async_validate(self.hass, data)
        except FirebrickAuthError:
            errors["base"] = "invalid_auth"
        except FirebrickError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error validating FireBrick")
            errors["base"] = "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_URL] = _normalise_url(user_input[CONF_URL])
            if serial := await self._async_try(user_input, errors):
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(
                    updates={CONF_URL: user_input[CONF_URL]}
                )
                return self.async_create_entry(
                    title=f"FireBrick {serial}", data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after the router rejected the credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            if serial := await self._async_try(data, errors):
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                REAUTH_SCHEMA, {CONF_USERNAME: entry.data[CONF_USERNAME]}
            ),
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: FirebrickConfigEntry,
    ) -> FirebrickOptionsFlow:
        """Return the options flow."""
        return FirebrickOptionsFlow()


class FirebrickOptionsFlow(OptionsFlowWithReload):
    """Polling interval option."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                }
            ),
        )
