"""Address-bound standard-library HTTPS transport for webhook delivery."""

from __future__ import annotations

import http.client
import socket
import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.parse import urlsplit

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
    ) -> None:
        context = ssl.create_default_context()
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
    return cast(
        WebhookHttpsConnection,
        _BoundHttpsConnection(
            destination,
            connect_timeout=endpoint.connect_timeout_seconds,
            read_timeout=endpoint.read_timeout_seconds,
        ),
    )


@dataclass(frozen=True)
class BoundHttpsWebhookTransport:
    """POST once without redirects, proxies, retries, or unbounded response reads."""

    connection_factory: Callable[[WebhookEndpoint, WebhookDestination], WebhookHttpsConnection] = (
        _make_connection
    )

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
        connection = self.connection_factory(endpoint, destination)
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
