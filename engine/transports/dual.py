"""
Dual TCP+UDP backend for the transport abstraction.

Reliable channel   (CHANNEL_RELIABLE=0)   → TCP (ordered, guaranteed delivery)
Unreliable channel (CHANNEL_UNRELIABLE=1) → UDP (fire-and-forget, no
                                             head-of-line blocking)
  Falls back to TCP until the UDP endpoint has been registered.

UDP registration handshake (transport-internal, invisible to game code):
  1. Server accepts TCP connection, assigns peer UUID, immediately sends a
     _CHANNEL_UDP_TOKEN frame over TCP — payload is the raw 16-byte UUID.
  2. Client intercepts the token frame, opens its UDP socket, echoes the 16
     bytes as a bare datagram to the server's (host, port).
  3. Server receives the 16-byte datagram, maps (src_ip, src_port) → UUID.
     All subsequent CHANNEL_UNRELIABLE sends now use the UDP path.

UDP datagram format:
  [16 bytes] peer UUID  (big-endian bytes)
  [1 byte]   channel    (CHANNEL_UNRELIABLE)
  [N bytes]  payload
"""
from __future__ import annotations

import select
import socket
import struct
from collections import deque
from uuid import UUID, uuid4

from engine.transport import (
    CHANNEL_RELIABLE,
    CHANNEL_UNRELIABLE,
    ConnectEvent,
    DisconnectEvent,
    ReceiveEvent,
    TransportEvent,
)

_TCP_HEADER = struct.Struct('!IB')    # uint32 length + uint8 channel = 5 bytes
_UDP_HEADER = struct.Struct('!16sB')  # 16-byte UUID + uint8 channel = 17 bytes
_CHANNEL_UDP_TOKEN = 0xFF             # internal: server delivers UUID to client over TCP


def _tcp_encode(data: bytes, channel: int) -> bytes:
    return _TCP_HEADER.pack(len(data), channel) + data


def _udp_encode(peer_id: UUID, data: bytes) -> bytes:
    return _UDP_HEADER.pack(peer_id.bytes, CHANNEL_UNRELIABLE) + data


class _RecvBuffer:
    """Accumulates raw TCP bytes; yields complete framed messages."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> None:
        self._buf.extend(chunk)

    def messages(self) -> list[tuple[int, bytes]]:
        out: list[tuple[int, bytes]] = []
        while len(self._buf) >= _TCP_HEADER.size:
            length, channel = _TCP_HEADER.unpack_from(self._buf)
            total = _TCP_HEADER.size + length
            if len(self._buf) < total:
                break
            payload = bytes(self._buf[_TCP_HEADER.size:total])
            del self._buf[:total]
            out.append((channel, payload))
        return out


class _TcpPeer:
    def __init__(self, sock: socket.socket, peer_id: UUID) -> None:
        self.sock = sock
        self.peer_id = peer_id
        self.recv_buf = _RecvBuffer()
        self._send_queue: deque[bytes] = deque()
        self.udp_addr: tuple[str, int] | None = None

    def queue_send(self, data: bytes, channel: int) -> None:
        self._send_queue.append(_tcp_encode(data, channel))

    def flush(self) -> bool:
        """Drain the TCP send queue. Returns False if the peer has disconnected."""
        while self._send_queue:
            frame = self._send_queue[0]
            try:
                sent = self.sock.send(frame)
                if sent == 0:
                    return False
                if sent < len(frame):
                    self._send_queue[0] = frame[sent:]
                    break
                self._send_queue.popleft()
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                return False
        return True

    def read(self) -> list[tuple[int, bytes]] | None:
        """Non-blocking TCP read. Returns parsed messages, or None on disconnect."""
        try:
            chunk = self.sock.recv(65536)
        except (BlockingIOError, InterruptedError):
            return []
        except OSError:
            return None
        if not chunk:
            return None
        self.recv_buf.feed(chunk)
        return self.recv_buf.messages()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# ── Server ─────────────────────────────────────────────────────────────────────

class DualServerTransport:
    """Listens on TCP and UDP on the same port number simultaneously.

    CHANNEL_RELIABLE  → always routed through TCP.
    CHANNEL_UNRELIABLE → routed through UDP once the peer's endpoint is
                         registered; falls back to TCP until then.
    """

    def __init__(self, host: str = '0.0.0.0', port: int = 9000,
                 max_clients: int = 16) -> None:
        self._max_clients = max_clients
        self._peers: dict[UUID, _TcpPeer] = {}
        self._udp_index: dict[tuple[str, int], UUID] = {}  # addr → peer_id
        self._sock_index: dict[int, _TcpPeer] = {}         # fileno → peer for O(1) lookup

        self._tcp_listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._tcp_listen.setblocking(False)
        self._tcp_listen.bind((host, port))
        self._tcp_listen.listen(max_clients)

        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._udp_sock.setblocking(False)
        self._udp_sock.bind((host, port))

        self._select_list: list[socket.socket] = [self._tcp_listen, self._udp_sock]

    def poll(self, timeout: float = 0) -> list[TransportEvent]:
        events: list[TransportEvent] = []

        readable, _, _ = select.select(self._select_list, [], [], timeout)

        for sock in readable:
            if sock is self._tcp_listen:
                self._accept(events)
            elif sock is self._udp_sock:
                self._recv_udp(events)
            else:
                self._recv_tcp(sock, events)

        dead: list[UUID] = []
        for pid, peer in self._peers.items():
            if not peer.flush():
                dead.append(pid)
        for pid in dead:
            self._drop(pid, events)

        return events

    def send(self, peer_id: UUID, data: bytes,
             channel: int = CHANNEL_RELIABLE) -> None:
        peer = self._peers.get(peer_id)
        if peer is None:
            return
        if channel == CHANNEL_UNRELIABLE and peer.udp_addr is not None:
            try:
                self._udp_sock.sendto(_udp_encode(peer_id, data), peer.udp_addr)
            except OSError:
                pass
        else:
            peer.queue_send(data, channel)

    def broadcast(self, data: bytes,
                  channel: int = CHANNEL_RELIABLE) -> None:
        for peer_id, peer in self._peers.items():
            if channel == CHANNEL_UNRELIABLE and peer.udp_addr is not None:
                try:
                    self._udp_sock.sendto(_udp_encode(peer_id, data), peer.udp_addr)
                except OSError:
                    pass
            else:
                peer._send_queue.append(_tcp_encode(data, channel))

    def disconnect(self, peer_id: UUID) -> None:
        if peer_id in self._peers:
            self._drop(peer_id, [])

    def close(self) -> None:
        for peer in list(self._peers.values()):
            peer.close()
        self._peers.clear()
        self._udp_index.clear()
        self._sock_index.clear()
        try:
            self._tcp_listen.close()
        except OSError:
            pass
        try:
            self._udp_sock.close()
        except OSError:
            pass

    def _accept(self, events: list[TransportEvent]) -> None:
        try:
            conn, _ = self._tcp_listen.accept()
        except OSError:
            return
        if len(self._peers) >= self._max_clients:
            conn.close()
            return
        conn.setblocking(False)
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        pid = uuid4()
        peer = _TcpPeer(conn, pid)
        self._peers[pid] = peer
        self._sock_index[conn.fileno()] = peer
        self._select_list.append(conn)
        peer.queue_send(pid.bytes, _CHANNEL_UDP_TOKEN)
        events.append(ConnectEvent(pid))

    def _recv_tcp(self, sock: socket.socket,
                  events: list[TransportEvent]) -> None:
        peer = self._sock_index.get(sock.fileno())
        if peer is None:
            return
        messages = peer.read()
        if messages is None:
            self._drop(peer.peer_id, events)
            return
        for channel, data in messages:
            if channel != _CHANNEL_UDP_TOKEN:
                events.append(ReceiveEvent(peer.peer_id, channel, data))

    def _recv_udp(self, events: list[TransportEvent]) -> None:
        try:
            data, addr = self._udp_sock.recvfrom(65536)
        except OSError:
            return

        if len(data) == 16:
            # Registration packet: bare 16-byte peer UUID echoed from client
            try:
                peer_id = UUID(bytes=data)
            except ValueError:
                return
            if peer_id in self._peers:
                self._udp_index[addr] = peer_id
                self._peers[peer_id].udp_addr = addr
            return

        if len(data) < _UDP_HEADER.size:
            return
        uuid_bytes, channel = _UDP_HEADER.unpack_from(data)
        payload = data[_UDP_HEADER.size:]
        try:
            peer_id = UUID(bytes=uuid_bytes)
        except ValueError:
            return
        if peer_id in self._peers:
            events.append(ReceiveEvent(peer_id, channel, payload))

    def _drop(self, peer_id: UUID, events: list[TransportEvent]) -> None:
        peer = self._peers.pop(peer_id, None)
        if peer:
            if peer.udp_addr:
                self._udp_index.pop(peer.udp_addr, None)
            self._sock_index.pop(peer.sock.fileno(), None)
            self._select_list = (
                [self._tcp_listen] + [p.sock for p in self._peers.values()] + [self._udp_sock]
            )
            peer.close()
            events.append(DisconnectEvent(peer_id))


# ── Client ─────────────────────────────────────────────────────────────────────

class DualClientTransport:
    """Connects via TCP for reliable traffic; upgrades CHANNEL_UNRELIABLE to UDP
    once the server delivers the peer UUID token over TCP."""

    def __init__(self, host: str = '127.0.0.1', port: int = 9000) -> None:
        self._host = host
        self._port = port
        # Stable ID used in ConnectEvent / ReceiveEvent / DisconnectEvent.
        self._local_id = uuid4()
        # UUID assigned by the server; required to stamp outgoing UDP datagrams.
        self._peer_uuid: UUID | None = None
        self._connected = False
        self._connecting = True

        self._tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_sock.setblocking(False)
        self._tcp_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._tcp_recv_buf = _RecvBuffer()
        self._tcp_send_queue: deque[bytes] = deque()

        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setblocking(False)

        try:
            self._tcp_sock.connect((host, port))
        except BlockingIOError:
            pass

    @property
    def connected(self) -> bool:
        return self._connected

    def poll(self, timeout: float = 0) -> list[TransportEvent]:
        events: list[TransportEvent] = []

        if self._connecting:
            _, writable, exceptional = select.select(
                [], [self._tcp_sock], [self._tcp_sock], timeout
            )
            if exceptional:
                self._connecting = False
                events.append(DisconnectEvent(self._local_id))
                return events
            if writable:
                err = self._tcp_sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                self._connecting = False
                if err != 0:
                    events.append(DisconnectEvent(self._local_id))
                    return events
                self._connected = True
                events.append(ConnectEvent(self._local_id))
            return events

        if not self._connected:
            return events

        # Flush outbound data before blocking so inputs sent last iteration go out now
        if not self._flush_tcp():
            self._connected = False
            events.append(DisconnectEvent(self._local_id))
            return events

        read_socks = [self._tcp_sock]
        if self._peer_uuid is not None:
            read_socks.append(self._udp_sock)
        try:
            readable, _, _ = select.select(read_socks, [], [], timeout)
        except OSError:
            self._connected = False
            events.append(DisconnectEvent(self._local_id))
            return events

        for sock in readable:
            if sock is self._tcp_sock:
                self._recv_tcp(events)
            else:
                self._recv_udp(events)

        if not self._flush_tcp():
            self._connected = False
            events.append(DisconnectEvent(self._local_id))

        return events

    def send(self, data: bytes, channel: int = CHANNEL_RELIABLE) -> None:
        if not self._connected:
            return
        if channel == CHANNEL_UNRELIABLE and self._peer_uuid is not None:
            try:
                self._udp_sock.sendto(
                    _udp_encode(self._peer_uuid, data), (self._host, self._port)
                )
            except OSError:
                pass
        else:
            self._tcp_send_queue.append(_tcp_encode(data, channel))

    def disconnect(self) -> None:
        self._connected = False
        self._connecting = False
        try:
            self._tcp_sock.close()
        except OSError:
            pass
        try:
            self._udp_sock.close()
        except OSError:
            pass

    def reconnect(self) -> None:
        try:
            self._tcp_sock.close()
        except OSError:
            pass
        try:
            self._udp_sock.close()
        except OSError:
            pass
        self._peer_uuid = None
        self._connected = False
        self._connecting = True
        self._tcp_recv_buf = _RecvBuffer()
        self._tcp_send_queue.clear()
        self._tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_sock.setblocking(False)
        self._tcp_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setblocking(False)
        try:
            self._tcp_sock.connect((self._host, self._port))
        except BlockingIOError:
            pass

    def _recv_tcp(self, events: list[TransportEvent]) -> None:
        try:
            chunk = self._tcp_sock.recv(65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._connected = False
            events.append(DisconnectEvent(self._local_id))
            return
        if not chunk:
            self._connected = False
            events.append(DisconnectEvent(self._local_id))
            return
        self._tcp_recv_buf.feed(chunk)
        for channel, data in self._tcp_recv_buf.messages():
            if channel == _CHANNEL_UDP_TOKEN and len(data) == 16:
                # Server assigned our UUID — register UDP endpoint with server
                self._peer_uuid = UUID(bytes=data)
                try:
                    self._udp_sock.sendto(data, (self._host, self._port))
                except OSError:
                    pass
            else:
                events.append(ReceiveEvent(self._local_id, channel, data))

    def _recv_udp(self, events: list[TransportEvent]) -> None:
        try:
            data, _ = self._udp_sock.recvfrom(65536)
        except (BlockingIOError, InterruptedError, OSError):
            return
        if len(data) < _UDP_HEADER.size:
            return
        _, channel = _UDP_HEADER.unpack_from(data)
        payload = data[_UDP_HEADER.size:]
        events.append(ReceiveEvent(self._local_id, channel, payload))

    def _flush_tcp(self) -> bool:
        while self._tcp_send_queue:
            frame = self._tcp_send_queue[0]
            try:
                sent = self._tcp_sock.send(frame)
                if sent == 0:
                    return False
                if sent < len(frame):
                    self._tcp_send_queue[0] = frame[sent:]
                    break
                self._tcp_send_queue.popleft()
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                return False
        return True
