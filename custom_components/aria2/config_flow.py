import logging
import asyncio
from typing import Any
import socket

import voluptuous as vol
import websockets

from homeassistant.helpers.selector import selector
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_ACCESS_TOKEN

from .aria2_client import WSClient
from .aria2_commands import (
    ChangeGlobalOptions,
    GetGlobalOption,
    AriaError,
)
from .const import CONF_SECURE_CONNECTION, DOMAIN, CONF_PORT, build_ws_url

_LOGGER = logging.getLogger(__name__)


class Aria2ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for aria2 integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step of the config flow.

        Args:
            user_input: User provided configuration data

        Returns:
            Config flow result
        """
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
                user_input[CONF_SECURE_CONNECTION]
                if CONF_SECURE_CONNECTION in user_input
                else False
            )

            ws_client = WSClient(
                ws_url=build_ws_url(host, port, secure_socket),
                secret=secret,
                loop=self.hass.loop,
                retry_on_connection_error=False,
            )

            try:
                await ws_client.call(GetGlobalOption())

                return self.async_create_entry(
                    title=f"aria {host}:{port}",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_ACCESS_TOKEN: secret,
                        CONF_SECURE_CONNECTION: secure_socket,
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
            except AriaError:
                errors["base"] = "aria_unauthorized"
            except:
                _LOGGER.exception("unknown error")
                errors["base"] = "unknown"

        schema = {
            vol.Required(CONF_HOST, default=host or vol.UNDEFINED): str,
            vol.Optional(CONF_PORT, default=port or vol.UNDEFINED): int,
            vol.Optional(CONF_ACCESS_TOKEN, default=secret or vol.UNDEFINED): str,
            vol.Optional(CONF_SECURE_CONNECTION, default=secure_socket or False): bool,
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
    # Connection options
    "all-proxy": str,
    "all-proxy-passwd": str,
    "all-proxy-user": str,
    "connect-timeout": str,  # Seconds (numeric with unit support)
    "dry-run": bool,
    "lowest-speed-limit": str,  # Speed with K/M support
    "max-connection-per-server": str,  # Count
    "max-download-limit": str,  # Speed with K/M support
    "max-tries": str,  # Count
    "max-upload-limit": str,  # Speed with K/M support
    "min-split-size": str,  # Byte size with K/M support
    "no-netrc": bool,
    "no-proxy": str,
    "proxy-method": selector(
        {
            "select": {
                "options": ["get", "tunnel"],
            }
        }
    ),
    "remote-time": bool,
    "reuse-uri": bool,
    "retry-wait": str,  # Seconds
    "server-stat-of": str,
    "split": str,  # Count
    "timeout": str,  # Seconds
    "uri-selector": selector(
        {
            "select": {
                "options": ["inorder", "feedback", "adaptive"],
            }
        }
    ),

    # HTTP/HTTPS/FTP options
    "conditional-get": bool,
    "content-disposition-default-utf8": bool,
    "continue": bool,
    "enable-http-keep-alive": bool,
    "enable-http-pipelining": bool,
    "follow-metalink": selector(
        {
            "select": {
                "options": ["true", "false", "mem"],
            }
        }
    ),
    "follow-torrent": selector(
        {
            "select": {
                "options": ["true", "false", "mem"],
            }
        }
    ),
    "ftp-passwd": str,
    "ftp-pasv": bool,
    "ftp-proxy": str,
    "ftp-proxy-passwd": str,
    "ftp-proxy-user": str,
    "ftp-reuse-connection": bool,
    "ftp-type": selector(
        {
            "select": {
                "options": ["binary", "ascii"],
            }
        }
    ),
    "ftp-user": str,
    "header": str,
    "http-accept-gzip": bool,
    "http-auth-challenge": bool,
    "http-no-cache": bool,
    "http-passwd": str,
    "http-proxy": str,
    "http-proxy-passwd": str,
    "http-proxy-user": str,
    "http-user": str,
    "https-proxy": str,
    "https-proxy-passwd": str,
    "https-proxy-user": str,
    "referer": str,
    "use-head": bool,
    "user-agent": str,

    # BitTorrent/Metalink options
    "bt-enable-hook-after-hash-check": bool,
    "bt-enable-lpd": bool,
    "bt-exclude-tracker": str,
    "bt-external-ip": str,
    "bt-force-encryption": bool,
    "bt-hash-check-seed": bool,
    "bt-load-saved-metadata": bool,
    "bt-max-open-files": str,  # Count
    "bt-max-peers": str,  # Count
    "bt-metadata-only": bool,
    "bt-min-crypto-level": selector(
        {
            "select": {
                "options": ["plain", "arc4"],
            }
        }
    ),
    "bt-prioritize-piece": str,
    "bt-remove-unselected-file": bool,
    "bt-request-peer-speed-limit": str,  # Speed with K/M support
    "bt-require-crypto": bool,
    "bt-save-metadata": bool,
    "bt-seed-unverified": bool,
    "bt-stop-timeout": str,  # Seconds
    "bt-tracker": str,
    "bt-tracker-connect-timeout": str,  # Seconds
    "bt-tracker-interval": str,  # Seconds
    "bt-tracker-timeout": str,  # Seconds
    "enable-peer-exchange": bool,
    "metalink-base-uri": str,
    "metalink-enable-unique-protocol": bool,
    "metalink-language": str,
    "metalink-location": str,
    "metalink-os": str,
    "metalink-preferred-protocol": selector(
        {
            "select": {
                "options": ["http", "https", "ftp", "none"],
            }
        }
    ),
    "metalink-version": str,
    "seed-ratio": str,  # Decimal ratio
    "seed-time": str,  # Minutes

    # Advanced options
    "allow-overwrite": bool,
    "allow-piece-length-change": bool,
    "always-resume": bool,
    "async-dns": bool,
    "auto-file-renaming": bool,
    "check-integrity": bool,
    "dir": str,
    "download-result": selector(
        {
            "select": {
                "options": ["default", "full", "hide"],
            }
        }
    ),
    "enable-mmap": bool,
    "file-allocation": selector(
        {
            "select": {
                "options": ["none", "prealloc", "trunc", "falloc"],
            }
        }
    ),
    "force-save": bool,
    "gid": str,
    "hash-check-only": bool,
    "keep-unfinished-download-result": bool,
    "log": str,
    "log-level": selector(
        {
            "select": {
                "options": ["debug", "info", "notice", "warn", "error"],
            }
        }
    ),
    "max-concurrent-downloads": str,  # Count
    "max-download-result": str,  # Count
    "max-file-not-found": str,  # Count
    "max-mmap-limit": str,  # Byte size with K/M support
    "max-overall-download-limit": str,  # Speed with K/M support
    "max-overall-upload-limit": str,  # Speed with K/M support
    "max-resume-failure-tries": str,  # Count
    "no-file-allocation-limit": str,  # Byte size with K/M support
    "optimize-concurrent-downloads": str,
    "parameterized-uri": bool,
    "pause-metadata": bool,
    "piece-length": str,  # Byte size with K/M support
    "realtime-chunk-checksum": bool,
    "remove-control-file": bool,
    "rpc-save-upload-metadata": bool,
    "save-cookies": str,
    "save-session": str,
    "ssh-host-key-md": str,
    "stream-piece-selector": selector(
        {
            "select": {
                "options": ["default", "inorder", "random", "geom"],
            }
        }
    ),
}


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for aria2 integration.

    Allows users to modify aria2 global options through the UI.
    """

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
