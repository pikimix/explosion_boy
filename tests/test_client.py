"""Tests for GameClient's handling of server messages."""

import time

from net.client import GameClient
from net.protocol import RejectMsg


class _FakeClientTransport:
    """Idle transport: never has events; only used so GameClient's net
    thread has something inert to poll while we drive it directly."""

    connected = True

    def poll(self, timeout: float = 0):
        time.sleep(min(timeout, 0.01))
        return []

    def send(self, data, channel):
        pass

    def disconnect(self):
        self.connected = False

    def reconnect(self):
        pass


def test_reject_msg_sets_reject_reason_and_stops_client():
    """Receiving a RejectMsg (e.g. protocol version mismatch) records the
    reason so the lobby scene can surface it, and stops the net thread."""
    client = GameClient(_FakeClientTransport())
    try:
        assert client.reject_reason is None

        client._handle_msg(RejectMsg(reason="Protocol version mismatch: client=1, server=2"))

        assert client.reject_reason == "Protocol version mismatch: client=1, server=2"
        assert client._running is False
    finally:
        client.stop()
