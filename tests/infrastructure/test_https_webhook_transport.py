"""Address-bound HTTPS transport tests without public network access."""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass, field
from typing import cast

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from OpenSSL import SSL

from ansiblectl.domain.secrets import SecretMaterial
from ansiblectl.domain.webhook_tls_trust import WebhookTlsTrustPolicy
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
from ansiblectl.infrastructure.webhook_client_identity import WebhookClientIdentity


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


def test_transport_selects_only_the_in_memory_factory_for_client_identity() -> None:
    connection = Connection()
    selected = endpoint()
    destination = WebhookDestination("hooks.example.test", 8443, ("8.8.8.8",))
    request = WebhookRequest(
        b"{}",
        {},
        client_identity=WebhookClientIdentity(b"certificate", b"private-key"),
    )
    calls: list[tuple[WebhookEndpoint, WebhookDestination, WebhookRequest]] = []

    def identity_factory(
        endpoint: WebhookEndpoint,
        destination: WebhookDestination,
        request: WebhookRequest,
    ) -> Connection:
        calls.append((endpoint, destination, request))
        return connection

    transport = BoundHttpsWebhookTransport(
        lambda endpoint, destination: pytest.fail("standard TLS path must not be used"),
        identity_factory,
    )

    assert transport.post(selected, destination, request) == 202
    assert calls == [(selected, destination, request)]
    assert connection.closed is True


@pytest.mark.parametrize(
    ("pattern", "hostname", "matches"),
    [
        ("hooks.example.test", "hooks.example.test", True),
        ("hooks.example.test", "other.example.test", False),
        ("*.example.test", "hooks.example.test", True),
        ("*.example.test", "nested.hooks.example.test", False),
        ("h*oks.example.test", "hooks.example.test", False),
        ("*.*.test", "hooks.example.test", False),
    ],
)
def test_in_memory_hostname_matching_is_exact_or_one_label_wildcard(
    pattern: str, hostname: str, matches: bool
) -> None:
    assert transport_module._dns_name_matches(pattern, hostname) is matches


def test_in_memory_context_loads_identity_chain_and_platform_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Identity:
        def reveal_for_transport(self) -> tuple[bytes, bytes]:
            return b"certificate-chain", b"private-key"

    class Context:
        def __init__(self, method: object) -> None:
            self.calls: list[tuple[str, object]] = [("method", method)]

        def set_min_proto_version(self, version: object) -> None:
            self.calls.append(("minimum", version))

        def set_verify(self, mode: object, callback: object) -> None:
            self.calls.append(("verify", (mode, callback)))

        def set_default_verify_paths(self) -> None:
            self.calls.append(("platform", True))

        def use_certificate(self, certificate: object) -> None:
            self.calls.append(("leaf", certificate))

        def use_privatekey(self, private_key: object) -> None:
            self.calls.append(("key", private_key))

        def add_extra_chain_cert(self, certificate: object) -> None:
            self.calls.append(("chain", certificate))

        def check_privatekey(self) -> None:
            self.calls.append(("matched", True))

    contexts: list[Context] = []

    def context_factory(method: object) -> Context:
        context = Context(method)
        contexts.append(context)
        return context

    monkeypatch.setattr(SSL, "Context", context_factory)
    monkeypatch.setattr(
        x509,
        "load_pem_x509_certificates",
        lambda value: ["leaf", "intermediate"],
    )
    monkeypatch.setattr(
        serialization,
        "load_pem_private_key",
        lambda value, password: "parsed-key",
    )
    request = WebhookRequest(b"{}", {}, client_identity=Identity())

    context = transport_module._make_identity_tls_context(endpoint(), request)

    assert context is not None
    assert len(contexts) == 1
    assert contexts[0].calls == [
        ("method", SSL.TLS_CLIENT_METHOD),
        ("minimum", SSL.TLS1_2_VERSION),
        ("verify", (SSL.VERIFY_PEER, None)),
        ("platform", True),
        ("leaf", "leaf"),
        ("key", "parsed-key"),
        ("chain", "intermediate"),
        ("matched", True),
    ]


def test_in_memory_context_rejects_a_missing_identity() -> None:
    with pytest.raises(ValueError, match="identity"):
        transport_module._make_identity_tls_context(endpoint(), WebhookRequest(b"{}", {}))


def test_in_memory_peer_hostname_requires_matching_dns_san() -> None:
    class AlternativeNames:
        def get_values_for_type(self, kind: object) -> list[str]:
            assert kind is x509.DNSName
            return ["hooks.example.test"]

    class Extensions:
        def get_extension_for_class(self, kind: object) -> object:
            assert kind is x509.SubjectAlternativeName
            return type("Extension", (), {"value": AlternativeNames()})()

    class Certificate:
        extensions = Extensions()

    class Peer:
        def to_cryptography(self) -> Certificate:
            return Certificate()

    class ConnectionWithPeer:
        def get_peer_certificate(self) -> Peer:
            return Peer()

    connection = cast(SSL.Connection, ConnectionWithPeer())
    transport_module._verify_peer_hostname(connection, "hooks.example.test")
    with pytest.raises(ssl.CertificateError, match="hostname"):
        transport_module._verify_peer_hostname(connection, "other.example.test")


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


class ExclusiveTlsContext(TlsContext):
    def __init__(self, protocol: object, tls_socket: TlsSocket) -> None:
        super().__init__(tls_socket)
        self.protocol = protocol
        self.verify_mode: object = None
        self.check_hostname = False
        self.loaded: list[str] = []

    def load_verify_locations(self, *, cadata: str) -> None:
        self.loaded.append(cadata)


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


def test_exclusive_context_loads_only_snapshot_and_keeps_mandatory_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tls_socket = TlsSocket()
    contexts: list[ExclusiveTlsContext] = []

    def context_factory(protocol: object) -> ExclusiveTlsContext:
        context = ExclusiveTlsContext(protocol, tls_socket)
        contexts.append(context)
        return context

    monkeypatch.setattr(ssl, "SSLContext", context_factory)
    monkeypatch.setattr(
        ssl,
        "create_default_context",
        lambda: pytest.fail("exclusive trust must not load platform roots"),
    )
    selected = endpoint()
    object.__setattr__(
        selected,
        "tls_trust_policy",
        WebhookTlsTrustPolicy(
            "sentinel", b"-----BEGIN CERTIFICATE-----\nAA==\n-----END CERTIFICATE-----\n"
        ),
    )

    connection = transport_module._make_connection(
        selected, WebhookDestination(selected.hostname, selected.port, ("8.8.8.8",))
    )

    assert connection is not None
    assert len(contexts) == 1
    assert contexts[0].protocol == ssl.PROTOCOL_TLS_CLIENT
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert contexts[0].check_hostname is True
    assert contexts[0].loaded == ["-----BEGIN CERTIFICATE-----\nAA==\n-----END CERTIFICATE-----\n"]


def test_exclusive_context_failure_never_loads_platform_roots_or_opens_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingContext(ExclusiveTlsContext):
        def load_verify_locations(self, *, cadata: str) -> None:
            self.loaded.append(cadata)
            raise RuntimeError("sentinel-policy path certificate subject TLS alert")

    contexts: list[FailingContext] = []

    def context_factory(protocol: object) -> FailingContext:
        context = FailingContext(protocol, TlsSocket())
        contexts.append(context)
        return context

    monkeypatch.setattr(ssl, "SSLContext", context_factory)
    monkeypatch.setattr(
        ssl,
        "create_default_context",
        lambda: pytest.fail("exclusive trust must not fall back to platform roots"),
    )
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: pytest.fail("context failure must happen before socket I/O"),
    )
    selected = endpoint()
    object.__setattr__(
        selected,
        "tls_trust_policy",
        WebhookTlsTrustPolicy(
            "sentinel-policy",
            b"-----BEGIN CERTIFICATE-----\nAA==\n-----END CERTIFICATE-----\n",
        ),
    )

    with pytest.raises(RuntimeError, match="sentinel-policy"):
        BoundHttpsWebhookTransport().post(
            selected,
            WebhookDestination(selected.hostname, selected.port, ("8.8.8.8",)),
            WebhookRequest(b"{}", {}),
        )

    assert len(contexts) == 1
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert contexts[0].check_hostname is True
