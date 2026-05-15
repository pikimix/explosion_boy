"""
TCP backend for the transport abstraction.

Frame format (per message):
  [4 bytes] payload length  — big-endian uint32
  [1 byte]  channel         — CHANNEL_RELIABLE or CHANNEL_UNRELIABLE
  [N bytes] payload

Each connection gets its own RecvBuffer so a slow peer never stalls others.
"""
from __future__ import annotations

import select
import socket
import struct
from collections import deque
from uuid import UUID, uuid4

from platform.transport import (
    CHANNEL_RELIABLE,
    CHANNEL_UNRELIABLE,
    ConnectEvent,
    DisconnectEvent,
    ReceiveEvent,
    TransportEvent,
)

_HEADER = struct.Struct("!IB")   # uint32 length + uint8 channel = 5 bytes


def _encode(data: bytes, channel: int) -> bytes:
    return _HEADER.pack(len(data), channel) + data


class _RecvBuffer:
    """Accumulates raw bytes from non-blocking reads; yields complete messages."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> None:
        self._buf.extend(chunk)

    def messages(self) -> list[tuple[int, bytes]]:
        out: list[tuple[int, bytes]] = []
        while len(self._buf) >= _HEADER.size:
            length, channel = _HEADER.unpack_from(self._buf)
            total = _HEADER.size + length
            if len(self._buf) < total:
                break
            payload = bytes(self._buf[_HEADER.size:total])
            del self._buf[:total]
            out.append((channel, payload))
        return out


class _Peer:
    def __init__(self, sock: socket.socket, peer_id: UUID) -> None:
        self.sock = sock
        self.peer_id = peer_id
        self.recv_buf = _RecvBuffer()
        self._send_queue: deque[bytes] = deque()

    def queue_send(self, data: bytes, channel: int) -> None:
        self._send_queue.append(_encode(data, channel))

    def flush(self) -> bool:
        """Attempt to drain send queue. Returns False if peer disconnected."""
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
        """Non-blocking read. Returns parsed messages, or None on disconnect."""
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

class TCPServerTransport:
    def __init__(self, host: str = "0.0.0.0", port: int = 9000,
                 max_clients: int = 12) -> None:
        self._max_clients = max_clients
        self._peers: dict[UUID, _Peer] = {}
        self._listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen.setblocking(False)
        self._listen.bind((host, port))
        self._listen.listen(max_clients)

    def poll(self) -> list[TransportEvent]:
        events: list[TransportEvent] = []

        readable, _, _ = select.select(
            [self._listen] + [p.sock for p in self._peers.values()], [], [], 0
        )

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
        if peer := self._peers.get(peer_id):
            peer.queue_send(data, channel)

    def broadcast(self, data: bytes,
                  channel: int = CHANNEL_RELIABLE) -> None:
        frame = _encode(data, channel)
        for peer in self._peers.values():
            peer._send_queue.append(frame)

    def disconnect(self, peer_id: UUID) -> None:
        if peer_id in self._peers:
            self._drop(peer_id, [])

    def close(self) -> None:
        for peer in list(self._peers.values()):
            peer.close()
        self._peers.clear()
        try:
            self._listen.close()
        except OSError:
            pass

    def _accept(self, events: list[TransportEvent]) -> None:
        try:
            conn, _ = self._listen.accept()
        except OSError:
            return
        if len(self._peers) >= self._max_clients:
            conn.close()
            return
        conn.setblocking(False)
        pid = uuid4()
        self._peers[pid] = _Peer(conn, pid)
        events.append(ConnectEvent(pid))

    def _recv_from(self, sock: socket.socket,
                   events: list[TransportEvent]) -> None:
        peer = next((p for p in self._peers.values() if p.sock is sock), None)
        if peer is None:
            return
        messages = peer.read()
        if messages is None:
            self._drop(peer.peer_id, events)
            return
        for channel, data in messages:
            events.append(ReceiveEvent(peer.peer_id, channel, data))

    def _drop(self, peer_id: UUID, events: list[TransportEvent]) -> None:
        peer = self._peers.pop(peer_id, None)
        if peer:
            peer.close()
            events.append(DisconnectEvent(peer_id))


# ── Client ─────────────────────────────────────────────────────────────────────

class TCPClientTransport:
    def __init__(self, host: str = "127.0.0.1", port: int = 9000) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setblocking(False)
        self._peer = _Peer(self._sock, uuid4())
        self._connected = False
        self._connecting = True
        try:
            self._sock.connect((host, port))
        except BlockingIOError:
            pass  # connection in progress — expected for non-blocking

    @property
    def connected(self) -> bool:
        return self._connected

    def poll(self) -> list[TransportEvent]:
        events: list[TransportEvent] = []

        if self._connecting:
            _, writable, exceptional = select.select(
                [], [self._sock], [self._sock], 0
            )
            if exceptional:
                self._connecting = False
                events.append(DisconnectEvent(self._peer.peer_id))
                return events
            if writable:
                err = self._sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                self._connecting = False
                if err != 0:
                    events.append(DisconnectEvent(self._peer.peer_id))
                    return events
                self._connected = True
                events.append(ConnectEvent(self._peer.peer_id))
            return events

        if not self._connected:
            return events

        readable, _, _ = select.select([self._sock], [], [], 0)
        if readable:
            messages = self._peer.read()
            if messages is None:
                self._connected = False
                events.append(DisconnectEvent(self._peer.peer_id))
                return events
            for channel, data in messages:
                events.append(ReceiveEvent(self._peer.peer_id, channel, data))

        if not self._peer.flush():
            self._connected = False
            events.append(DisconnectEvent(self._peer.peer_id))

        return events

    def send(self, data: bytes, channel: int = CHANNEL_RELIABLE) -> None:
        if self._connected:
            self._peer.queue_send(data, channel)

    def disconnect(self) -> None:
        self._connected = False
        self._connecting = False
        self._peer.close()
