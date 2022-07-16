import asyncio
import inspect
from typing import TypeVar

from aria2p import API
from custom_components.aria2.aria2_commands import Command
import websockets
import json
import logging

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

class WSClient():

    def __init__(self, ws_url: str, loop: asyncio.AbstractEventLoop, secret: str = None, retry_on_connection_error: bool = True):
        self.loop = loop
        self.secret = secret
        self.ws = SharableWebsocket(ws_url, loop, retry_on_connection_error)
        self.notification_listeners = []
        self.running_command = dict()
        self.is_websocket_listener_started = False

    def on_download_state_updated(self, listener):
        self.notification_listeners.append(listener)

    async def call(self, command: Command[T]) -> T:
        listen_task = None
        if not self.is_websocket_listener_started:
            listen_task = self.loop.create_task(self.listen_notifications())

        ws = await self.ws.get()
        future = command.build_awaitable_future(self.loop)
        self.running_command[str(command.id)] = command

        json_command = command.to_json(self.secret)
        _LOGGER.debug('send command ' + str(json_command))
        await ws.send(json.dumps(json_command))

        try:
            result = await future
            return result
        finally:
            if listen_task:
                listen_task.cancel()


    async def call_notification_listeners(self, args: list):
        for listener in self.notification_listeners:
            if inspect.iscoroutinefunction(listener):
                await listener(*args)
            else:
                listener(*args)

    async def listen_notifications(self):
        if self.is_websocket_listener_started:
            return
        self.is_websocket_listener_started = True
        while True:
            try:
                _LOGGER.debug('starting refresh loop')
                websocket = await self.ws.get()
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
                            self.loop.create_task(self.call_notification_listeners([gid, status]))
                        else:
                            _LOGGER.info('unsuported aria method ' + action)
                    elif 'id' in json_message and json_message['id'] != None:
                        command_id = json_message['id']
                        if command_id in self.running_command:
                            command = self.running_command.pop(command_id)
                            if 'result' in json_message:
                                command.result_received(json_message['result'])
                            elif 'error' in json_message:
                                command.error_received(json_message['error'])
                            else:
                                _LOGGER.error('unsuported aria response ' + str(json_message))
                        else:
                            _LOGGER.warn('receive a response for an unknown command. id = ' + command_id)
            except asyncio.CancelledError:
                _LOGGER.info('the asyncio is cancelled. stop to listen aria2 state update.')
                await (await self.ws.get()).close()
                break
            except:
                _LOGGER.exception('error on aria2 websocket. restart it. wait 3 seoncds before restart')
                await asyncio.sleep(3)
                _LOGGER.debug('after 3 second of wait.')

        _LOGGER.info("End of listen notification")


class SharableWebsocket():

    def __init__(self, url: str, loop: asyncio.AbstractEventLoop, retry_on_connection_error: bool = True):
        self.url = url
        self.ws = None
        self.loop = loop
        self.is_opening_socket = False
        self.waiting_opening_socket_futures = []
        self.retry_on_connection_error = retry_on_connection_error

    async def get(self):
        if self.ws and self.ws.open:
            _LOGGER.debug("the websocket is already open reuse it")
            return self.ws
        elif not self.is_opening_socket:
            _LOGGER.debug("restart aria2 websocket")
            self.is_opening_socket = True
            try:
                self.ws = await websockets.connect(self.url)
            except:
                if self.retry_on_connection_error:
                    _LOGGER.exception("fail to create connection. wait 3 seconds and restart process.")
                    self.is_opening_socket = False
                    await asyncio.sleep(3)
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

