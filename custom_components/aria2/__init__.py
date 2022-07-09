import asyncio
from datetime import timedelta
import logging
from typing import List

from custom_components.aria2.aria2_client import WSClient
from custom_components.aria2.aria2_commands import AddUri, DownoladKeys, MultiCall, Pause, Remove, TellActive, TellStopped, TellWaiting, Unpause

from .const import DOMAIN, CONF_PORT
from homeassistant.const import CONF_HOST, CONF_ACCESS_TOKEN
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)
import aria2p
import async_timeout

_LOGGER = logging.getLogger(__name__)

DOWNLOAD_DUMP_KEYS = [
    DownoladKeys.GID,
    DownoladKeys.FILES,
    DownoladKeys.STATUS,
    DownoladKeys.TOTAL_LENGTH,
    DownoladKeys.COMPLETED_LENGTH,
    DownoladKeys.DOWNLOAD_SPEED,
    DownoladKeys.DIR
]
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

    ws_client = WSClient(aria2, hass.loop)

    hass.data[DOMAIN][entry.entry_id]['aria2_client'] = aria2
    hass.data[DOMAIN][entry.entry_id]['ws_client'] = ws_client
    hass.data[DOMAIN]['aria2_client'] = aria2

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, 'sensor')
    )

    async def handle_add_download(call):
        """Handle the service call."""
        url = call.data.get('url')
        await ws_client.call(AddUri([url]))

    async def handle_remove_download(call):
        """Handle the service call."""
        gid = call.data.get('gid')
        await ws_client.call(Remove(gid))
        await download_list_coordinator.async_refresh()

    async def handle_pause_download(call):
        """Handle the service call."""
        gid = call.data.get('gid')
        await ws_client.call(Pause(gid))

    async def handle_resume_download(call):
        """Handle the service call."""
        gid = call.data.get('gid')
        await ws_client.call(Unpause(gid))

    async def handler_refresh_downloads(call):
        await download_list_coordinator.async_refresh()

    hass.services.async_register(DOMAIN, 'start_download', handle_add_download)
    hass.services.async_register(DOMAIN, 'remove_download', handle_remove_download)
    hass.services.async_register(DOMAIN, 'pause_download', handle_pause_download)
    hass.services.async_register(DOMAIN, 'resume_download', handle_resume_download)
    hass.services.async_register(DOMAIN, 'refresh_downloads', handler_refresh_downloads)

    hass.loop.create_task(ws_client.listen_notifications())

    async def on_download_state_updated(gid, status):
        hass.bus.fire('download_state_updated', {'gid': gid, 'status': status})
        await download_list_coordinator.async_refresh()
    ws_client.on_download_state_updated(on_download_state_updated)

    download_list_coordinator = init_download_list_update_coordinator()
    download_list_coordinator.async_add_listener(lambda: hass.bus.fire('download_list_updated', {'list': [dump(d) for d in download_list_coordinator.data]}))

    return True

def init_download_list_update_coordinator(hass, ws_client):
    async def get_downloads() -> List[aria2p.Download]:
        async with async_timeout.timeout(10):
            [active, waiting, stopped] = await ws_client.call(MultiCall([
                TellActive(keys = DOWNLOAD_DUMP_KEYS),
                TellWaiting(keys = DOWNLOAD_DUMP_KEYS),
                TellStopped(keys = DOWNLOAD_DUMP_KEYS)
            ]))

            downloads = [*active, *waiting, *stopped]

            active_downloads = [d for d in downloads if d.status == 'active']
            if len(active_downloads) > 0:
                _LOGGER.debug("update the coordinator to refresh each 3 seconds")
                coordinator.update_interval = timedelta(seconds=3)
            else:
                _LOGGER.debug("update the coordinator to refresh each 30 seconds")
                coordinator.update_interval = timedelta(seconds=30)

            return downloads

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="download_list",
        update_method=get_downloads,
        update_interval=timedelta(seconds=3),
    )
    return coordinator