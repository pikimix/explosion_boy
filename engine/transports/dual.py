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

TCP framing and connection management (recv buffering, send queue, the
connect handshake, and accept/register bookkeeping) are shared with the
plain-TCP backend — see engine/transports/_shared.py.
"""
from __future__ import annotations

import select
import socket
import struct
from uuid import UUID, uuid4

from engine.transport import (
    CHANNEL_RELIABLE,
    CHANNEL_UNRELIABLE,
    ConnectEvent,
    DisconnectEvent,
    ReceiveEvent,
    TransportEvent,
)
from engine.transports._shared import (
    TcpConnection,
    accept_and_register,
    encode_frame,
    poll_connecting,
)

_UDP_HEADER = struct.Struct('!16sB')  # 16-byte UUID + uint8 channel = 17 bytes
_CHANNEL_UDP_TOKEN = 0xFF             # internal: server delivers UUID to client over TCP


def _udp_encode(peer_id: UUID, data: bytes) -> bytes:
    return _UDP_HEADER.pack(peer_id.bytes, CHANNEL_UNRELIABLE) + data


class _TcpPeer(TcpConnection):
    """A server-side TCP peer connection, plus its registered UDP endpoint."""

    def __init__(self, sock: socket.socket, peer_id: UUID) -> None:
        super().__init__(sock, peer_id)
        self.udp_addr: tuple[str, int] | None = None


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
        """Service the TCP listen socket, UDP socket and all TCP peers once.

        Accepts new TCP connections, receives pending TCP/UDP data, flushes
        queued outbound TCP data, and drops any peer whose TCP connection
        has died.

        Parameters
        ----------
        timeout : float, optional
            Maximum time in seconds to block in ``select`` waiting for
            readable sockets (default 0, i.e. non-blocking).

        Returns
        -------
        list[TransportEvent]
            Connect, receive and disconnect events produced during this poll.
        """
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
        """Send a payload to a single connected peer.

        Parameters
        ----------
        peer_id : UUID
            Identifier of the target peer. Silently ignored if unknown.
        data : bytes
            Payload to send.
        channel : int, optional
            ``CHANNEL_RELIABLE`` routes over TCP; ``CHANNEL_UNRELIABLE``
            routes over UDP if the peer's UDP endpoint is registered,
            otherwise falls back to TCP (default ``CHANNEL_RELIABLE``).
        """
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
        """Send a payload to every currently connected peer.

        Parameters
        ----------
        data : bytes
            Payload to send.
        channel : int, optional
            ``CHANNEL_RELIABLE`` routes over TCP; ``CHANNEL_UNRELIABLE``
            routes over UDP for peers with a registered UDP endpoint,
            otherwise falls back to TCP (default ``CHANNEL_RELIABLE``).
        """
        frame = encode_frame(data, channel)
        for peer_id, peer in self._peers.items():
            if channel == CHANNEL_UNRELIABLE and peer.udp_addr is not None:
                try:
                    self._udp_sock.sendto(_udp_encode(peer_id, data), peer.udp_addr)
                except OSError:
                    pass
            else:
                peer.queue_encoded(frame)

    def disconnect(self, peer_id: UUID) -> None:
        """Forcibly drop a connected peer.

        Parameters
        ----------
        peer_id : UUID
            Identifier of the peer to disconnect. No-op if unknown.
        """
        if peer_id in self._peers:
            self._drop(peer_id, [])

    def close(self) -> None:
        """Close all peer connections and the TCP/UDP listen sockets."""
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
        peer = accept_and_register(
            self._tcp_listen, self._peers, self._sock_index, self._select_list,
            self._max_clients, peer_factory=_TcpPeer,
        )
        if peer is not None:
            peer.queue_send(peer.peer_id.bytes, _CHANNEL_UDP_TOKEN)
            events.append(ConnectEvent(peer.peer_id))

    def _recv_tcp(self, sock: socket.socket,
                  events: list[TransportEvent]) -> None:
        peer = self._sock_index.get(sock.fileno())
        if peer is None:
            return
        messages = peer.read()
        if messages is None:
            self._drop(peer.peer_id, events)
            return
        for frame in messages:
            if frame.channel != _CHANNEL_UDP_TOKEN:
                events.append(ReceiveEvent(peer.peer_id, frame.channel, frame.payload))

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

        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.setblocking(False)
        tcp_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._tcp = TcpConnection(tcp_sock, self._local_id)

        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setblocking(False)

        try:
            tcp_sock.connect((host, port))
        except BlockingIOError:
            pass

    @property
    def connected(self) -> bool:
        """Return whether the client currently has an established connection."""
        return self._connected

    def poll(self, timeout: float = 0) -> list[TransportEvent]:
        """Advance the connection state machine and process socket I/O once.

        While connecting, checks for TCP connect completion. Once connected,
        flushes queued outbound TCP data, reads pending TCP/UDP data, and
        detects disconnection.

        Parameters
        ----------
        timeout : float, optional
            Maximum time in seconds to block in ``select`` waiting for
            socket readiness (default 0, i.e. non-blocking).

        Returns
        -------
        list[TransportEvent]
            Connect, receive and disconnect events produced during this poll.
        """
        events: list[TransportEvent] = []

        if self._connecting:
            self._connecting, event = poll_connecting(
                self._tcp.sock, self._local_id, timeout, guard_select_oserror=True,
            )
            if isinstance(event, ConnectEvent):
                self._connected = True
            if event is not None:
                events.append(event)
            return events

        if not self._connected:
            return events

        # Flush outbound data before blocking so inputs sent last iteration go out now
        if not self._tcp.flush():
            self._connected = False
            events.append(DisconnectEvent(self._local_id))
            return events

        read_socks = [self._tcp.sock]
        if self._peer_uuid is not None:
            read_socks.append(self._udp_sock)
        try:
            readable, _, _ = select.select(read_socks, [], [], timeout)
        except OSError:
            self._connected = False
            events.append(DisconnectEvent(self._local_id))
            return events

        for sock in readable:
            if sock is self._tcp.sock:
                self._recv_tcp(events)
            else:
                self._recv_udp(events)

        if not self._tcp.flush():
            self._connected = False
            events.append(DisconnectEvent(self._local_id))

        return events

    def send(self, data: bytes, channel: int = CHANNEL_RELIABLE) -> None:
        """Send a payload to the server.

        Parameters
        ----------
        data : bytes
            Payload to send.
        channel : int, optional
            ``CHANNEL_RELIABLE`` routes over TCP; ``CHANNEL_UNRELIABLE``
            routes over UDP once the server has assigned a peer UUID,
            otherwise falls back to TCP (default ``CHANNEL_RELIABLE``).
        """
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
            self._tcp.queue_send(data, channel)

    def disconnect(self) -> None:
        """Close the TCP and UDP sockets and mark the client as disconnected."""
        self._connected = False
        self._connecting = False
        self._tcp.close()
        try:
            self._udp_sock.close()
        except OSError:
            pass

    def reconnect(self) -> None:
        """Close existing sockets and start a fresh connection attempt to the same host/port."""
        self._tcp.close()
        try:
            self._udp_sock.close()
        except OSError:
            pass
        self._peer_uuid = None
        self._connected = False
        self._connecting = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._tcp = TcpConnection(sock, self._local_id)
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setblocking(False)
        try:
            sock.connect((self._host, self._port))
        except BlockingIOError:
            pass

    def _recv_tcp(self, events: list[TransportEvent]) -> None:
        messages = self._tcp.read()
        if messages is None:
            self._connected = False
            events.append(DisconnectEvent(self._local_id))
            return
        for frame in messages:
            if frame.channel == _CHANNEL_UDP_TOKEN and len(frame.payload) == 16:
                # Server assigned our UUID — register UDP endpoint with server
                self._peer_uuid = UUID(bytes=frame.payload)
                try:
                    self._udp_sock.sendto(frame.payload, (self._host, self._port))
                except OSError:
                    pass
            else:
                events.append(ReceiveEvent(self._local_id, frame.channel, frame.payload))

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
