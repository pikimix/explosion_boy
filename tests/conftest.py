"""Shared fake transports for net/ tests."""
from __future__ import annotations

import time

import pytest


class FakeServerTransport:
    """In-memory ServerTransport double: records sends/disconnects, never has
    pending events on its own (tests drive the server directly via
    `_on_receive` instead of relying on `poll`)."""

    def __init__(self) -> None:
        self.sent: list[tuple] = []
        self.disconnected: list = []

    def poll(self, timeout: float = 0):
        """Return no pending events, satisfying the transport polling interface."""
        return []

    def send(self, peer_id, data, channel):
        self.sent.append((peer_id, data, channel))

    def broadcast(self, data, channel):
        pass

    def disconnect(self, peer_id):
        self.disconnected.append(peer_id)


class FakeClientTransport:
    """Idle ClientTransport double: never has events; only used so
    GameClient's net thread has something inert to poll while driven
    directly in a test."""

    def __init__(self) -> None:
        self.connected = True

    def poll(self, timeout: float = 0):
        time.sleep(min(timeout, 0.01))
        return []

    def send(self, data, channel):
        pass

    def disconnect(self):
        self.connected = False

    def reconnect(self):
        pass


@pytest.fixture
def fake_server_transport() -> FakeServerTransport:
    return FakeServerTransport()


@pytest.fixture
def fake_client_transport() -> FakeClientTransport:
    return FakeClientTransport()
