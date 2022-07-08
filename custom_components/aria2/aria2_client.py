import asyncio
import inspect
import string
import websockets
import json
import logging

from aria2p.downloads import Download

_LOGGER = logging.getLogger(__name__)

class WSClient():

    def __init__(self, aria2_api, hass):
        self.aria2_api = aria2_api
        self.ws_url = aria2_api.client.ws_server
        self.hass = hass
        self.secret = aria2_api.client.secret
        self.ws = None
        self.is_opening_socket = False
        self.listeners = {
            'global_stat': [],
            'download_list_refreshed': [],
            'download_state_updated': []
        }
        self.waiting_opening_socket_futures = []
        self.downloads = []

    async def get_ws(self):
        if self.ws and self.ws.open:
            _LOGGER.debug("the websocket is already open reuse it")
            return self.ws
        elif not self.is_opening_socket:
            _LOGGER.debug("restart aria2 websocket")
            self.is_opening_socket = True
            try:
                self.ws = await websockets.connect(self.ws_url)
            except asyncio.exceptions.TimeoutError:
                self.is_opening_socket = False
                return await self.get_ws()

            self.is_opening_socket = False
            for future in self.waiting_opening_socket_futures:
                _LOGGER.debug("call websocket waiting future")
                future.set_result(self.ws)
            self.waiting_opening_socket_futures = []
            return self.ws
        else:
            _LOGGER.info("waiting for websocket connected before continue")
            ws_future = self.hass.loop.create_future()
            self.waiting_opening_socket_futures.append(ws_future)
            return await ws_future

    def on_global_stat(self, listener):
        self.listeners['global_stat'].append(listener)

    def on_download_list_refreshed(self, listener):
        self.listeners['download_list_refreshed'].append(listener)

    def on_download_state_updated(self, listener):
        self.listeners['download_state_updated'].append(listener)

    async def call_global_stat(self):
        _LOGGER.debug("resfresh global stats")
        await (await self.get_ws()).send(json.dumps({
            'jsonrpc': '2.0',
            'method': 'aria2.getGlobalStat',
            'id': '1',
            'params': ["token:" + self.secret]
        }))

    async def call_resume_download(self, gid):
        await (await self.get_ws()).send(json.dumps({
            'jsonrpc': '2.0',
            'method': 'aria2.unpause',
            'id': '5',
            'params': ["token:" + self.secret, gid]
        }))

    async def call_pause_download(self, gid):
        await (await self.get_ws()).send(json.dumps({
            'jsonrpc': '2.0',
            'method': 'aria2.pause',
            'id': '5',
            'params': ["token:" + self.secret, gid]
        }))

    async def call_remove_download(self, gid):
        await (await self.get_ws()).send(json.dumps({
            'jsonrpc': '2.0',
            'method': 'aria2.remove',
            'id': '5',
            'params': ["token:" + self.secret, gid]
        }))

    async def refresh_downloads(self):
        _LOGGER.debug("resfresh downloads")
        ws = await self.get_ws()
        await ws.send(json.dumps({
            'jsonrpc': '2.0',
            'method': 'system.multicall',
            'id': '10',
            'params': [[
                {'methodName': 'aria2.tellActive', 'params': ["token:" + self.secret]},
                {'methodName': 'aria2.tellWaiting', 'params': ["token:" + self.secret, 0, 1000]},
                {'methodName': 'aria2.tellStopped', 'params': ["token:" + self.secret, 0, 1000]}
            ]]
        }))

    async def call_add_uri(self, uri):
        await (await self.get_ws()).send(json.dumps({
            'jsonrpc': '2.0',
            'method': 'aria2.addUri',
            'id': '5',
            'params': ["token:" + self.secret, [uri]]
        }))

    async def call_listeners(self, name: string, args: list):
        for listener in self.listeners[name]:
            if inspect.iscoroutinefunction(listener):
                await listener(*args)
            else:
                listener(*args)

    async def listen_notifications(self):
        while True:
            try:
                _LOGGER.debug('starting refresh loop')
                websocket = await self.get_ws()
                _LOGGER.debug('refresh loop have a websocket')
                async for message in websocket:
                    _LOGGER.debug('message received ' + message)
                    json_message = json.loads(message)
                    if 'method' in json_message:
                        action = json_message['method']
                        gid = json_message['params'][0]['gid']

                        status_mapping = {
                            'aria2.onDownloadStart': 'active',
                            'aria2.onDownloadPause': 'paused',
                            'aria2.onDownloadStop': 'stoped',
                            'aria2.onDownloadComplete': 'complete',
                            'aria2.onDownloadError': 'error'
                        }

                        if action in status_mapping:
                            status = status_mapping[action]
                            await self.call_listeners('download_state_updated', [gid, status])
                        else:
                            _LOGGER.info('unsuported aria method ' + action)
                    elif 'result' in json_message and isinstance(json_message['result'], list):
                        if json_message['id'] == '10':
                            downloads_json = []
                            downloads_json.extend(json_message['result'][0][0])
                            downloads_json.extend(json_message['result'][1][0])
                            downloads_json.extend(json_message['result'][2][0])

                            self.downloads = [Download(self.aria2_api, struct) for struct in downloads_json]
                            await self.call_listeners('download_list_refreshed', [self.downloads])

                    elif 'result' in json_message and 'downloadSpeed' in json_message['result']:
                        state = Stats(json_message['result'])
                        _LOGGER.debug('global state received' + str(json_message['result']))
                        await self.call_listeners('global_stat', [state])
            except asyncio.CancelledError:
                _LOGGER.info('the asyncio is cancelled. stop to listen aria2 state update.')
                await websocket.close()
                break
            except:
                _LOGGER.exception('error on aria2 websocket. restart it. wait 3 seoncds before restart')
                await asyncio.sleep(3)
                _LOGGER.debug('after 3 second of wait.')

        _LOGGER.info("End of listen notification")


class Stats:
    """This class holds information retrieved with the `get_global_stat` method of the client."""

    def __init__(self, struct: dict) -> None:
        """
        Initialize the object.

        Arguments:
            struct: A dictionary Python object returned by the JSON-RPC client.
        """
        self._struct = struct or {}

    @property
    def download_speed(self) -> int:
        """
        Overall download speed (byte/sec).

        Returns:
            The overall download speed in bytes per second.
        """
        return int(self._struct["downloadSpeed"])

    def download_speed_string(self, human_readable: bool = True) -> str:
        """
        Return the download speed as string.

        Arguments:
            human_readable: Return in human readable format or not.

        Returns:
            The download speed string.
        """
        return str(self.download_speed) + " B/s"

    @property
    def upload_speed(self) -> int:
        """
        Overall upload speed (byte/sec).

        Returns:
            The overall upload speed in bytes per second.
        """
        return int(self._struct["uploadSpeed"])

    def upload_speed_string(self, human_readable: bool = True) -> str:
        """
        Return the upload speed as string.

        Arguments:
            human_readable: Return in human readable format or not.

        Returns:
            The upload speed string.
        """
        return str(self.upload_speed) + " B/s"

    @property
    def num_active(self) -> int:
        """
        Return the number of active downloads.

        Returns:
            The number of active downloads.
        """
        return int(self._struct["numActive"])

    @property
    def num_waiting(self) -> int:
        """
        Return the number of waiting downloads.

        Returns:
            The number of waiting downloads.
        """
        return int(self._struct["numWaiting"])

    @property
    def num_stopped(self) -> int:
        """
        Return the number of stopped downloads in the current session.

        This value is capped by the [`--max-download-result`][aria2p.options.Options.max_download_result] option.

        Returns:
            The number of stopped downloads in the current session (capped).
        """
        return int(self._struct["numStopped"])

    @property
    def num_stopped_total(self) -> int:
        """
        Return the number of stopped downloads in the current session.

        This value is not capped by the [`--max-download-result`][aria2p.options.Options.max_download_result] option.

        Returns:
            The number of stopped downloads in the current session (not capped).
        """
        return int(self._struct["numStoppedTotal"])
