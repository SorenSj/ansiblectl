"""Address-bound HTTPS transport tests without public network access."""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass, field
from typing import cast

import pytest

from ansiblectl.domain.secrets import SecretMaterial
from ansiblectl.domain.webhooks import (
    WebhookDestination,
    WebhookEndpoint,
    WebhookRequest,
    parse_webhook_endpoints,
)
from ansiblectl.infrastructure import https_webhook_transport as transport_module
from ansiblectl.infrastructure.https_webhook_transport import (
    MAX_WEBHOOK_RESPONSE_BYTES,
    BoundHttpsWebhookTransport,
    SocketAddressResolver,
)


def endpoint() -> WebhookEndpoint:
    document = {
        "schema_version": 1,
        "endpoints": {
            "audit": {
                "url": "https://hooks.example.test:8443/events?source=ansiblectl",
                "allowed_hostnames": ["hooks.example.test"],
                "connect_timeout_seconds": 4,
                "read_timeout_seconds": 9,
            }
        },
    }
    return parse_webhook_endpoints(document, "test")["audit"]


@dataclass
class Response:
    status: int = 202
    reads: list[int | None] = field(default_factory=list)

    def read(self, amount: int | None = None) -> bytes:
        self.reads.append(amount)
        return b"private response body"


@dataclass
class Connection:
    response: Response = field(default_factory=Response)
    requests: list[tuple[str, str, bytes | None, dict[str, str]]] = field(default_factory=list)
    closed: bool = False

    def request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        headers: object = None,
    ) -> None:
        self.requests.append((method, url, body, dict(cast(dict[str, str], headers))))

    def getresponse(self) -> Response:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_transport_posts_once_with_bounded_read_and_no_redirect_following() -> None:
    connection = Connection(Response(status=302))
    calls: list[tuple[WebhookEndpoint, WebhookDestination]] = []

    def factory(selected: WebhookEndpoint, destination: WebhookDestination) -> Connection:
        calls.append((selected, destination))
        return connection

    request = WebhookRequest(
        b'{"safe":true}',
        {"Content-Type": "application/json", "Idempotency-Key": "event"},
        SecretMaterial("credential-value"),
    )
    destination = WebhookDestination("hooks.example.test", 8443, ("8.8.8.8",))

    status = BoundHttpsWebhookTransport(factory).post(endpoint(), destination, request)

    assert status == 302
    assert calls == [(endpoint(), destination)]
    assert connection.requests == [
        (
            "POST",
            "/events?source=ansiblectl",
            b'{"safe":true}',
            {
                "Authorization": "Bearer credential-value",
                "Content-Type": "application/json",
                "Idempotency-Key": "event",
            },
        )
    ]
    assert connection.response.reads == [MAX_WEBHOOK_RESPONSE_BYTES + 1]
    assert connection.closed is True


def test_transport_always_closes_and_rejects_header_injection() -> None:
    connection = Connection()
    request = WebhookRequest(b"{}", {}, SecretMaterial("unsafe\rvalue"))

    with pytest.raises(ValueError, match="bearer material"):
        BoundHttpsWebhookTransport(lambda endpoint, destination: connection).post(
            endpoint(),
            WebhookDestination("hooks.example.test", 8443, ("8.8.8.8",)),
            request,
        )

    assert connection.requests == []
    assert connection.closed is False


def test_socket_resolver_returns_unique_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, type: [
            (socket.AF_INET, type, 6, "", ("8.8.8.8", port)),
            (socket.AF_INET6, type, 6, "", ("2001:4860:4860::8888", port, 0, 0)),
            (socket.AF_INET, type, 6, "", ("8.8.8.8", port)),
        ],
    )

    assert SocketAddressResolver().resolve("hooks.example.test", 443) == (
        "8.8.8.8",
        "2001:4860:4860::8888",
    )


class RawSocket:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class TlsSocket:
    def __init__(self) -> None:
        self.timeout: int | None = None

    def settimeout(self, timeout: int) -> None:
        self.timeout = timeout


class TlsContext:
    def __init__(self, tls_socket: TlsSocket) -> None:
        self.tls_socket = tls_socket
        self.wraps: list[tuple[RawSocket, str | None]] = []

    def wrap_socket(self, raw_socket: RawSocket, server_hostname: str | None = None) -> TlsSocket:
        self.wraps.append((raw_socket, server_hostname))
        return self.tls_socket


def test_connection_uses_validated_literal_with_original_hostname_for_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_socket = RawSocket()
    tls_socket = TlsSocket()
    context = TlsContext(tls_socket)
    connections: list[tuple[tuple[str, int], object]] = []

    def create_connection(address: tuple[str, int], timeout: object) -> RawSocket:
        connections.append((address, timeout))
        return raw_socket

    monkeypatch.setattr(ssl, "create_default_context", lambda: context)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    selected = endpoint()
    destination = WebhookDestination(selected.hostname, selected.port, ("8.8.8.8",))

    connection = transport_module._make_connection(selected, destination)
    connection.connect()  # type: ignore[attr-defined]

    assert connections == [(("8.8.8.8", 8443), 4)]
    assert context.wraps == [(raw_socket, "hooks.example.test")]
    assert tls_socket.timeout == 9
