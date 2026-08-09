"""Tests for GameClient's handling of server messages."""

from net.client import GameClient
from net.protocol import RejectMsg


def test_reject_msg_sets_reject_reason_and_stops_client(fake_client_transport):
    """Receiving a RejectMsg (e.g. protocol version mismatch) records the
    reason so the lobby scene can surface it, and stops the net thread."""
    client = GameClient(fake_client_transport)
    try:
        assert client.reject_reason is None

        client._handle_msg(RejectMsg(reason="Protocol version mismatch: client=1, server=2"))

        assert client.reject_reason == "Protocol version mismatch: client=1, server=2"
        assert client._running is False
    finally:
        client.stop()
