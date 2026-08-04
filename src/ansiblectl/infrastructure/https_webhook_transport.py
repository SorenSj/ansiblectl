"""Address-bound standard-library HTTPS transport for webhook delivery."""

from __future__ import annotations

import http.client
import socket
import ssl
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from OpenSSL import SSL, crypto

from ansiblectl.domain.webhooks import (
    WebhookDestination,
    WebhookEndpoint,
    WebhookRequest,
)

MAX_WEBHOOK_RESPONSE_BYTES = 4_096


class WebhookHttpResponse(Protocol):
    status: int

    def read(self, amount: int | None = None) -> bytes: ...


class WebhookHttpsConnection(Protocol):
    def request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None: ...

    def getresponse(self) -> WebhookHttpResponse: ...

    def close(self) -> None: ...


class SocketAddressResolver:
    """Resolve stream addresses without retaining resolver metadata."""

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        addresses: list[str] = []
        for record in records:
            address = str(record[4][0])
            if address not in addresses:
                addresses.append(address)
        return tuple(addresses)


class _BoundHttpsConnection(http.client.HTTPSConnection):
    """Connect to validated literals while authenticating the original DNS hostname."""

    def __init__(
        self,
        destination: WebhookDestination,
        *,
        connect_timeout: int,
        read_timeout: int,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(
            destination.hostname,
            destination.port,
            timeout=connect_timeout,
            context=context,
        )
        self._webhook_context = context
        self._validated_addresses = destination.addresses
        self._read_timeout = read_timeout

    def connect(self) -> None:
        last_error: OSError | None = None
        for address in self._validated_addresses:
            raw_socket: socket.socket | None = None
            try:
                raw_socket = socket.create_connection((address, self.port), self.timeout)
                self.sock = self._webhook_context.wrap_socket(raw_socket, server_hostname=self.host)
                self.sock.settimeout(self._read_timeout)
                return
            except OSError as error:
                last_error = error
                if raw_socket is not None:
                    raw_socket.close()
        if last_error is None:
            raise OSError("No validated webhook destination address is available.")
        raise OSError("Webhook destination connection failed.") from last_error


def _make_connection(
    endpoint: WebhookEndpoint, destination: WebhookDestination
) -> WebhookHttpsConnection:
    context = _make_tls_context(endpoint)
    return cast(
        WebhookHttpsConnection,
        _BoundHttpsConnection(
            destination,
            connect_timeout=endpoint.connect_timeout_seconds,
            read_timeout=endpoint.read_timeout_seconds,
            context=context,
        ),
    )


class _MemoryIdentityHttpsConnection(http.client.HTTPConnection):
    """Address-bound HTTP connection upgraded with an in-memory OpenSSL identity."""

    def __init__(
        self,
        endpoint: WebhookEndpoint,
        destination: WebhookDestination,
        request: WebhookRequest,
    ) -> None:
        super().__init__(
            destination.hostname,
            destination.port,
            timeout=endpoint.connect_timeout_seconds,
        )
        if request.client_identity is None:
            raise ValueError("Webhook client identity is unavailable.")
        self._context = _make_identity_tls_context(endpoint, request)
        self._validated_addresses = destination.addresses
        self._read_timeout = endpoint.read_timeout_seconds
        self._raw_socket: socket.socket | None = None

    def connect(self) -> None:
        last_error: Exception | None = None
        for address in self._validated_addresses:
            raw_socket: socket.socket | None = None
            tls_socket: SSL.Connection | None = None
            try:
                raw_socket = socket.create_connection((address, self.port), self.timeout)
                raw_socket.settimeout(self._read_timeout)
                tls_socket = SSL.Connection(self._context, raw_socket)
                tls_socket.set_connect_state()
                tls_socket.set_tlsext_host_name(self.host.encode("ascii"))
                tls_socket.do_handshake()
                _verify_peer_hostname(tls_socket, self.host)
                self._raw_socket = raw_socket
                self.sock = tls_socket
                return
            except Exception as error:
                last_error = error
                if tls_socket is not None:
                    with suppress(Exception):
                        tls_socket.shutdown()
                if raw_socket is not None:
                    raw_socket.close()
        if last_error is None:
            raise OSError("No validated webhook destination address is available.")
        raise OSError("Webhook destination TLS connection failed.") from last_error

    def close(self) -> None:
        tls_socket = self.sock
        self.sock = None
        if isinstance(tls_socket, SSL.Connection):
            with suppress(Exception):
                tls_socket.shutdown()
        if self._raw_socket is not None:
            self._raw_socket.close()
            self._raw_socket = None


def _make_identity_connection(
    endpoint: WebhookEndpoint,
    destination: WebhookDestination,
    request: WebhookRequest,
) -> WebhookHttpsConnection:
    return cast(
        WebhookHttpsConnection,
        _MemoryIdentityHttpsConnection(endpoint, destination, request),
    )


def _make_identity_tls_context(endpoint: WebhookEndpoint, request: WebhookRequest) -> SSL.Context:
    if request.client_identity is None:
        raise ValueError("Webhook client identity is unavailable.")
    certificate_pem, private_key_pem = request.client_identity.reveal_for_transport()
    certificates = x509.load_pem_x509_certificates(certificate_pem)
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    context = SSL.Context(SSL.TLS_CLIENT_METHOD)
    context.set_min_proto_version(SSL.TLS1_2_VERSION)
    context.set_verify(SSL.VERIFY_PEER, None)
    if endpoint.tls_trust_policy is None:
        context.set_default_verify_paths()
    else:
        store = context.get_cert_store()
        if store is None:
            raise ssl.SSLError("Webhook TLS trust store is unavailable.")
        for certificate in x509.load_pem_x509_certificates(endpoint.tls_trust_policy.ca_pem):
            store.add_cert(crypto.X509.from_cryptography(certificate))
    context.use_certificate(certificates[0])
    context.use_privatekey(private_key)  # type: ignore[arg-type]
    for certificate in certificates[1:]:
        context.add_extra_chain_cert(certificate)
    context.check_privatekey()
    return context


def _verify_peer_hostname(connection: SSL.Connection, hostname: str) -> None:
    peer = connection.get_peer_certificate()
    if peer is None:
        raise ssl.CertificateError("Webhook server certificate is unavailable.")
    certificate = peer.to_cryptography()
    names: list[tuple[str, str]] = []
    try:
        extension = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        pass
    else:
        names.extend(("DNS", name) for name in extension.value.get_values_for_type(x509.DNSName))
    candidates = [name for _, name in names]
    if not candidates:
        candidates = [
            attribute.value
            for attribute in certificate.subject.get_attributes_for_oid(
                x509.oid.NameOID.COMMON_NAME
            )
            if isinstance(attribute.value, str)
        ]
    if not any(_dns_name_matches(candidate, hostname) for candidate in candidates):
        raise ssl.CertificateError("Webhook server certificate hostname does not match.")


def _dns_name_matches(pattern: str, hostname: str) -> bool:
    pattern = pattern.lower()
    hostname = hostname.lower()
    if "*" not in pattern:
        return pattern == hostname
    if not pattern.startswith("*.") or pattern.count("*") != 1:
        return False
    pattern_labels = pattern.split(".")
    hostname_labels = hostname.split(".")
    return len(pattern_labels) == len(hostname_labels) and pattern_labels[1:] == hostname_labels[1:]


def _make_tls_context(endpoint: WebhookEndpoint) -> ssl.SSLContext:
    policy = endpoint.tls_trust_policy
    if policy is None:
        return ssl.create_default_context()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.load_verify_locations(cadata=policy.ca_pem.decode("ascii"))
    return context


@dataclass(frozen=True)
class BoundHttpsWebhookTransport:
    """POST once without redirects, proxies, retries, or unbounded response reads."""

    connection_factory: Callable[[WebhookEndpoint, WebhookDestination], WebhookHttpsConnection] = (
        _make_connection
    )
    identity_connection_factory: Callable[
        [WebhookEndpoint, WebhookDestination, WebhookRequest], WebhookHttpsConnection
    ] = _make_identity_connection

    def post(
        self,
        endpoint: WebhookEndpoint,
        destination: WebhookDestination,
        request: WebhookRequest,
    ) -> int:
        target = urlsplit(endpoint.url)
        request_target = target.path or "/"
        if target.query:
            request_target = f"{request_target}?{target.query}"
        headers = dict(request.headers)
        if request.bearer_material is not None:
            material = request.bearer_material.reveal_for_operation()
            if not material or "\r" in material or "\n" in material:
                raise ValueError("Webhook bearer material is invalid.")
            headers["Authorization"] = f"Bearer {material}"
        if request.client_identity is None:
            connection = self.connection_factory(endpoint, destination)
        else:
            connection = self.identity_connection_factory(endpoint, destination, request)
        try:
            connection.request("POST", request_target, body=request.body, headers=headers)
            response = connection.getresponse()
            response.read(MAX_WEBHOOK_RESPONSE_BYTES + 1)
            return response.status
        finally:
            connection.close()


__all__ = [
    "BoundHttpsWebhookTransport",
    "MAX_WEBHOOK_RESPONSE_BYTES",
    "SocketAddressResolver",
]
