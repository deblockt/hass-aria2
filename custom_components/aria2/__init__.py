from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any
import voluptuous as vol

from .aria2_client import WSClient
from .aria2_commands import (
    AddUri,
    AddTorrent,
    DownloadKeys,
    MultiCall,
    Pause,
    Remove,
    TellActive,
    TellStatus,
    TellStopped,
    TellWaiting,
    Unpause,
)

from .const import (
    CONF_SECURE_CONNECTION,
    DOMAIN,
    CONF_PORT,
    build_ws_url,
    COORDINATOR_FAST_UPDATE_SECONDS,
    COORDINATOR_SLOW_UPDATE_SECONDS,
    TIMEOUT_SECONDS,
    STATE_ACTIVE,
)
from homeassistant.const import CONF_HOST, CONF_ACCESS_TOKEN, Platform
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers import config_validation as cv

import aria2p

_LOGGER = logging.getLogger(__name__)

DOWNLOAD_DUMP_KEYS = [
    DownloadKeys.GID,
    DownloadKeys.FILES,
    DownloadKeys.STATUS,
    DownloadKeys.TOTAL_LENGTH,
    DownloadKeys.COMPLETED_LENGTH,
    DownloadKeys.DOWNLOAD_SPEED,
    DownloadKeys.DIR,
    DownloadKeys.BITTORRENT,
    DownloadKeys.SEEDER,
    DownloadKeys.UPLOAD_SPEED,
    DownloadKeys.UPLOADED_LENGTH,
    DownloadKeys.ERROR_CODE,
    DownloadKeys.ERROR_MESSAGE
]


def dump_files(files: list[aria2p.File]) -> list[dict[str, Any]]:
    """Convert aria2p File objects to dictionaries.

    Args:
        files: List of aria2p.File objects

    Returns:
        List of dictionaries with file information
    """
    return [
        {
            "path": f.path,
            "completed_length": f.completed_length,
            "index": f.index,
            "length": f.length,
        }
        for f in files
    ]


def dump(download: aria2p.Download) -> dict[str, Any]:
    """Convert an aria2p Download object to a dictionary.

    Args:
        download: aria2p.Download object

    Returns:
        Dictionary with download information
    """
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


async def async_setup_entry(hass, entry) -> bool:
    """Set up aria2 integration from a config entry.

    Args:
        hass: Home Assistant instance
        entry: ConfigEntry with aria2 server configuration

    Returns:
        True if setup was successful
    """
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = dict(entry.data)

    server_url = build_ws_url(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_SECURE_CONNECTION]
        if CONF_SECURE_CONNECTION in entry.data
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
                "list": [dump(d) for d in download_list_coordinator.data] if download_list_coordinator.data else [],
            },
        )
    )
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = download_list_coordinator

    register_services(hass)

    hass.loop.create_task(ws_client.listen_notifications())

    async def on_download_state_updated(gid: str, status: str) -> None:
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


async def async_unload_entry(hass, entry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: ConfigEntry being unloaded

    Returns:
        True if unload was successful
    """
    # Stop the coordinator first
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
        if coordinator:
            # Stop the coordinator from updating
            await coordinator.async_shutdown()

        # Close the WebSocket client
        ws_client = hass.data[DOMAIN][entry.entry_id].get("ws_client")
        if ws_client:
            # Stop listening for notifications
            ws = await ws_client.ws.get()
            if ws:
                await ws.close()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])

    # Remove data
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


def register_services(hass) -> None:
    """Register aria2 services in Home Assistant.

    Args:
        hass: Home Assistant instance
    """
    # Check if services are already registered
    if hass.services.has_service(DOMAIN, "start_download"):
        return

    def entry_exists(hass):
        """Return a voluptuous validator that checks the entry_id exists in hass.data[DOMAIN]."""
        def validator(value):
            entries = list(hass.data.get(DOMAIN, {}).keys())
            if value not in entries:
                raise vol.Invalid(
                    f"entry_id '{value}' unknown. Available entry_ids: {entries}."
                )
            return value
        return validator

    ADD_DOWNLOAD_SCHEMA = vol.Schema({
        vol.Required("url"): cv.string,
        vol.Required("server_entry_id"): entry_exists(hass),
    })
    REMOVE_DOWNLOAD_SCHEMA = vol.Schema({
        vol.Required("gid"): cv.string,
        vol.Required("server_entry_id"): entry_exists(hass),
    })
    PAUSE_DOWNLOAD_SCHEMA = vol.Schema({
        vol.Required("gid"): cv.string,
        vol.Required("server_entry_id"): entry_exists(hass),
    })
    RESUME_DOWNLOAD_SCHEMA = vol.Schema({
        vol.Required("gid"): cv.string,
        vol.Required("server_entry_id"): entry_exists(hass),
    })
    REFRESH_DOWNLOADS_SCHEMA = vol.Schema({
        vol.Required("server_entry_id"): entry_exists(hass),
    })
    
    async def handle_add_download(call) -> None:
        """Handle the service call."""
        url = call.data.get("url")
        entry_id = call.data.get("server_entry_id")
        if url.startswith(("http://", "https://", "ftp://", "magnet:")):
            await hass.data[DOMAIN][entry_id]["ws_client"].call(AddUri([url]))
        else:
            await hass.data[DOMAIN][entry_id]["ws_client"].call(AddTorrent(url))

    async def handle_remove_download(call) -> None:
        """Handle the service call."""
        gid = call.data.get("gid")
        entry_id = call.data.get("server_entry_id")
        await hass.data[DOMAIN][entry_id]["ws_client"].call(Remove(gid))
        await hass.data[DOMAIN][entry_id]["coordinator"].async_refresh()

    async def handle_pause_download(call) -> None:
        """Handle the service call."""
        gid = call.data.get("gid")
        entry_id = call.data.get("server_entry_id")
        await hass.data[DOMAIN][entry_id]["ws_client"].call(Pause(gid))

    async def handle_resume_download(call) -> None:
        """Handle the service call."""
        gid = call.data.get("gid")
        entry_id = call.data.get("server_entry_id")
        await hass.data[DOMAIN][entry_id]["ws_client"].call(Unpause(gid))

    async def handler_refresh_downloads(call) -> None:
        """Handle the service call."""
        entry_id = call.data.get("server_entry_id")
        await hass.data[DOMAIN][entry_id]["coordinator"].async_refresh()

    hass.services.async_register(DOMAIN, "start_download", handle_add_download, schema=ADD_DOWNLOAD_SCHEMA)
    hass.services.async_register(DOMAIN, "remove_download", handle_remove_download, schema=REMOVE_DOWNLOAD_SCHEMA)
    hass.services.async_register(DOMAIN, "pause_download", handle_pause_download, schema=PAUSE_DOWNLOAD_SCHEMA)
    hass.services.async_register(DOMAIN, "resume_download", handle_resume_download, schema=RESUME_DOWNLOAD_SCHEMA)
    hass.services.async_register(DOMAIN, "refresh_downloads", handler_refresh_downloads, schema=REFRESH_DOWNLOADS_SCHEMA)


def init_download_list_update_coordinator(hass, ws_client: WSClient) -> DataUpdateCoordinator:
    """Initialize the download list update coordinator.

    Args:
        hass: Home Assistant instance
        ws_client: WebSocket client for aria2

    Returns:
        DataUpdateCoordinator instance
    """
    async def get_downloads() -> list[aria2p.Download]:
        async with asyncio.timeout(TIMEOUT_SECONDS):
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

            active_downloads = [d for d in downloads if d.status == STATE_ACTIVE]
            if len(active_downloads) > 0:
                _LOGGER.debug("update the coordinator to refresh each %s seconds", COORDINATOR_FAST_UPDATE_SECONDS)
                coordinator.update_interval = timedelta(seconds=COORDINATOR_FAST_UPDATE_SECONDS)
            else:
                _LOGGER.debug("update the coordinator to refresh each %s seconds", COORDINATOR_SLOW_UPDATE_SECONDS)
                coordinator.update_interval = timedelta(seconds=COORDINATOR_SLOW_UPDATE_SECONDS)

            return downloads

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="download_list",
        update_method=get_downloads,
        update_interval=timedelta(seconds=COORDINATOR_FAST_UPDATE_SECONDS),
    )
    return coordinator
