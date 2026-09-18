import asyncio

from apps.worker_sessions.src.generation.socks5_tunnel.constants import (
    ATYPE_DOMAIN,
    ATYPE_IPV4,
    ATYPE_IPV6,
    AUTH_NO_ACCEPTABLE,
    AUTH_NO_AUTH,
    AUTH_USER_PASS,
    CMD_CONNECT,
    REP_SUCCESS,
    SOCKS5_VER,
)
from apps.worker_sessions.src.generation.socks5_tunnel.errors import (
    ClientDisconnected,
    ClientProtocolError,
    UpstreamAuthFailed,
    UpstreamProtocolError,
    UpstreamRejected,
)


async def read_exact(reader: asyncio.StreamReader, byte_count: int) -> bytes:
    try:
        data = await reader.readexactly(byte_count)
    except asyncio.IncompleteReadError as exc:
        raise ClientDisconnected('connection closed while reading') from exc
    return data


async def read_addr(reader: asyncio.StreamReader, atype: int) -> bytes:
    if atype == ATYPE_IPV4:
        return await read_exact(reader=reader, byte_count=4)
    if atype == ATYPE_DOMAIN:
        length = (await read_exact(reader=reader, byte_count=1))[0]
        return bytes([length]) + await read_exact(reader=reader, byte_count=length)
    if atype == ATYPE_IPV6:
        return await read_exact(reader=reader, byte_count=16)
    raise ValueError(f'unknown address type: 0x{atype:02x}')


class ConnectRequest:
    __slots__ = ('atype', 'addr_raw', 'port')

    def __init__(self, atype: int, addr_raw: bytes, port: int) -> None:
        self.atype = atype
        self.addr_raw = addr_raw
        self.port = port


async def read_client_handshake(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
) -> ConnectRequest:
    """Reads the client greeting + CONNECT request (RFC 1928 §3/§4) and always selects
    NO AUTH — the browser side never needs real credentials, that's the whole point of
    this tunnel. Writes SOCKS5 error replies itself for request-level rejections (bad
    CMD/ATYP) since those are protocol-level, not connection-level, failures."""
    header = await read_exact(reader=reader, byte_count=2)
    if header[0] != SOCKS5_VER:
        raise ClientProtocolError(f'unsupported SOCKS version: {header[0]}')
    method_count = header[1]
    await read_exact(reader=reader, byte_count=method_count)
    writer.write(b'\x05\x00')
    await writer.drain()

    request_header = await read_exact(reader=reader, byte_count=4)
    if request_header[0] != SOCKS5_VER:
        raise ClientProtocolError(f'unexpected VER in request: {request_header[0]}')
    if request_header[1] != CMD_CONNECT:
        writer.write(b'\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00')
        await writer.drain()
        raise ClientProtocolError(f'unsupported CMD: {request_header[1]}')
    atype = request_header[3]

    try:
        addr_raw = await read_addr(reader=reader, atype=atype)
    except ValueError as exc:
        writer.write(b'\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00')
        await writer.drain()
        raise ClientProtocolError(str(exc)) from exc

    port_raw = await read_exact(reader=reader, byte_count=2)
    return ConnectRequest(atype=atype, addr_raw=addr_raw, port=int.from_bytes(port_raw, 'big'))


_CONNECT_PREFIX = {
    ATYPE_IPV4: b'\x05\x01\x00\x01',
    ATYPE_DOMAIN: b'\x05\x01\x00\x03',
    ATYPE_IPV6: b'\x05\x01\x00\x04',
}


async def upstream_connect(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    username: str,
    password: str,
    request: ConnectRequest,
) -> bytes:
    """Performs the upstream SOCKS5 handshake + CONNECT (RFC 1928 §3/§4/§6) using the
    real proxy credentials, and returns the raw reply header+addr+port to relay back to
    the client verbatim. Raises UpstreamRejected for any non-zero REP code."""
    writer.write(b'\x05\x02\x00\x02')  # offer NO AUTH or USER/PASS
    await writer.drain()
    server_choice = await read_exact(reader=reader, byte_count=2)
    if server_choice[0] != SOCKS5_VER:
        raise UpstreamProtocolError(f'upstream returned unexpected VER: {server_choice[0]}')
    selected = server_choice[1]

    if selected == AUTH_NO_ACCEPTABLE:
        raise UpstreamAuthFailed('upstream: no acceptable auth method')
    if selected == AUTH_USER_PASS:
        username_bytes, password_bytes = username.encode(), password.encode()
        writer.write(
            b'\x01'
            + bytes([len(username_bytes)]) + username_bytes
            + bytes([len(password_bytes)]) + password_bytes,
        )
        await writer.drain()
        auth_response = await read_exact(reader=reader, byte_count=2)
        if auth_response[1] != REP_SUCCESS:
            raise UpstreamAuthFailed('upstream: authentication failed')
    elif selected != AUTH_NO_AUTH:
        raise UpstreamProtocolError(f'upstream: unexpected auth method 0x{selected:02x}')

    prefix = _CONNECT_PREFIX[request.atype]
    port_raw = request.port.to_bytes(2, 'big')
    writer.write(prefix + request.addr_raw + port_raw)
    await writer.drain()

    response_header = await read_exact(reader=reader, byte_count=4)
    if response_header[0] != SOCKS5_VER:
        raise UpstreamProtocolError(f'upstream response unexpected VER: {response_header[0]}')
    response_atype = response_header[3]
    try:
        response_addr = await read_addr(reader=reader, atype=response_atype)
    except ValueError as exc:
        raise UpstreamProtocolError(
            f'upstream response has unknown ATYP: 0x{response_atype:02x}',
        ) from exc
    response_port = await read_exact(reader=reader, byte_count=2)

    if response_header[1] != REP_SUCCESS:
        raise UpstreamRejected(response_header[1])

    return response_header + response_addr + response_port
