import asyncio
from asyncio import futures
from enum import Enum
import logging
from typing import Any, Dict, Generic, List, TypeVar
from uuid import uuid4

from aria2p import Download, Options, Stats

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


class DownoladKeys(Enum):
    GID = "gid"
    STATUS = "status"
    TOTAL_LENGTH = "totalLength"
    COMPLETED_LENGTH = "completedLength"
    UPLOADED_LENGTH = "uploadLength"
    BIT_FIELD = "bitfield"
    DOWNLOAD_SPEED = "downloadSpeed"
    UPLOAD_SPEED = "uploadSpeed"
    INFO_HASH = "infoHash"
    NUM_SEEDERS = "numSeeders"
    SEEDER = "seeder"
    PIECE_LENGTH = "pieceLength"
    NUM_PIECES = "numPieces"
    CONNECTIONS = "connections"
    ERROR_CODE = "errorCode"
    FOLLOWED_BY = "followedBy"
    FOLLOWING = "following"
    BELONGS_TO = "belongsTo"
    DIR = "dir"
    FILES = "files"
    BITTORENT = "bittorrent"
    VERIFIED_LENGTH = "verifiedLength"
    VERIFY_INTEGRITY_PENDING = "verifyIntegrityPending"


class UnauthorizedError(Exception):
    pass


class Command(Generic[T]):
    def __init__(self, method: str, params: list = []):
        self.id = uuid4()
        self.method_name = method
        self.params = params
        self.result_future = None

    def to_json(self, security_token: str = None) -> dict:
        params = ["token:" + security_token] if security_token else []
        params.extend(self.params)

        return {
            "jsonrpc": "2.0",
            "method": self.method_name,
            "id": str(self.id),
            "params": params,
        }

    def build_awaitable_future(self, loop: asyncio.AbstractEventLoop) -> futures.Future:
        self.result_future = loop.create_future()
        return self.result_future

    def result_received(self, json: dict) -> T:
        result = self.get_result(json)
        if self.result_future and not self.result_future.cancelled():
            self.result_future.set_result(result)
        return result

    def error_received(self, json_error: dict):
        if json_error["code"] == 1:
            self._raise_except(UnauthorizedError())

    def get_result(self, json_result: dict) -> T:
        _LOGGER.error("the get_result function should be overriden")

    def _raise_except(self, exception: Exception):
        if self.result_future and not self.result_future.cancelled():
            self.result_future.set_exception(exception)
        else:
            raise exception


class GetGlobalOption(Command[Options]):
    def __init__(self):
        super().__init__("aria2.getGlobalOption")

    def get_result(self, json_result: dict) -> Options:
        return Options(None, json_result)


class ChangeGlobalOptions(Command[bool]):
    def __init__(self, optionValues: Dict[str, str]):
        super().__init__("aria2.changeGlobalOption", [optionValues])

    def get_result(self, json_result: dict) -> bool:
        return json_result == "OK"

    def error_received(self, json_error: dict):
        return self.result_received("KO")


class GetGlobalStat(Command[Stats]):
    def __init__(self):
        super().__init__("aria2.getGlobalStat")

    def get_result(self, json_result: dict) -> Stats:
        _LOGGER.debug("get_result for GetGlobalStat. " + str(json_result))
        return Stats(json_result)


class Unpause(Command[str]):
    def __init__(self, gid):
        super().__init__("aria2.unpause", [gid])

    def get_result(self, json_result: Any) -> str:
        _LOGGER.debug("get_result for unpause. " + str(json_result))
        return json_result


class Pause(Command[str]):
    def __init__(self, gid):
        super().__init__("aria2.pause", [gid])

    def get_result(self, json_result: dict) -> str:
        _LOGGER.debug("get_result for pause. " + str(json_result))
        return json_result


class Remove(Command[str]):
    def __init__(self, gid):
        super().__init__("aria2.remove", [gid])

    def get_result(self, json_result: dict) -> str:
        _LOGGER.debug("get_result for remove. " + str(json_result))
        return json_result


class AddUri(Command[str]):
    def __init__(self, uris: List[str]):
        super().__init__("aria2.addUri", [uris])

    def get_result(self, json_result: Any) -> str:
        _LOGGER.debug("get_result for addUri. " + str(json_result))
        return json_result


class AddTorrent(Command[str]):
    def __init__(self, uri: str):
        super().__init__("aria2.addTorrent", [uri])

    def get_result(self, json_result: Any) -> str:
        _LOGGER.debug("get_result for addTorrent. " + str(json_result))
        return json_result


class TellActive(Command[List[Download]]):
    def __init__(self, keys: List[DownoladKeys] = []):
        super().__init__("aria2.tellActive", [[k.value for k in keys]])

    def get_result(self, json_result: Any) -> str:
        _LOGGER.debug("get_result for tellActive. " + str(json_result))
        return [Download(None, d) for d in json_result]


class TellWaiting(Command[List[Download]]):
    def __init__(
        self, offset: int = 0, pageSize: int = 1000, keys: List[DownoladKeys] = []
    ):
        super().__init__(
            "aria2.tellWaiting", [offset, pageSize, [k.value for k in keys]]
        )

    def get_result(self, json_result: Any) -> str:
        _LOGGER.debug("get_result for tellWaiting. " + str(json_result))
        return [Download(None, d) for d in json_result]


class TellStopped(Command[List[Download]]):
    def __init__(
        self, offset: int = 0, pageSize: int = 1000, keys: List[DownoladKeys] = []
    ):
        super().__init__(
            "aria2.tellStopped", [offset, pageSize, [k.value for k in keys]]
        )

    def get_result(self, json_result: Any) -> str:
        _LOGGER.debug("get_result for tellStopped. " + str(json_result))
        return [Download(None, d) for d in json_result]


class TellStatus(Command[Download]):
    def __init__(self, gid: str, keys: List[DownoladKeys] = []):
        super().__init__("aria2.tellStatus", [gid, [k.value for k in keys]])

    def get_result(self, json_result: Any) -> str:
        _LOGGER.debug("get_result for tellStatus. " + str(json_result))
        return Download(None, json_result)


class MultiCall(Command[List[Any]]):
    def __init__(self, commands: List[Command[Any]]):
        super().__init__("system.multicall", commands)

    def to_json(self, security_token: str = None) -> dict:
        params = []
        for command in self.params:
            command_json = command.to_json(security_token)
            params.append(
                {"methodName": command_json["method"], "params": command_json["params"]}
            )

        return {
            "jsonrpc": "2.0",
            "method": self.method_name,
            "id": str(self.id),
            "params": [params],
        }

    def get_result(self, json_result: Any) -> str:
        _LOGGER.debug("get_result for multi_call. " + str(json_result))
        return [
            self.params[index].get_result(result[0])
            for index, result in enumerate(json_result)
        ]
