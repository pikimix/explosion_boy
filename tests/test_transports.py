"""Integration tests for the real socket-based transport backends.

Unlike the rest of net/'s test suite — which drives GameServer/GameClient/
LobbyManager through hand-written fakes (see tests/conftest.py) and never
touches engine/transports/*.py at all — these tests exercise actual TCP/UDP
sockets on localhost, covering the code the Phase D transport-layer dedup
(engine/transports/_shared.py, tcp.py, dual.py) actually changed.

Real sockets need a handful of non-blocking poll() calls to advance a
connect/accept/send — unlike the fakes, there's real (if tiny) I/O latency.
`_poll_until` polls in a loop and returns as soon as a condition is met
rather than a fixed number of times, so these stay fast in the common case
while tolerating slower CI environments.
"""
from __future__ import annotations

import socket

from engine.transport import (
    CHANNEL_RELIABLE,
    CHANNEL_UNRELIABLE,
    ConnectEvent,
    DisconnectEvent,
    ReceiveEvent,
)
from engine.transports.dual import DualClientTransport, DualServerTransport
from engine.transports.tcp import TCPClientTransport, TCPServerTransport


def _free_port() -> int:
    """Ask the OS for a currently-unused localhost port."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]
    finally:
        probe.close()


def _poll_until(transport, predicate, timeout: float = 0.02, max_rounds: int = 100) -> list:
    """Poll `transport` until `predicate(events_seen_so_far)` is true.

    Returns whatever events were collected, whether or not the predicate
    was ever satisfied (callers assert on the outcome themselves, so a
    failure points at a real assertion instead of a bare timeout).
    """
    events: list = []
    for _ in range(max_rounds):
        events.extend(transport.poll(timeout))
        if predicate(events):
            break
    return events


def _has(events: list, cls: type) -> bool:
    return any(isinstance(e, cls) for e in events)


def _connect(server, client) -> object:
    """Drive both sides through the connect handshake. Returns the peer_id
    the server assigned, as seen in its ConnectEvent."""
    server_events = _poll_until(server, lambda evs: _has(evs, ConnectEvent))
    connect = next((e for e in server_events if isinstance(e, ConnectEvent)), None)
    assert connect is not None, "server never saw a ConnectEvent"

    _poll_until(client, lambda evs: client.connected)
    assert client.connected, "client never reached connected state"

    return connect.peer_id


def _wait_for_data(
    sender, receiver, data: bytes, timeout: float = 0.02, max_rounds: int = 100
) -> ReceiveEvent | None:
    """Poll both sides until `data` arrives on `receiver`.

    A queued send only actually goes out on the wire once something polls
    the sender (poll() is what flushes its outbound queue), so both sides
    need polling — polling only the receiver leaves the send stuck queued
    forever.
    """
    events: list = []
    for _ in range(max_rounds):
        sender.poll(timeout)
        events.extend(receiver.poll(timeout))
        found = next((e for e in events if isinstance(e, ReceiveEvent) and e.data == data), None)
        if found is not None:
            return found
    return None


def _shutdown(*transports) -> None:
    for t in transports:
        try:
            if hasattr(t, "close"):
                t.close()
            else:
                t.disconnect()
        except OSError:
            pass


class TestTcpBackend:
    """engine.transports.tcp — plain TCP for both channels."""

    def test_client_connects_and_exchanges_data(self):
        port = _free_port()
        server = TCPServerTransport(host='127.0.0.1', port=port)
        client = TCPClientTransport(host='127.0.0.1', port=port)
        try:
            peer_id = _connect(server, client)

            client.send(b'hello', CHANNEL_RELIABLE)
            received = _wait_for_data(client, server, b'hello')
            assert received is not None
            assert received.peer_id == peer_id

            server.send(peer_id, b'world', CHANNEL_RELIABLE)
            assert _wait_for_data(server, client, b'world') is not None
        finally:
            _shutdown(client, server)

    def test_broadcast_reaches_all_connected_peers(self):
        port = _free_port()
        server = TCPServerTransport(host='127.0.0.1', port=port)
        client_a = TCPClientTransport(host='127.0.0.1', port=port)
        try:
            _connect(server, client_a)
            client_b = TCPClientTransport(host='127.0.0.1', port=port)
            try:
                _connect(server, client_b)

                server.broadcast(b'to-everyone', CHANNEL_RELIABLE)

                assert _wait_for_data(server, client_a, b'to-everyone') is not None
                assert _wait_for_data(server, client_b, b'to-everyone') is not None
            finally:
                _shutdown(client_b)
        finally:
            _shutdown(client_a, server)

    def test_client_disconnect_is_seen_by_server(self):
        port = _free_port()
        server = TCPServerTransport(host='127.0.0.1', port=port)
        client = TCPClientTransport(host='127.0.0.1', port=port)
        try:
            peer_id = _connect(server, client)

            client.disconnect()

            events = _poll_until(server, lambda evs: _has(evs, DisconnectEvent))
            assert any(isinstance(e, DisconnectEvent) and e.peer_id == peer_id for e in events)
        finally:
            _shutdown(server)

    def test_server_disconnect_is_seen_by_client(self):
        port = _free_port()
        server = TCPServerTransport(host='127.0.0.1', port=port)
        client = TCPClientTransport(host='127.0.0.1', port=port)
        try:
            peer_id = _connect(server, client)

            server.disconnect(peer_id)

            events = _poll_until(client, lambda evs: _has(evs, DisconnectEvent))
            assert _has(events, DisconnectEvent)
        finally:
            _shutdown(client, server)


class TestDualBackend:
    """engine.transports.dual — TCP for reliable, UDP for unreliable."""

    def test_client_connects_and_exchanges_data_over_tcp_channel(self):
        port = _free_port()
        server = DualServerTransport(host='127.0.0.1', port=port)
        client = DualClientTransport(host='127.0.0.1', port=port)
        try:
            peer_id = _connect(server, client)

            client.send(b'hello', CHANNEL_RELIABLE)
            received = _wait_for_data(client, server, b'hello')
            assert received is not None
            assert received.peer_id == peer_id
            assert received.channel == CHANNEL_RELIABLE

            server.send(peer_id, b'world', CHANNEL_RELIABLE)
            assert _wait_for_data(server, client, b'world') is not None
        finally:
            _shutdown(client, server)

    def test_unreliable_channel_actually_uses_udp_once_registered(self):
        port = _free_port()
        server = DualServerTransport(host='127.0.0.1', port=port)
        client = DualClientTransport(host='127.0.0.1', port=port)
        try:
            peer_id = _connect(server, client)

            # CHANNEL_UNRELIABLE silently falls back to TCP until the UDP
            # registration handshake completes, so checking these private
            # fields (rather than just "did the data arrive") is the only
            # way to confirm this test actually exercises the UDP path
            # instead of the fallback.
            for _ in range(100):
                if client._peer_uuid is not None and server._peers[peer_id].udp_addr is not None:
                    break
                server.poll(0.02)
                client.poll(0.02)
            assert client._peer_uuid is not None, "client never learned its peer uuid"
            assert server._peers[peer_id].udp_addr is not None, "server never registered client's UDP endpoint"

            client.send(b'snapshot-ish', CHANNEL_UNRELIABLE)
            received = _wait_for_data(client, server, b'snapshot-ish')
            assert received is not None
            assert received.channel == CHANNEL_UNRELIABLE

            server.send(peer_id, b'state-ish', CHANNEL_UNRELIABLE)
            received = _wait_for_data(server, client, b'state-ish')
            assert received is not None
            assert received.channel == CHANNEL_UNRELIABLE
        finally:
            _shutdown(client, server)

    def test_broadcast_reaches_all_connected_peers(self):
        port = _free_port()
        server = DualServerTransport(host='127.0.0.1', port=port)
        client_a = DualClientTransport(host='127.0.0.1', port=port)
        try:
            _connect(server, client_a)
            client_b = DualClientTransport(host='127.0.0.1', port=port)
            try:
                _connect(server, client_b)

                server.broadcast(b'to-everyone', CHANNEL_RELIABLE)

                assert _wait_for_data(server, client_a, b'to-everyone') is not None
                assert _wait_for_data(server, client_b, b'to-everyone') is not None
            finally:
                _shutdown(client_b)
        finally:
            _shutdown(client_a, server)

    def test_client_disconnect_is_seen_by_server(self):
        port = _free_port()
        server = DualServerTransport(host='127.0.0.1', port=port)
        client = DualClientTransport(host='127.0.0.1', port=port)
        try:
            peer_id = _connect(server, client)

            client.disconnect()

            events = _poll_until(server, lambda evs: _has(evs, DisconnectEvent))
            assert any(isinstance(e, DisconnectEvent) and e.peer_id == peer_id for e in events)
        finally:
            _shutdown(server)
