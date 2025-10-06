import logging
import asyncio
from typing import Any

from custom_components.aria2.aria2_client import WSClient
from custom_components.aria2.aria2_commands import (
    ChangeGlobalOptions,
    GetGlobalOption,
    UnauthorizedError,
)

from homeassistant.helpers.selector import selector
from homeassistant import config_entries
from .const import CONF_SERCURE_CONNECTION, DOMAIN, CONF_PORT, ws_url

import voluptuous as vol

from homeassistant.const import CONF_HOST, CONF_ACCESS_TOKEN
import socket
import websockets

_LOGGER = logging.getLogger(__name__)


class Aria2ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        host = None
        port = None
        secret = None
        secure_socket = None
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT] if CONF_PORT in user_input else 6800
            secret = (
                user_input[CONF_ACCESS_TOKEN]
                if CONF_ACCESS_TOKEN in user_input
                else None
            )
            secure_socket = (
                user_input[CONF_SERCURE_CONNECTION]
                if CONF_SERCURE_CONNECTION in user_input
                else False
            )

            ws_client = WSClient(
                ws_url=ws_url(host, port, secure_socket),
                secret=secret,
                loop=self.hass.loop,
                retry_on_connection_error=False,
            )

            try:
                await ws_client.call(GetGlobalOption())

                return self.async_create_entry(
                    title="aria " + host + ":" + str(port),
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_ACCESS_TOKEN: secret,
                        CONF_SERCURE_CONNECTION: secure_socket,
                    },
                )
            except (
                socket.gaierror,
                asyncio.exceptions.TimeoutError,
                ConnectionRefusedError,
                ConnectionResetError,
            ):
                _LOGGER.exception("connexion error")
                errors["base"] = "invalid_url"
            except websockets.exceptions.InvalidStatusCode:
                _LOGGER.exception("server exists but is not aria2 server")
                errors["base"] = "connexion"
            except UnauthorizedError:
                errors["base"] = "aria_unauthorized"
            except:
                _LOGGER.exception("unknow error")
                errors["base"] = "unknown"

        schema = {
            vol.Required(CONF_HOST, default=host or vol.UNDEFINED): str,
            vol.Optional(CONF_PORT, default=port or vol.UNDEFINED): int,
            vol.Optional(CONF_ACCESS_TOKEN, default=secret or vol.UNDEFINED): str,
            vol.Optional(CONF_SERCURE_CONNECTION, default=secure_socket or False): bool,
        }

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(schema), errors=errors
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()


GLOBAL_OPTIONS = {
    "bt-max-open-files": int,
    "download-result": selector(
        {
            "select": {
                "options": ["default", "full", "hide"],
            }
        }
    ),
    "keep-unfinished-download-result": bool,
    "log": str,
    "log-level": selector(
        {
            "select": {
                "options": ["debug", "info", "notice", "warn", "error"],
            }
        }
    ),
    "max-concurrent-downloads": int,
    "max-download-result": int,
    "max-overall-download-limit": str,
    "max-overall-upload-limit": str,
    "optimize-concurrent-downloads": str,
    "save-cookies": str,
    "save-session": str,
    "server-stat-of": str,
}


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self) -> None:
        """Initialize options flow."""
        self.config_name = None

    async def async_step_init(self, user_input: dict[str, Any] = None):
        """Manage the options."""
        if user_input is not None and "option_to_update" in user_input:
            return await self.load_set_config_flow(user_input["option_to_update"])

        return self.load_config_list_flow()

    async def async_step_set_option(self, user_input: dict[str, Any] = None):
        """Manage the options."""
        if user_input is not None and "option_value" in user_input:
            return await self.update_option(user_input["option_value"])

        return self.load_config_list_flow()

    async def update_option(self, option_value: str):
        ws_client: WSClient = self.hass.data[DOMAIN][self._config_entry_id]["ws_client"]
        result = await ws_client.call(
            ChangeGlobalOptions({self.config_name: option_value})
        )

        if result:
            return self.async_abort(reason="config_successfuly_updated")
        else:
            return await self.load_set_config_flow(self.config_name, option_value)

    async def load_set_config_flow(self, config_name: str, previous_value: str = None):
        self.config_name = config_name
        ws_client: WSClient = self.hass.data[DOMAIN][self._config_entry_id]["ws_client"]
        options = await ws_client.call(GetGlobalOption())

        return self.async_show_form(
            step_id="set_option",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "option_value",
                        default=previous_value
                        if previous_value
                        else GLOBAL_OPTIONS[config_name](options.get(config_name)),
                    ): GLOBAL_OPTIONS[config_name],
                }
            ),
            errors={"option_value": "invalid_value"} if previous_value else None,
        )

    def load_config_list_flow(self):
        option_list = list(GLOBAL_OPTIONS.keys())
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "option_to_update",
                        default=option_list[0],
                    ): selector({"select": {"options": option_list}})
                }
            ),
        )
