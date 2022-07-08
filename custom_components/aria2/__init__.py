import logging

from custom_components.aria2.aria2_client import WSClient

from .const import DOMAIN, CONF_PORT
from homeassistant.const import CONF_HOST, CONF_ACCESS_TOKEN
from homeassistant.components import http
from homeassistant.core import callback
import websockets
import json
import aria2p

_LOGGER = logging.getLogger(__name__)


def dump(download):
    return {
        'name': download.name,
        'gid': download.gid,
        'status': download.status,
        'total_length': download.total_length,
        'completed_length': download.completed_length,
        'download_speed': download.download_speed,
    }

async def async_setup_entry(hass, entry):
    """ a aria sensor """
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = dict(entry.data)

    aria2 = aria2p.API(
        aria2p.Client(
            host = entry.data[CONF_HOST],
            port = entry.data[CONF_PORT],
            secret = entry.data[CONF_ACCESS_TOKEN]
        )
    )

    ws_client = WSClient(aria2, hass)

    hass.data[DOMAIN][entry.entry_id]['aria2_client'] = aria2
    hass.data[DOMAIN][entry.entry_id]['ws_client'] = ws_client
    hass.data[DOMAIN]['aria2_client'] = aria2

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, 'sensor')
    )

    def download_list_refreshed(downloads):
        hass.bus.fire('download_list_updated', {'list': [dump(d) for d in downloads]})

    ws_client.on_download_list_refreshed(download_list_refreshed)

    async def handle_add_download(call):
        """Handle the service call."""
        url = call.data.get('url')
        await ws_client.call_add_uri(url)

    async def handle_remove_download(call):
        """Handle the service call."""
        gid = call.data.get('gid')
        await ws_client.call_remove_download(gid)
        await ws_client.refresh_downloads()

    async def handle_pause_download(call):
        """Handle the service call."""
        gid = call.data.get('gid')
        await ws_client.call_pause_download(gid)

    async def handle_resume_download(call):
        """Handle the service call."""
        gid = call.data.get('gid')
        await ws_client.call_resume_download(gid)

    async def on_download_state_updated(gid, status):
        hass.bus.fire('download_state_updated', {'gid': gid, 'status': status})
        await ws_client.refresh_downloads()

    ws_client.on_download_state_updated(on_download_state_updated)

    hass.services.async_register(DOMAIN, 'start_download', handle_add_download)
    hass.services.async_register(DOMAIN, 'remove_download', handle_remove_download)
    hass.services.async_register(DOMAIN, 'pause_download', handle_pause_download)
    hass.services.async_register(DOMAIN, 'resume_download', handle_resume_download)

    hass.loop.create_task(ws_client.listen_notifications())

    return True
