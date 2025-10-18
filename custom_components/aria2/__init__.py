from datetime import timedelta
import logging
from typing import List

from custom_components.aria2.aria2_client import WSClient
from custom_components.aria2.aria2_commands import (
    AddUri,
    AddTorrent,
    DownoladKeys,
    MultiCall,
    Pause,
    Remove,
    TellActive,
    TellStatus,
    TellStopped,
    TellWaiting,
    Unpause,
)

from .const import CONF_SERCURE_CONNECTION, DOMAIN, CONF_PORT, ws_url
from homeassistant.const import CONF_HOST, CONF_ACCESS_TOKEN, Platform
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)
from homeassistant.helpers.device_registry import DeviceEntryType

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
    DownoladKeys.DIR,
    DownoladKeys.BITTORENT,
    DownoladKeys.SEEDER,
    DownoladKeys.UPLOAD_SPEED,
    DownoladKeys.UPLOADED_LENGTH,
    DownoladKeys.ERROR_CODE,
    DownoladKeys.ERROR_MESSAGE
]


def dump_files(files: list[aria2p.File]):
    return [
        {
            "path": f.path,
            "completed_length": f.completed_length,
            "index": f.index,
            "length": f.length,
        }
        for f in files
    ]


def dump(download: aria2p.Download):
    data = {
        "name": download.name,
        "gid": download.gid,
        "status": download.status,
        "total_length": download.total_length,
        "completed_length": download.completed_length,
        "download_speed": download.download_speed,
        "files": dump_files(download.files),
        "is_torrent": download.is_torrent,
        "error_code": download.error_code,
        "error_message": download.error_message
    }

    if download.is_torrent:
        data.update(
            {
                "seeder": download.seeder,
                "upload_length": download.upload_length,
                "upload_speed": download.upload_speed,
            }
        )

    return data


async def async_setup_entry(hass, entry):
    """a aria sensor"""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = dict(entry.data)

    server_url = ws_url(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_SERCURE_CONNECTION]
        if CONF_SERCURE_CONNECTION in entry.data
        else False,
    )
    ws_client = WSClient(
        ws_url=server_url, secret=entry.data[CONF_ACCESS_TOKEN], loop=hass.loop
    )

    hass.data[DOMAIN][entry.entry_id]["ws_client"] = ws_client
    hass.data[DOMAIN][entry.entry_id]["service_attributes"] = {
        "identifiers": {(DOMAIN, server_url)},
        "manufacturer": "Aria2",
        "name": "Aria2",
        "entry_type": DeviceEntryType.SERVICE,
    }

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    )

    download_list_coordinator = init_download_list_update_coordinator(hass, ws_client)
    download_list_coordinator.async_add_listener(
        lambda: hass.bus.fire(
            "download_list_updated",
            {
                "server_entry_id": entry.entry_id,
                "list": [dump(d) for d in download_list_coordinator.data],
            },
        )
    )
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = download_list_coordinator

    register_services(hass)

    hass.loop.create_task(ws_client.listen_notifications())

    async def on_download_state_updated(gid, status):
        await download_list_coordinator.async_refresh()
        download = await ws_client.call(TellStatus(gid, DOWNLOAD_DUMP_KEYS))

        hass.bus.fire(
            "download_state_updated",
            {
                "server_entry_id": entry.entry_id,
                "gid": gid,
                "status": status,
                "download": dump(download),
            },
        )

    ws_client.on_download_state_updated(on_download_state_updated)

    return True


def register_services(hass):
    async def handle_add_download(call):
        """Handle the service call."""
        url = call.data.get("url")
        entry_id = call.data.get("server_entry_id")
        if url.startswith("http"):
            await hass.data[DOMAIN][entry_id]["ws_client"].call(AddUri([url]))
        else:
            await hass.data[DOMAIN][entry_id]["ws_client"].call(AddTorrent(url))

    async def handle_remove_download(call):
        """Handle the service call."""
        gid = call.data.get("gid")
        entry_id = call.data.get("server_entry_id")
        await hass.data[DOMAIN][entry_id]["ws_client"].call(Remove(gid))
        await hass.data[DOMAIN][entry_id]["coordinator"].async_refresh()

    async def handle_pause_download(call):
        """Handle the service call."""
        gid = call.data.get("gid")
        entry_id = call.data.get("server_entry_id")
        await hass.data[DOMAIN][entry_id]["ws_client"].call(Pause(gid))

    async def handle_resume_download(call):
        """Handle the service call."""
        gid = call.data.get("gid")
        entry_id = call.data.get("server_entry_id")
        await hass.data[DOMAIN][entry_id]["ws_client"].call(Unpause(gid))

    async def handler_refresh_downloads(call):
        entry_id = call.data.get("server_entry_id")
        await hass.data[DOMAIN][entry_id]["coordinator"].async_refresh()

    hass.services.async_register(DOMAIN, "start_download", handle_add_download)
    hass.services.async_register(DOMAIN, "remove_download", handle_remove_download)
    hass.services.async_register(DOMAIN, "pause_download", handle_pause_download)
    hass.services.async_register(DOMAIN, "resume_download", handle_resume_download)
    hass.services.async_register(DOMAIN, "refresh_downloads", handler_refresh_downloads)


def init_download_list_update_coordinator(hass, ws_client):
    async def get_downloads() -> List[aria2p.Download]:
        async with async_timeout.timeout(10):
            [active, waiting, stopped] = await ws_client.call(
                MultiCall(
                    [
                        TellActive(keys=DOWNLOAD_DUMP_KEYS),
                        TellWaiting(keys=DOWNLOAD_DUMP_KEYS),
                        TellStopped(keys=DOWNLOAD_DUMP_KEYS),
                    ]
                )
            )

            downloads = [*active, *waiting, *stopped]

            active_downloads = [d for d in downloads if d.status == "active"]
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
