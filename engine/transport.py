"""
Transport abstraction layer.

Game code depends only on ServerTransport / ClientTransport Protocol and the
event types below. Concrete implementations live in platform/transports/.
Swap backend by changing the argument to make_server_transport() /
make_client_transport() — nothing else needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

# ── Channel constants ──────────────────────────────────────────────────────────
# Both constants are meaningful to every backend. For TCP the distinction is
# advisory: all traffic is reliable, but CHANNEL_UNRELIABLE messages are tagged
# so the receiver can discard stale ones (same semantics as a true unreliable
# channel). A real UDP backend (ENet etc.) maps these to distinct channels.
CHANNEL_RELIABLE   = 0   # game events — must arrive, must arrive in order
CHANNEL_UNRELIABLE = 1   # state snapshots — only latest matters


# ── Transport events ───────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ConnectEvent:
    peer_id: UUID

@dataclass(frozen=True, slots=True)
class DisconnectEvent:
    peer_id: UUID

@dataclass(frozen=True, slots=True)
class ReceiveEvent:
    peer_id: UUID
    channel: int
    data: bytes

TransportEvent = ConnectEvent | DisconnectEvent | ReceiveEvent


# ── Protocols (the engine contract) ───────────────────────────────────────────
@runtime_checkable
class ServerTransport(Protocol):
    """Non-blocking server-side transport. Call poll() each game tick."""

    def poll(self) -> list[TransportEvent]:
        """Return all pending events (connects, disconnects, received data).
        Never blocks."""
        ...

    def send(self, peer_id: UUID, data: bytes,
             channel: int = CHANNEL_RELIABLE) -> None:
        """Send data to one peer."""
        ...

    def broadcast(self, data: bytes,
                  channel: int = CHANNEL_RELIABLE) -> None:
        """Send data to every connected peer."""
        ...

    def disconnect(self, peer_id: UUID) -> None: ...
    def close(self) -> None: ...


@runtime_checkable
class ClientTransport(Protocol):
    """Non-blocking client-side transport. Call poll() each frame."""

    @property
    def connected(self) -> bool: ...

    def poll(self) -> list[TransportEvent]:
        """Return all pending events (connect confirmation, disconnects,
        received data). Never blocks."""
        ...

    def send(self, data: bytes, channel: int = CHANNEL_RELIABLE) -> None: ...
    def disconnect(self) -> None: ...


# ── Factory ────────────────────────────────────────────────────────────────────
def make_server_transport(backend: str = "tcp", **kwargs) -> ServerTransport:
    """Instantiate a server transport by name. kwargs forwarded to constructor.

    Supported backends:
      "tcp"  — TCPServerTransport(host, port, max_clients)
    """
    if backend == "tcp":
        from engine.transports.tcp import TCPServerTransport
        return TCPServerTransport(**kwargs)
    raise ValueError(f"Unknown transport backend: {backend!r}")


def make_client_transport(backend: str = "tcp", **kwargs) -> ClientTransport:
    """Instantiate a client transport by name.

    Supported backends:
      "tcp"  — TCPClientTransport(host, port)
    """
    if backend == "tcp":
        from engine.transports.tcp import TCPClientTransport
        return TCPClientTransport(**kwargs)
    raise ValueError(f"Unknown transport backend: {backend!r}")
