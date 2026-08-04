"""Loopback mutual TLS handshake tests for the in-memory webhook identity path."""

from __future__ import annotations

import socket
import ssl
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from OpenSSL import SSL

from ansiblectl.domain.secrets import SecretMaterial
from ansiblectl.domain.webhook_tls_trust import WebhookTlsTrustPolicy
from ansiblectl.domain.webhooks import (
    WebhookDestination,
    WebhookEndpoint,
    WebhookRequest,
    parse_webhook_endpoints,
)
from ansiblectl.infrastructure.https_webhook_transport import BoundHttpsWebhookTransport
from ansiblectl.infrastructure.webhook_client_identity import validate_webhook_client_identity


@dataclass(frozen=True)
class Authority:
    key: rsa.RSAPrivateKey
    certificate: x509.Certificate


@dataclass
class MutualTlsServer:
    listener: socket.socket
    context: ssl.SSLContext
    peer_certificates: list[object] = field(default_factory=list)
    requests: list[bytes] = field(default_factory=list)
    errors: list[BaseException] = field(default_factory=list)
    accepts: int = 0

    def run_once(self) -> None:
        try:
            raw, _ = self.listener.accept()
            self.accepts += 1
            with raw, self.context.wrap_socket(raw, server_side=True) as connection:
                peer = connection.getpeercert()
                assert peer
                self.peer_certificates.append(peer)
                request = connection.recv(16_384)
                self.requests.append(request)
                connection.sendall(
                    b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
        except BaseException as error:
            self.errors.append(error)
        finally:
            self.listener.close()


def authority(common_name: str) -> Authority:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return Authority(key, certificate)


def issued_identity(
    issuer: Authority,
    common_name: str,
    usage: x509.ObjectIdentifier,
    *,
    dns_name: str | None = None,
) -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer.certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
    )
    if dns_name is not None:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(dns_name)]), critical=False
        )
    certificate = builder.sign(issuer.key, hashes.SHA256())
    return (
        certificate.public_bytes(serialization.Encoding.PEM),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def start_server(
    tmp_path: Path,
    authority_value: Authority,
    server_identity: tuple[bytes, bytes],
) -> tuple[MutualTlsServer, threading.Thread, int]:
    certificate_path = tmp_path / "server-certificate.pem"
    key_path = tmp_path / "server-private-key.pem"
    ca_path = tmp_path / "client-ca.pem"
    certificate_path.write_bytes(server_identity[0])
    key_path.write_bytes(server_identity[1])
    ca_path.write_bytes(authority_value.certificate.public_bytes(serialization.Encoding.PEM))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(certificate_path, key_path)
    context.load_verify_locations(cafile=ca_path)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5)
    server = MutualTlsServer(listener, context)
    thread = threading.Thread(target=server.run_once, daemon=True)
    thread.start()
    return server, thread, int(listener.getsockname()[1])


def selected_endpoint(port: int, ca_pem: bytes) -> WebhookEndpoint:
    endpoint = parse_webhook_endpoints(
        {
            "schema_version": 6,
            "endpoints": {
                "audit": {
                    "url": f"https://hooks.example.test:{port}/events",
                    "allowed_hostnames": ["hooks.example.test"],
                    "client_certificate_secret": "file:CLIENT_CERTIFICATE",
                    "client_private_key_secret": "file:CLIENT_PRIVATE_KEY",
                }
            },
        },
        "test",
    )["audit"]
    object.__setattr__(endpoint, "tls_trust_policy", WebhookTlsTrustPolicy("test-ca", ca_pem))
    return endpoint


def test_in_memory_client_identity_completes_a_real_mutual_tls_request(tmp_path: Path) -> None:
    trusted = authority("test-ca")
    server_identity = issued_identity(
        trusted,
        "hooks.example.test",
        ExtendedKeyUsageOID.SERVER_AUTH,
        dns_name="hooks.example.test",
    )
    client_identity = issued_identity(trusted, "ansiblectl-client", ExtendedKeyUsageOID.CLIENT_AUTH)
    server, thread, port = start_server(tmp_path, trusted, server_identity)
    endpoint = selected_endpoint(port, trusted.certificate.public_bytes(serialization.Encoding.PEM))
    identity = validate_webhook_client_identity(
        SecretMaterial(client_identity[0].decode("ascii")),
        SecretMaterial(client_identity[1].decode("ascii")),
    )

    status = BoundHttpsWebhookTransport().post(
        endpoint,
        WebhookDestination("hooks.example.test", port, ("127.0.0.1",)),
        WebhookRequest(b"{}", {"Content-Type": "application/json"}, client_identity=identity),
    )
    thread.join(5)

    assert status == 204
    assert not thread.is_alive()
    assert server.errors == []
    assert server.accepts == 1
    assert len(server.peer_certificates) == 1
    assert server.requests[0].startswith(b"POST /events HTTP/1.1\r\n")


def test_untrusted_client_identity_fails_once_without_anonymous_fallback(tmp_path: Path) -> None:
    trusted = authority("trusted-ca")
    untrusted = authority("untrusted-ca")
    server_identity = issued_identity(
        trusted,
        "hooks.example.test",
        ExtendedKeyUsageOID.SERVER_AUTH,
        dns_name="hooks.example.test",
    )
    client_identity = issued_identity(
        untrusted, "untrusted-client", ExtendedKeyUsageOID.CLIENT_AUTH
    )
    server, thread, port = start_server(tmp_path, trusted, server_identity)
    endpoint = selected_endpoint(port, trusted.certificate.public_bytes(serialization.Encoding.PEM))
    identity = validate_webhook_client_identity(
        SecretMaterial(client_identity[0].decode("ascii")),
        SecretMaterial(client_identity[1].decode("ascii")),
    )

    with pytest.raises(SSL.Error):
        BoundHttpsWebhookTransport().post(
            endpoint,
            WebhookDestination("hooks.example.test", port, ("127.0.0.1",)),
            WebhookRequest(b"{}", {}, client_identity=identity),
        )
    thread.join(5)

    assert not thread.is_alive()
    assert server.accepts == 1
    assert server.peer_certificates == []
    assert len(server.errors) == 1
