from __future__ import annotations

import asyncio
from asyncio import futures
from enum import Enum
import logging
from typing import Any, Dict, Generic, List, TypeVar
from uuid import uuid4
from homeassistant.exceptions import HomeAssistantError

from aria2p import Download, Options, Stats

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


class DownloadKeys(Enum):
    """Enumeration of aria2 download status keys."""

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
    ERROR_MESSAGE = "errorMessage"
    FOLLOWED_BY = "followedBy"
    FOLLOWING = "following"
    BELONGS_TO = "belongsTo"
    DIR = "dir"
    FILES = "files"
    BITTORRENT = "bittorrent"
    VERIFIED_LENGTH = "verifiedLength"
    VERIFY_INTEGRITY_PENDING = "verifyIntegrityPending"


class AriaError(HomeAssistantError):
    """Exception raised for aria2 RPC errors."""

    def __init__(self, message: str):
        """Initialize the error with a message."""
        super().__init__(message)


class Command(Generic[T]):
    """Base class for aria2 JSON-RPC commands.

    Generic command that can be executed via WebSocket to aria2 server.
    """

    def __init__(self, method: str, params: list | None = None) -> None:
        """Initialize a command.

        Args:
            method: The aria2 RPC method name
            params: List of parameters for the method
        """
        self.id = uuid4()
        self.method_name = method
        self.params = params if params is not None else []
        self.result_future = None

    def to_json(self, security_token: str | None = None) -> dict:
        """Convert command to JSON-RPC format.

        Args:
            security_token: Optional authentication token

        Returns:
            JSON-RPC formatted dictionary
        """
        params = ["token:" + security_token] if security_token else []
        params.extend(self.params)

        return {
            "jsonrpc": "2.0",
            "method": self.method_name,
            "id": str(self.id),
            "params": params,
        }

    def build_awaitable_future(self, loop: asyncio.AbstractEventLoop) -> futures.Future[T]:
        self.result_future = loop.create_future()
        return self.result_future

    def result_received(self, json: dict) -> T:
        result = self.get_result(json)
        if self.result_future and not self.result_future.cancelled():
            self.result_future.set_result(result)
        return result

    def error_received(self, json_error: dict) -> None:
        if json_error["code"] == 1:
            self._raise_except(AriaError(json_error["message"]))

    def get_result(self, json_result: dict) -> T:
        _LOGGER.error("the get_result function should be overriden")
        raise NotImplementedError("Subclasses must implement get_result")

    def _raise_except(self, exception: Exception) -> None:
        if self.result_future and not self.result_future.cancelled():
            self.result_future.set_exception(exception)
        else:
            raise exception


class GetGlobalOption(Command[Options]):
    """Command to get aria2 global options."""

    def __init__(self):
        """Initialize the GetGlobalOption command."""
        super().__init__("aria2.getGlobalOption")

    def get_result(self, json_result: dict) -> Options:
        return Options(None, json_result)


class ChangeGlobalOptions(Command[bool]):
    """Command to change aria2 global options."""

    def __init__(self, option_values: Dict[str, str]):
        """Initialize the ChangeGlobalOptions command.

        Args:
            option_values: Dictionary of option names and values to change
        """
        super().__init__("aria2.changeGlobalOption", [option_values])

    def get_result(self, json_result: dict) -> bool:
        return json_result == "OK"

    def error_received(self, json_error: dict):
        return self.result_received("KO")


class GetGlobalStat(Command[Stats]):
    """Command to get aria2 global statistics."""

    def __init__(self) -> None:
        """Initialize the GetGlobalStat command."""
        super().__init__("aria2.getGlobalStat")

    def get_result(self, json_result: dict) -> Stats:
        _LOGGER.debug("get_result for GetGlobalStat. %s", json_result)
        return Stats(json_result)


class Unpause(Command[str]):
    """Command to unpause a download."""

    def __init__(self, gid: str) -> None:
        """Initialize the Unpause command.

        Args:
            gid: Download GID to unpause
        """
        super().__init__("aria2.unpause", [gid])

    def get_result(self, json_result: Any) -> str:
        _LOGGER.debug("get_result for unpause. %s", json_result)
        return json_result


class Pause(Command[str]):
    """Command to pause a download."""

    def __init__(self, gid: str) -> None:
        """Initialize the Pause command.

        Args:
            gid: Download GID to pause
        """
        super().__init__("aria2.pause", [gid])

    def get_result(self, json_result: dict) -> str:
        _LOGGER.debug("get_result for pause. %s", json_result)
        return json_result


class Remove(Command[str]):
    """Command to remove a download."""

    def __init__(self, gid: str) -> None:
        """Initialize the Remove command.

        Args:
            gid: Download GID to remove
        """
        super().__init__("aria2.remove", [gid])

    def get_result(self, json_result: dict) -> str:
        _LOGGER.debug("get_result for remove. %s", json_result)
        return json_result


class AddUri(Command[str]):
    """Command to add a download by URI."""

    def __init__(self, uris: List[str]) -> None:
        """Initialize the AddUri command.

        Args:
            uris: List of URIs to download
        """
        super().__init__("aria2.addUri", [uris])

    def get_result(self, json_result: Any) -> str:
        _LOGGER.debug("get_result for addUri. %s", json_result)
        return json_result


class AddTorrent(Command[str]):
    """Command to add a torrent download."""

    def __init__(self, uri: str) -> None:
        """Initialize the AddTorrent command.

        Args:
            uri: Torrent URI
        """
        super().__init__("aria2.addTorrent", [uri])

    def get_result(self, json_result: Any) -> str:
        _LOGGER.debug("get_result for addTorrent. %s", json_result)
        return json_result


class TellActive(Command[List[Download]]):
    """Command to get active downloads."""

    def __init__(self, keys: List[DownloadKeys] | None = None) -> None:
        """Initialize the TellActive command.

        Args:
            keys: List of download keys to retrieve
        """
        keys = keys or []
        super().__init__("aria2.tellActive", [[k.value for k in keys]])

    def get_result(self, json_result: Any) -> List[Download]:
        _LOGGER.debug("get_result for tellActive. %s", json_result)
        return [Download(None, d) for d in json_result]


class TellWaiting(Command[List[Download]]):
    """Command to get waiting downloads."""

    def __init__(
        self, offset: int = 0, page_size: int = 1000, keys: List[DownloadKeys] | None = None
    ) -> None:
        """Initialize the TellWaiting command.

        Args:
            offset: Offset for pagination
            page_size: Number of downloads to retrieve
            keys: List of download keys to retrieve
        """
        keys = keys or []
        super().__init__(
            "aria2.tellWaiting", [offset, page_size, [k.value for k in keys]]
        )

    def get_result(self, json_result: Any) -> List[Download]:
        _LOGGER.debug("get_result for tellWaiting. %s", json_result)
        return [Download(None, d) for d in json_result]


class TellStopped(Command[List[Download]]):
    """Command to get stopped downloads."""

    def __init__(
        self, offset: int = 0, page_size: int = 1000, keys: List[DownloadKeys] | None = None
    ) -> None:
        """Initialize the TellStopped command.

        Args:
            offset: Offset for pagination
            page_size: Number of downloads to retrieve
            keys: List of download keys to retrieve
        """
        keys = keys or []
        super().__init__(
            "aria2.tellStopped", [offset, page_size, [k.value for k in keys]]
        )

    def get_result(self, json_result: Any) -> List[Download]:
        _LOGGER.debug("get_result for tellStopped. %s", json_result)
        return [Download(None, d) for d in json_result]


class TellStatus(Command[Download]):
    """Command to get download status."""

    def __init__(self, gid: str, keys: List[DownloadKeys] | None = None) -> None:
        """Initialize the TellStatus command.

        Args:
            gid: Download GID
            keys: List of download keys to retrieve
        """
        keys = keys or []
        super().__init__("aria2.tellStatus", [gid, [k.value for k in keys]])

    def get_result(self, json_result: Any) -> Download:
        _LOGGER.debug("get_result for tellStatus. %s", json_result)
        return Download(None, json_result)


class MultiCall(Command[List[Any]]):
    """Command to execute multiple commands in a single call."""

    def __init__(self, commands: List[Command[Any]]) -> None:
        """Initialize the MultiCall command.

        Args:
            commands: List of commands to execute
        """
        super().__init__("system.multicall", commands)

    def to_json(self, security_token: str | None = None) -> dict:
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

    def get_result(self, json_result: Any) -> List[Any]:
        _LOGGER.debug("get_result for multi_call. %s", json_result)
        return [
            self.params[index].get_result(result[0])
            for index, result in enumerate(json_result)
        ]
