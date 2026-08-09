"""
Shared TCP framing/connection code used by both the plain-TCP and dual
TCP+UDP transport backends.

Frame format (per message), used identically by both backends' TCP path:
  [4 bytes] payload length  — big-endian uint32
  [1 byte]  channel         — CHANNEL_RELIABLE or CHANNEL_UNRELIABLE
  [N bytes] payload
"""
from __future__ import annotations

import select
import socket
import struct
from collections import deque
from typing import Callable
from uuid import UUID, uuid4

from engine.transport import ConnectEvent, DisconnectEvent, Frame, TransportEvent

TCP_HEADER = struct.Struct("!IB")   # uint32 length + uint8 channel = 5 bytes


def encode_frame(data: bytes, channel: int) -> bytes:
    """Wrap a payload in the shared TCP frame header."""
    return TCP_HEADER.pack(len(data), channel) + data


class RecvBuffer:
    """Accumulates raw bytes from non-blocking reads; yields complete messages."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> None:
        """Append raw bytes received from the socket to the internal buffer.

        Parameters
        ----------
        chunk : bytes
            Raw bytes read from the socket to append to the buffer.
        """
        self._buf.extend(chunk)

    def messages(self) -> list[Frame]:
        """Extract all complete messages currently available in the buffer.

        Returns
        -------
        list[Frame]
            One frame per fully-received message. Consumed bytes are
            removed from the internal buffer.
        """
        out: list[Frame] = []
        while len(self._buf) >= TCP_HEADER.size:
            length, channel = TCP_HEADER.unpack_from(self._buf)
            total = TCP_HEADER.size + length
            if len(self._buf) < total:
                break
            payload = bytes(self._buf[TCP_HEADER.size:total])
            del self._buf[:total]
            out.append(Frame(channel, payload))
        return out


class TcpConnection:
    """A single TCP connection: send queue, recv buffer, and framed I/O."""

    def __init__(self, sock: socket.socket, peer_id: UUID) -> None:
        self.sock = sock
        self.peer_id = peer_id
        self.recv_buf = RecvBuffer()
        self._send_queue: deque[bytes] = deque()

    def queue_send(self, data: bytes, channel: int) -> None:
        """Encode a payload and enqueue it for sending on the next flush.

        Parameters
        ----------
        data : bytes
            Payload to send to the peer.
        channel : int
            Channel identifier (e.g. ``CHANNEL_RELIABLE``) to tag the frame with.
        """
        self._send_queue.append(encode_frame(data, channel))

    def queue_encoded(self, frame: bytes) -> None:
        """Enqueue an already-encoded frame (e.g. one shared across a broadcast)."""
        self._send_queue.append(frame)

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

    def read(self) -> list[Frame] | None:
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
        """Close the underlying socket, ignoring any errors."""
        try:
            self.sock.close()
        except OSError:
            pass


def poll_connecting(
    sock: socket.socket,
    peer_id: UUID,
    timeout: float,
    guard_select_oserror: bool = False,
) -> tuple[bool, ConnectEvent | DisconnectEvent | None]:
    """Advance one step of a non-blocking connect() attempt.

    Parameters
    ----------
    guard_select_oserror : bool, optional
        If True, an OSError from ``select.select`` is treated as a failed
        connection (a DisconnectEvent) instead of propagating (default False).

    Returns
    -------
    tuple[bool, ConnectEvent | DisconnectEvent | None]
        ``(still_connecting, event)`` — event is a ConnectEvent on success,
        a DisconnectEvent on failure, or None while still waiting.
    """
    try:
        _, writable, exceptional = select.select([], [sock], [sock], timeout)
    except OSError:
        if not guard_select_oserror:
            raise
        return False, DisconnectEvent(peer_id)
    if exceptional:
        return False, DisconnectEvent(peer_id)
    if writable:
        err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            return False, DisconnectEvent(peer_id)
        return False, ConnectEvent(peer_id)
    return True, None


def accept_and_register(
    listen_sock: socket.socket,
    peers: dict[UUID, TcpConnection],
    sock_index: dict[int, TcpConnection],
    select_list: list[socket.socket],
    max_clients: int,
    peer_factory: Callable[[socket.socket, UUID], TcpConnection] = TcpConnection,
) -> TcpConnection | None:
    """Accept one pending connection on `listen_sock` and register it.

    Returns
    -------
    TcpConnection or None
        The newly registered connection, or None if there was nothing to
        accept or the server is already at `max_clients`.
    """
    try:
        conn, _ = listen_sock.accept()
    except OSError:
        return None
    if len(peers) >= max_clients:
        conn.close()
        return None
    conn.setblocking(False)
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    pid = uuid4()
    peer = peer_factory(conn, pid)
    peers[pid] = peer
    sock_index[conn.fileno()] = peer
    select_list.append(conn)
    return peer
