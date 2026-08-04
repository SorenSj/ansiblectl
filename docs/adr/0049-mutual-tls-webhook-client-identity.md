# ADR-0049: Mutual TLS Webhook Client Identity

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0042](0042-outbound-https-webhook-delivery.md), [ADR-0045](0045-exclusive-webhook-ca-trust.md), [ADR-0047](0047-workspace-file-secret-provider.md), [TS-0032](../specifications/ts-0032-mutual-tls-webhook-client-identity.md) |

## Context

Outbound HTTPS webhooks authenticate servers with platform or explicitly selected CA trust and can
authenticate request bodies with bearer or HMAC material. Some operator-controlled receivers also
require a client certificate during the TLS handshake. Treating certificate and private-key paths
as ordinary endpoint configuration would expose filesystem layout, bypass the secret-provider
boundary, and make key custody dependent on ambient process state.

Mutual TLS is transport authentication, not authorization, payload signing, or receiver identity.
It must compose with the existing destination, network, CA, bearer, and signature contracts without
weakening any of them.

## Decision

Version 0.14 adds opt-in webhook client identity through endpoint schema version 6. An endpoint may
select one certificate-chain secret reference and one private-key secret reference. The two fields
are an indivisible pair and use the existing exact `file:NAME` provider only. Environment-backed
client identities, literal paths, inline PEM, passphrases, PKCS#12, and ambient certificate stores
are rejected.

Both materials are resolved and validated before DNS or transport construction. The certificate
must be a bounded PEM certificate chain and the key must be one bounded, unencrypted PEM private
key matching its leaf certificate. Resolution, parsing, and pair validation happen in memory. The
transport receives an opaque request-local client identity; it must not persist key material or
place it in exceptions, diagnostics, configuration, events, history, or output.

TLS continues to require server-certificate and hostname validation. Client authentication cannot
enable redirects, proxies, TLS downgrade, alternate destinations, or fallback to an anonymous
handshake. Identity failure maps to one stable redacted outcome before network activity. Schema
versions 1 through 5 retain their exact behavior and do not resolve client identity material.

## Consequences

- Operators can authenticate ansiblectl to a receiver with a workspace-custodied client identity.
- Certificate and key rotation remains an explicit file replacement under the existing provider's
  ownership and permission contract.
- The HTTPS transport boundary must support request-local in-memory identity material; temporary
  key files and ambient TLS identity discovery are forbidden.
- Receiver authorization and certificate issuance remain external operator responsibilities.

## Alternatives considered

Literal paths and inline PEM were rejected because configuration and command surfaces are durable.
Environment-backed private keys were rejected because multiline material and process inheritance
create avoidable ambiguity for this first client-identity contract. Encrypted keys and passphrase
references were deferred because they add a second secret, prompt, and failure lifecycle. Anonymous
fallback was rejected because it silently weakens receiver policy. Replacing HMAC or bearer
authentication was rejected because TLS identity and application authentication prove different
properties.

## Compliance

TS-0032 defines schema selection, provider restrictions, PEM and pair validation, ordering,
transport behavior, compatibility, redaction, and adversarial verification. Certificate issuance,
renewal, revocation services, passphrases, hardware keys, and inbound APIs remain out of scope.
