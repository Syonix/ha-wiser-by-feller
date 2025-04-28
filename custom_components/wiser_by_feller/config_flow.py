"""Config flow for Wiser by Feller integration."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp.client_exceptions import ClientError
from aiowiserbyfeller import Auth, AuthorizationFailed, WiserByFellerAPI
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import dhcp
from homeassistant.const import CONF_HOST, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_USER,
    CONF_IMPORTUSER,
    DEFAULT_IMPORT_USER,
    DOMAIN,
    OPTIONS_ALLOW_MISSING_GATEWAY_DATA,
)
from .exceptions import CannotConnect, InvalidAuth

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME, default=API_USER): cv.string,
        vol.Required(CONF_IMPORTUSER, default=DEFAULT_IMPORT_USER): cv.string,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(OPTIONS_ALLOW_MISSING_GATEWAY_DATA, default=False): bool,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wiser by Feller."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await self.validate_input(self.hass, user_input)
                await self.async_set_unique_id(info["sn"])
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=info)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_dhcp(self, discovery_info: dhcp.DhcpServiceInfo) -> FlowResult:
        """Handle a flow initialized by discovery."""
        try:
            session = async_get_clientsession(self.hass)
            auth = Auth(session, discovery_info.ip)
            api = WiserByFellerAPI(auth)
            info = await api.async_get_info()
        except Exception:  # pylint: disable=broad-except
            return self.async_abort(reason="not_wiser_gateway")

        await self.async_set_unique_id(info["sn"])
        self._abort_if_unique_id_configured({CONF_HOST: discovery_info.ip})
        self._async_abort_entries_match({CONF_HOST: discovery_info.ip})

        self._discovered_host = discovery_info.ip

        return await self.async_step_confirm()

    async def validate_input(
        self, hass: HomeAssistant, user_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate user input for µGateway setup."""
        session = async_get_clientsession(hass)
        auth = Auth(session, user_input["host"])
        api = WiserByFellerAPI(auth)
        info = await api.async_get_info()

        await self.async_set_unique_id(info["sn"])
        self._abort_if_unique_id_configured({CONF_HOST: user_input["host"]})
        self._async_abort_entries_match({CONF_HOST: user_input["host"]})

        try:
            token = await auth.claim(
                user_input[CONF_USERNAME], user_input[CONF_IMPORTUSER]
            )
        except AuthorizationFailed as err:
            raise CannotConnect from err
        except ClientError as err:
            raise CannotConnect from err

        net_state = await api.async_get_net_state()

        return {
            "title": net_state["hostname"],
            "token": token,
            "sn": info["sn"],
            "host": user_input["host"],
            "user": API_USER,
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handles options flow for the component."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
