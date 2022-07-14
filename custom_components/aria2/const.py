import logging


DOMAIN="aria2"

CONF_PORT="port"
CONF_SERCURE_CONNECTION = 'secure_connection'

def ws_url(host: str, port: str, secure_socket: bool = False):
    if host.startswith('https'):
        return f"wss://{host[8:]}:{port}/jsonrpc"
    elif host.startswith('http'):
        return f"ws://{host[7:]}:{port}/jsonrpc"
    elif secure_socket:
        return f"wss://{host}:{port}/jsonrpc"
    else:
        return f"ws://{host}:{port}/jsonrpc"
