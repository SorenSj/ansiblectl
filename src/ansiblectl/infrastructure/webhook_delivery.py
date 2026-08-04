"""Canonical bounded outbound webhook delivery adapter."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_delivery import DeliveryOutcome
from ansiblectl.domain.secrets import SecretProvider
from ansiblectl.domain.webhooks import (
    MAX_WEBHOOK_PAYLOAD_BYTES,
    WebhookAddressResolver,
    WebhookEndpoint,
    WebhookRequest,
    WebhookTransport,
    resolve_webhook_destination,
)

AUTHENTICATION_UNAVAILABLE = "AUTHENTICATION_UNAVAILABLE"
DESTINATION_DENIED = "DESTINATION_DENIED"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
REMOTE_REJECTED = "REMOTE_REJECTED"
REMOTE_RETRYABLE = "REMOTE_RETRYABLE"
SIGNING_UNAVAILABLE = "SIGNING_UNAVAILABLE"
TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
WEBHOOK_SIGNATURE_DOMAIN = b"ansiblectl-webhook-signature-v1\n"
MIN_WEBHOOK_SIGNING_KEY_BYTES = 32
MAX_WEBHOOK_SIGNING_KEY_BYTES = 256


@dataclass(frozen=True)
class HttpsWebhookDeliveryAdapter:
    """Map one immutable envelope to at most one bounded transport attempt."""

    endpoint: WebhookEndpoint
    resolver: WebhookAddressResolver
    transport: WebhookTransport
    secrets: SecretProvider | None = None

    def deliver(self, envelope: DurableEventEnvelope) -> DeliveryOutcome:
        body = json.dumps(
            envelope.to_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        if len(body) > MAX_WEBHOOK_PAYLOAD_BYTES:
            return DeliveryOutcome.failure(PAYLOAD_TOO_LARGE)
        bearer = None
        if self.endpoint.bearer_secret is not None:
            if self.secrets is None:
                return DeliveryOutcome.failure(AUTHENTICATION_UNAVAILABLE)
            try:
                bearer = self.secrets.resolve(self.endpoint.bearer_secret)
                revealed = bearer.reveal_for_operation()
                if not revealed or any(char in revealed for char in "\r\n"):
                    return DeliveryOutcome.failure(AUTHENTICATION_UNAVAILABLE)
            except Exception:
                return DeliveryOutcome.failure(AUTHENTICATION_UNAVAILABLE)
        signature = None
        if self.endpoint.signature_secret is not None:
            if self.secrets is None:
                return DeliveryOutcome.failure(SIGNING_UNAVAILABLE)
            try:
                signing_material = self.secrets.resolve(self.endpoint.signature_secret)
                signing_value = signing_material.reveal_for_operation()
                signing_key = signing_value.encode("utf-8")
                if not MIN_WEBHOOK_SIGNING_KEY_BYTES <= len(
                    signing_key
                ) <= MAX_WEBHOOK_SIGNING_KEY_BYTES or any(
                    ord(char) < 32 or 127 <= ord(char) <= 159 for char in signing_value
                ):
                    return DeliveryOutcome.failure(SIGNING_UNAVAILABLE)
                digest = hmac.new(
                    signing_key, WEBHOOK_SIGNATURE_DOMAIN + body, hashlib.sha256
                ).hexdigest()
                signature = f"v1={digest}"
            except Exception:
                return DeliveryOutcome.failure(SIGNING_UNAVAILABLE)
        try:
            destination = resolve_webhook_destination(self.endpoint, self.resolver)
        except Exception:
            return DeliveryOutcome.failure(DESTINATION_DENIED)
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": envelope.event_id,
            "User-Agent": "ansiblectl-webhook/1",
            "X-Ansiblectl-Event-Id": envelope.event_id,
            "X-Ansiblectl-Event-Sequence": str(envelope.sequence),
        }
        if signature is not None:
            headers["X-Ansiblectl-Signature"] = signature
        request = WebhookRequest(body, headers, bearer)
        try:
            status = self.transport.post(self.endpoint, destination, request)
        except Exception:
            return DeliveryOutcome.failure(TRANSPORT_FAILURE)
        if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
            return DeliveryOutcome.failure(TRANSPORT_FAILURE)
        if 200 <= status <= 299:
            return DeliveryOutcome.success()
        if status in {408, 425, 429} or 500 <= status <= 599:
            return DeliveryOutcome.failure(REMOTE_RETRYABLE)
        return DeliveryOutcome.failure(REMOTE_REJECTED)


__all__ = [
    "AUTHENTICATION_UNAVAILABLE",
    "DESTINATION_DENIED",
    "HttpsWebhookDeliveryAdapter",
    "PAYLOAD_TOO_LARGE",
    "REMOTE_REJECTED",
    "REMOTE_RETRYABLE",
    "SIGNING_UNAVAILABLE",
    "TRANSPORT_FAILURE",
    "WEBHOOK_SIGNATURE_DOMAIN",
]
