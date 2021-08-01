from homeassistant import config_entries
from .const import DOMAIN, CONF_PORT

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_ACCESS_TOKEN

import aria2p
import traceback

def get_port(host):
    if host.startswith('http'):
        return 80
    else:
        return 443

class Aria2ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        host = None
        port = None
        secret = None
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT] if CONF_PORT in user_input else get_port(user_input[CONF_HOST])
            secret = user_input[CONF_ACCESS_TOKEN] if CONF_ACCESS_TOKEN in user_input else None

            aria2 = aria2p.API(
                aria2p.Client(
                    host = host,
                    port = port,
                    secret = secret
                )
            )

            try:
                await self.hass.async_add_executor_job(lambda: aria2.get_global_options())

                return self.async_create_entry(
                    title="aria 2 configuration",
                    data= {
                        CONF_HOST:  host,
                        CONF_PORT: port,
                        CONF_ACCESS_TOKEN: secret
                    }
                )
            except:
                traceback.print_exc()
                errors['base'] = 'connexion'

        schema = {
            vol.Required(CONF_HOST, default = host): str,
            vol.Optional(CONF_PORT, default = port): str,
            vol.Optional(CONF_ACCESS_TOKEN, default = secret): str
        }

        return self.async_show_form(
            step_id='user', data_schema=vol.Schema(schema), errors=errors
        )
