"""
TCP backend for the transport abstraction.

Frame format and connection management are shared with the dual TCP+UDP
backend — see engine/transports/_shared.py.

Each connection gets its own recv buffer so a slow peer never stalls others.
"""
from __future__ import annotations

import select
import socket
from uuid import UUID, uuid4

from engine.transport import (
    CHANNEL_RELIABLE,
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


# ── Server ─────────────────────────────────────────────────────────────────────

class TCPServerTransport:
    """TCP transport backend that accepts and manages multiple client connections."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9000,
                 max_clients: int = 16) -> None:
        self._max_clients = max_clients
        self._peers: dict[UUID, TcpConnection] = {}
        self._sock_index: dict[int, TcpConnection] = {}   # fileno → peer for O(1) lookup
        self._listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen.setblocking(False)
        self._listen.bind((host, port))
        self._listen.listen(max_clients)
        self._select_list: list[socket.socket] = [self._listen]

    def poll(self, timeout: float = 0) -> list[TransportEvent]:
        """Accept new connections, receive data, and flush outbound queues.

        Parameters
        ----------
        timeout : float, optional
            Maximum time in seconds to block in ``select`` waiting for
            readable sockets (default 0, i.e. non-blocking).

        Returns
        -------
        list of TransportEvent
            Connect, receive, and disconnect events generated during this poll.
        """
        events: list[TransportEvent] = []

        readable, _, _ = select.select(self._select_list, [], [], timeout)

        for sock in readable:
            if sock is self._listen:
                self._accept(events)
            else:
                self._recv_from(sock, events)

        # Flush outbound queues for all peers
        dead: list[UUID] = []
        for pid, peer in self._peers.items():
            if not peer.flush():
                dead.append(pid)
        for pid in dead:
            self._drop(pid, events)

        return events

    def send(self, peer_id: UUID, data: bytes,
             channel: int = CHANNEL_RELIABLE) -> None:
        """Queue data to be sent to a single connected peer.

        Parameters
        ----------
        peer_id : UUID
            Identifier of the target peer; unknown ids are silently ignored.
        data : bytes
            Payload to send.
        channel : int, optional
            Channel identifier to tag the frame with (default ``CHANNEL_RELIABLE``).
        """
        if peer := self._peers.get(peer_id):
            peer.queue_send(data, channel)

    def broadcast(self, data: bytes,
                  channel: int = CHANNEL_RELIABLE) -> None:
        """Queue data to be sent to every currently connected peer.

        Parameters
        ----------
        data : bytes
            Payload to send to all peers.
        channel : int, optional
            Channel identifier to tag the frame with (default ``CHANNEL_RELIABLE``).
        """
        frame = encode_frame(data, channel)
        for peer in self._peers.values():
            peer.queue_encoded(frame)

    def disconnect(self, peer_id: UUID) -> None:
        """Forcibly drop a connected peer.

        Parameters
        ----------
        peer_id : UUID
            Identifier of the peer to disconnect; unknown ids are ignored.
        """
        if peer_id in self._peers:
            self._drop(peer_id, [])

    def close(self) -> None:
        """Close all peer connections and the listening socket."""
        for peer in list(self._peers.values()):
            peer.close()
        self._peers.clear()
        self._sock_index.clear()
        try:
            self._listen.close()
        except OSError:
            pass

    def _accept(self, events: list[TransportEvent]) -> None:
        peer = accept_and_register(
            self._listen, self._peers, self._sock_index, self._select_list, self._max_clients,
        )
        if peer is not None:
            events.append(ConnectEvent(peer.peer_id))

    def _recv_from(self, sock: socket.socket,
                   events: list[TransportEvent]) -> None:
        peer = self._sock_index.get(sock.fileno())
        if peer is None:
            return
        messages = peer.read()
        if messages is None:
            self._drop(peer.peer_id, events)
            return
        for frame in messages:
            events.append(ReceiveEvent(peer.peer_id, frame.channel, frame.payload))

    def _drop(self, peer_id: UUID, events: list[TransportEvent]) -> None:
        peer = self._peers.pop(peer_id, None)
        if peer:
            self._sock_index.pop(peer.sock.fileno(), None)
            self._select_list = [self._listen] + [p.sock for p in self._peers.values()]
            peer.close()
            events.append(DisconnectEvent(peer_id))


# ── Client ─────────────────────────────────────────────────────────────────────

class TCPClientTransport:
    """TCP transport backend that connects to a single remote server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9000) -> None:
        self._host = host
        self._port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setblocking(False)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._peer = TcpConnection(self._sock, uuid4())
        self._connected = False
        self._connecting = True
        try:
            self._sock.connect((host, port))
        except BlockingIOError:
            pass  # connection in progress — expected for non-blocking

    @property
    def connected(self) -> bool:
        """Whether the client currently has an established connection."""
        return self._connected

    def poll(self, timeout: float = 0) -> list[TransportEvent]:
        """Advance the connection state machine and process socket I/O.

        Handles the in-progress connection handshake, flushes queued
        outbound data, reads incoming messages, and detects disconnection.

        Parameters
        ----------
        timeout : float, optional
            Maximum time in seconds to block in ``select`` waiting for
            socket readiness (default 0, i.e. non-blocking).

        Returns
        -------
        list of TransportEvent
            Connect, receive, and disconnect events generated during this poll.
        """
        events: list[TransportEvent] = []

        if self._connecting:
            self._connecting, event = poll_connecting(self._sock, self._peer.peer_id, timeout)
            if isinstance(event, ConnectEvent):
                self._connected = True
            if event is not None:
                events.append(event)
            return events

        if not self._connected:
            return events

        # Flush outbound data before blocking so inputs sent last iteration go out now
        if not self._peer.flush():
            self._connected = False
            events.append(DisconnectEvent(self._peer.peer_id))
            return events

        try:
            readable, _, _ = select.select([self._sock], [], [], timeout)
        except OSError:
            self._connected = False
            events.append(DisconnectEvent(self._peer.peer_id))
            return events

        if readable:
            messages = self._peer.read()
            if messages is None:
                self._connected = False
                events.append(DisconnectEvent(self._peer.peer_id))
                return events
            for frame in messages:
                events.append(ReceiveEvent(self._peer.peer_id, frame.channel, frame.payload))

        if not self._peer.flush():
            self._connected = False
            events.append(DisconnectEvent(self._peer.peer_id))

        return events

    def send(self, data: bytes, channel: int = CHANNEL_RELIABLE) -> None:
        """Queue data to be sent to the server if currently connected.

        Parameters
        ----------
        data : bytes
            Payload to send.
        channel : int, optional
            Channel identifier to tag the frame with (default ``CHANNEL_RELIABLE``).
        """
        if self._connected:
            self._peer.queue_send(data, channel)

    def disconnect(self) -> None:
        """Close the connection and reset connection state flags."""
        self._connected = False
        self._connecting = False
        self._peer.close()

    def reconnect(self) -> None:
        """Close the current socket and start a new non-blocking connection
        attempt to the same host and port."""
        self._peer.close()
        self._connected = False
        self._connecting = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        self._peer = TcpConnection(sock, self._peer.peer_id)
        try:
            sock.connect((self._host, self._port))
        except BlockingIOError:
            pass
