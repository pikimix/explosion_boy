"""Tests for GameServer's connection handling."""

from uuid import uuid4

from net.protocol import JoinMsg, PROTOCOL_VERSION, RejectMsg, decode_any
from net.server import GameServer


class _FakeServerTransport:
    def __init__(self):
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


def test_join_with_mismatched_protocol_version_is_rejected():
    """A client whose protocol version doesn't match the server's is sent a
    RejectMsg and disconnected, without being admitted to the lobby."""
    transport = _FakeServerTransport()
    server = GameServer(transport)
    peer_id = uuid4()

    server._on_receive(peer_id, JoinMsg(player_name="p1", version=PROTOCOL_VERSION - 1).encode())

    assert peer_id in transport.disconnected
    assert len(transport.sent) == 1
    sent_peer, data, _channel = transport.sent[0]
    assert sent_peer == peer_id
    msg = decode_any(data)
    assert isinstance(msg, RejectMsg)
    assert str(PROTOCOL_VERSION - 1) in msg.reason
    assert str(PROTOCOL_VERSION) in msg.reason
    assert server._lobby.peer_to_player_id(peer_id) is None


def test_join_with_matching_protocol_version_is_accepted():
    """A client whose protocol version matches the server's joins the lobby
    and is not disconnected or rejected."""
    transport = _FakeServerTransport()
    server = GameServer(transport)
    peer_id = uuid4()

    server._on_receive(peer_id, JoinMsg(player_name="p1", version=PROTOCOL_VERSION).encode())

    assert peer_id not in transport.disconnected
    assert server._lobby.peer_to_player_id(peer_id) is not None
    assert not any(isinstance(decode_any(data), RejectMsg) for _peer, data, _ch in transport.sent)
