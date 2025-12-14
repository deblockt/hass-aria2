import asyncio
import inspect
from typing import TypeVar

from aria2p import API
from custom_components.aria2.aria2_commands import Command
from custom_components.aria2.const import WS_RETRY_DELAY_SECONDS
import websockets
import json
import logging

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


class WSClient:
    """WebSocket client for aria2 RPC communication.

    Manages WebSocket connections and handles aria2 JSON-RPC commands
    with automatic retry on connection errors.
    """

    def __init__(self, ws_url: str, loop: asyncio.AbstractEventLoop, secret: str = None, retry_on_connection_error: bool = True):
        """Initialize the WebSocket client.

        Args:
            ws_url: WebSocket URL for aria2 server
            loop: Asyncio event loop
            secret: Optional authentication token
            retry_on_connection_error: Whether to retry on connection errors
        """
        self.loop = loop
        self.secret = secret
        self.ws = SharableWebsocket(ws_url, loop, retry_on_connection_error)
        self.notification_listeners = []
        self.running_command = dict()
        self.is_websocket_listener_started = False

    def on_download_state_updated(self, listener):
        """Register a listener for download state update notifications.

        Args:
            listener: Callback function to be called when download state changes
        """
        self.notification_listeners.append(listener)

    async def call(self, command: Command[T]) -> T:
        """Execute an aria2 RPC command.

        Args:
            command: The Command object to execute

        Returns:
            The result of the command execution
        """
        listen_task = None
        if not self.is_websocket_listener_started:
            listen_task = self.loop.create_task(self.listen_notifications())

        ws = await self.ws.get()
        future = command.build_awaitable_future(self.loop)
        self.running_command[str(command.id)] = command

        json_command = command.to_json(self.secret)
        _LOGGER.debug('send command %s', json_command)
        await ws.send(json.dumps(json_command))

        try:
            result = await future
            return result
        finally:
            if listen_task:
                listen_task.cancel()


    async def call_notification_listeners(self, args: list):
        """Call all registered notification listeners.

        Args:
            args: Arguments to pass to the listener callbacks
        """
        for listener in self.notification_listeners:
            if inspect.iscoroutinefunction(listener):
                await listener(*args)
            else:
                listener(*args)

    async def listen_notifications(self):
        """Listen for notifications from aria2 server.

        Continuously listens for WebSocket messages and processes
        aria2 notifications and command responses.
        """
        if self.is_websocket_listener_started:
            return
        self.is_websocket_listener_started = True
        while True:
            try:
                _LOGGER.debug('starting refresh loop')
                websocket = await self.ws.get()
                _LOGGER.debug('refresh loop have a websocket')
                async for message in websocket:
                    _LOGGER.debug('message received %s', message)
                    json_message = json.loads(message)
                    if 'method' in json_message:
                        action = json_message['method']
                        gid = json_message['params'][0]['gid']

                        status_mapping = {
                            'aria2.onDownloadStart': 'active',
                            'aria2.onDownloadPause': 'paused',
                            'aria2.onDownloadStop': 'stopped',
                            'aria2.onDownloadComplete': 'complete',
                            'aria2.onDownloadError': 'error'
                        }

                        if action in status_mapping:
                            status = status_mapping[action]
                            self.loop.create_task(self.call_notification_listeners([gid, status]))
                        else:
                            _LOGGER.info('unsupported aria method %s', action)
                    elif 'id' in json_message and json_message['id'] is not None:
                        command_id = json_message['id']
                        if command_id in self.running_command:
                            command = self.running_command.pop(command_id)
                            if 'result' in json_message:
                                command.result_received(json_message['result'])
                            elif 'error' in json_message:
                                command.error_received(json_message['error'])
                            else:
                                _LOGGER.error('unsupported aria response %s', json_message)
                        else:
                            _LOGGER.warning('receive a response for an unknown command. id = %s', command_id)
            except asyncio.CancelledError:
                _LOGGER.info('the asyncio is cancelled. stop to listen aria2 state update.')
                await (await self.ws.get()).close()
                break
            except:
                _LOGGER.exception('error on aria2 websocket. restart it. wait %s seconds before restart', WS_RETRY_DELAY_SECONDS)
                await asyncio.sleep(WS_RETRY_DELAY_SECONDS)
                _LOGGER.debug('after %s second of wait.', WS_RETRY_DELAY_SECONDS)

        _LOGGER.info("End of listen notification")


class SharableWebsocket:
    """Shareable WebSocket connection manager.

    Manages a single WebSocket connection that can be shared across
    multiple concurrent requests with automatic reconnection.
    """

    def __init__(self, url: str, loop: asyncio.AbstractEventLoop, retry_on_connection_error: bool = True):
        """Initialize the sharable WebSocket.

        Args:
            url: WebSocket URL to connect to
            loop: Asyncio event loop
            retry_on_connection_error: Whether to retry on connection errors
        """
        self.url = url
        self.ws = None
        self.loop = loop
        self.is_opening_socket = False
        self.waiting_opening_socket_futures = []
        self.retry_on_connection_error = retry_on_connection_error

    async def get(self):
        """Get or create a WebSocket connection.

        Returns an existing open connection or creates a new one.
        Handles connection queuing to avoid multiple simultaneous connection attempts.

        Returns:
            An open WebSocket connection
        """
        if self.ws and self.ws.state == websockets.protocol.State.OPEN:
            _LOGGER.debug("the websocket is already open reuse it")
            return self.ws
        elif not self.is_opening_socket:
            _LOGGER.debug("restart aria2 websocket")
            self.is_opening_socket = True
            try:
                self.ws = await websockets.connect(self.url)
            except:
                if self.retry_on_connection_error:
                    _LOGGER.exception("fail to create connection. wait %s seconds and restart process.", WS_RETRY_DELAY_SECONDS)
                    self.is_opening_socket = False
                    await asyncio.sleep(WS_RETRY_DELAY_SECONDS)
                    return await self.get()
                else:
                    raise

            self.is_opening_socket = False
            for future in self.waiting_opening_socket_futures:
                if not future.cancelled():
                    _LOGGER.debug("call websocket waiting future")
                    future.set_result(self.ws)
            self.waiting_opening_socket_futures = []
            return self.ws
        else:
            _LOGGER.debug("waiting for websocket connected before continue")
            ws_future = self.loop.create_future()
            self.waiting_opening_socket_futures.append(ws_future)
            return await ws_future

