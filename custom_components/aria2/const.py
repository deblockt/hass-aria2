import logging


DOMAIN="aria2"

CONF_PORT="port"

_LOGGER = logging.getLogger(__name__)
def ws_url(host: str, port: str):
    if host.startswith('https'):
        _LOGGER.warn("https is not supported yet")
        return f"ws://{host[8:]}:{port}/jsonrpc"
    elif host.startswith('http'):
        return f"ws://{host[7:]}:{port}/jsonrpc"
    else:
        return f"ws://{host}:{port}/jsonrpc"
