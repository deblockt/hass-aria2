import logging

from .const import DOMAIN, CONF_PORT
from homeassistant.const import CONF_HOST, CONF_ACCESS_TOKEN
from homeassistant.components import http
from homeassistant.core import callback

import aria2p

_LOGGER = logging.getLogger(__name__)

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

    hass.data[DOMAIN][entry.entry_id]['aria2_client'] = aria2
    hass.data[DOMAIN]['aria2_client'] = aria2

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, 'sensor')
    )

    def handle_add_download(call):
        """Handle the service call."""
        url = call.data.get('url')
        aria2.add(url)

    def handle_remove_download(call):
        """Handle the service call."""
        gid = call.data.get('gid')
        download = aria2.get_download(gid)
        aria2.remove([download])

    def handle_pause_download(call):
        """Handle the service call."""
        gid = call.data.get('gid')
        download = aria2.get_download(gid)
        aria2.pause([download])

    def handle_resume_download(call):
        """Handle the service call."""
        gid = call.data.get('gid')
        download = aria2.get_download(gid)
        aria2.resume([download])

    hass.services.async_register(DOMAIN, 'start_download', handle_add_download)
    hass.services.async_register(DOMAIN, 'remove_download', handle_remove_download)
    hass.services.async_register(DOMAIN, 'pause_download', handle_pause_download)
    hass.services.async_register(DOMAIN, 'resume_download', handle_resume_download)

    hass.http.register_view(DisplayDownloadsView(hass, aria2))

    def listen_notifications():
        aria2.listen_to_notifications(
            threaded = True,
            on_download_start = lambda api_client, gid: hass.bus.fire('download_state_updated', {'gid': gid, 'status': 'active'}),
            on_download_pause = lambda api_client, gid: hass.bus.fire('download_state_updated', {'gid': gid, 'status': 'paused'}),
            on_download_stop = lambda api_client, gid: hass.bus.fire('download_state_updated', {'gid': gid, 'status': 'stoped'}),
            on_download_complete = lambda api_client, gid: hass.bus.fire('download_state_updated', {'gid': gid, 'status': 'complete'}),
            on_download_error = lambda api_client, gid: hass.bus.fire('download_state_updated', {'gid': gid, 'status': 'error'})
        )

    listen_notifications()

    return True


class DisplayDownloadsView(http.HomeAssistantView):
    """View to retrieve download list."""

    def __init__(self, hass, aria2_client):
        self._aria_client = aria2_client
        self._hass = hass

    url = "/api/aria_download_list"
    name = "api:aria_download_list"

    def dump(self, download):
        return {
            'name': download.name,
            'gid': download.gid,
            'status': download.status,
            'total_length': download.total_length,
            'completed_length': download.completed_length,
            'download_speed': download.download_speed,
        }

    @callback
    async def get(self, request):
        """Retrieve shopping list items."""
        downloads = [self.dump(download) for download in await self._hass.async_add_executor_job(self._aria_client.get_downloads)]
        return self.json(downloads)