import logging
import asyncio
from custom_components.aria2.aria2_client import WSClient
from custom_components.aria2.aria2_commands import GetGlobalOption, UnauthorizedError

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
            secret = user_input[CONF_ACCESS_TOKEN] if CONF_ACCESS_TOKEN in user_input else None
            secure_socket = user_input[CONF_SERCURE_CONNECTION] if CONF_SERCURE_CONNECTION in user_input else False

            ws_client = WSClient(ws_url = ws_url(host, port, secure_socket), secret = secret, loop = self.hass.loop, retry_on_connection_error = False)

            try:
                await ws_client.call(GetGlobalOption())

                return self.async_create_entry(
                    title="aria 2 configuration",
                    data= {
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_ACCESS_TOKEN: secret,
                        CONF_SERCURE_CONNECTION: secure_socket
                    }
                )
            except (socket.gaierror, asyncio.exceptions.TimeoutError, ConnectionRefusedError, ConnectionResetError):
                _LOGGER.exception("connexion error")
                errors['base'] = 'invalid_url'
            except websockets.exceptions.InvalidStatusCode:
                _LOGGER.exception("server exists but is not aria2 server")
                errors['base'] = 'connexion'
            except UnauthorizedError:
                errors['base'] = 'aria_unauthorized'
            except:
                _LOGGER.exception("unknow error")
                errors['base'] = 'unknown'

        schema = {
            vol.Required(CONF_HOST, default = host or vol.UNDEFINED): str,
            vol.Optional(CONF_PORT, default = port or vol.UNDEFINED): int,
            vol.Optional(CONF_ACCESS_TOKEN, default = secret or vol.UNDEFINED): str,
            vol.Optional(CONF_SERCURE_CONNECTION, default = secure_socket or False): bool
        }

        return self.async_show_form(
            step_id='user', data_schema=vol.Schema(schema), errors=errors
        )
