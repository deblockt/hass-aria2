import logging


DOMAIN = "aria2"

CONF_PORT = "port"
CONF_SECURE_CONNECTION = "secure_connection"

# Timeout and delay constants
WS_RETRY_DELAY_SECONDS = 3
COORDINATOR_FAST_UPDATE_SECONDS = 3
COORDINATOR_SLOW_UPDATE_SECONDS = 30
TIMEOUT_SECONDS = 10

# Download state constants
STATE_ACTIVE = "active"
STATE_WAITING = "waiting"
STATE_STOPPED = "stopped"
STATE_PAUSED = "paused"
STATE_COMPLETE = "complete"
STATE_ERROR = "error"

# Conversion constants
BYTES_TO_MEGABYTES = 1_000_000

# Default values
DEFAULT_WS_PORT = 6800


def build_ws_url(host: str, port: str, secure_socket: bool = False) -> str:
    if host.startswith('https'):
        return f"wss://{host[8:]}:{port}/jsonrpc"
    elif host.startswith('http'):
        return f"ws://{host[7:]}:{port}/jsonrpc"
    elif secure_socket:
        return f"wss://{host}:{port}/jsonrpc"
    else:
        return f"ws://{host}:{port}/jsonrpc"
