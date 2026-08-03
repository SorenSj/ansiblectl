# ADR-0038: Signed Plugin Provenance and Registry Trust

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0025](0025-plugin-sdk-compatibility-and-distribution.md), [ADR-0034](0034-supply-chain-and-dependency-governance.md), [TS-0022](../specifications/ts-0022-plugin-trust-verification.md) |

## Context

Manifest validation proves shape and compatibility but not who produced a plugin or whether its
artifact changed after review. Registry names, transport security, and package metadata alone do
not bind publisher identity to exact executable bytes.

Ansiblectl needs deterministic, offline-verifiable evidence before it imports third-party code.
The trust boundary must remain local-first and must not silently install, fetch, or execute a
plugin while evaluating provenance.

## Decision

Version 0.4 introduces a versioned detached provenance statement. It binds one provider identity,
plugin version, SDK compatibility, exact SHA-256 artifact digest, normalized distribution origin,
and signing-key fingerprint. The statement is canonical UTF-8 JSON and is signed with Ed25519 using
a domain-separated payload defined by TS-0022.

Trusted public keys are configured explicitly and identified by a SHA-256 fingerprint of their raw
public-key bytes. Registry trust is an exact normalized-origin allowlist associated with a provider
and signing key. HTTPS protects transport but is not evidence of publisher identity. Local origins
remain explicit policy entries rather than an implicit trust bypass.

Verification occurs before archive extraction, module import, lifecycle hooks, permission prompts,
or plugin-provided diagnostics. Digest, signature, identity, version, origin, key, and policy must
all agree. Failures use stable reason codes and expose no raw key material, signature bytes,
filesystem paths, registry credentials, or parser exceptions.

The first v0.4 increment verifies already available local artifacts and provenance statements. It
does not add a registry client, network installation, key discovery, certificate authority, or
automatic revocation service.

## Consequences

- Plugin execution can be bound to reviewed bytes and an explicitly trusted publisher key.
- Artifact changes, registry substitution, and manifest/provenance disagreement fail before code
  import.
- Operators must distribute and rotate trust policy independently from plugin artifacts.
- Ed25519 verification adds a narrowly scoped cryptographic dependency or adapter.
- Offline operation remains possible after policy, key, artifact, and provenance are available.

## Alternatives considered

Trust on first use was rejected because unattended hosts cannot distinguish first use from initial
compromise. Registry TLS and package hashes without signatures were rejected because they do not
establish publisher identity. Signing YAML manifests directly was rejected because YAML has no
single portable canonical byte representation. Online-only transparency or revocation checks were
rejected for the initial local-first contract.

## Compliance

TS-0022 defines canonicalization, verification order, stable outcomes, and trust-policy inputs. A
change of signature algorithm, signed fields, or origin semantics requires a superseding ADR and a
new provenance schema version.
