# TS-0022: Plugin Trust Verification

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0038](../adr/0038-signed-plugin-provenance-and-registry-trust.md), [ADR-0039](../adr/0039-unattended-plugin-policy.md) |

## Purpose

Define deterministic plugin provenance verification, registry-origin trust, and unattended
permission policy before third-party code import.

## Scope

This specification covers local verification of an already available plugin artifact, detached
provenance statement, trusted Ed25519 public key, and versioned policy. It extends manifest and
permission preflight without introducing registry download or plugin execution.

## Provenance statement

Schema version 1 contains exactly:

- `schema_version`: integer `1`;
- `provider_identity`: non-empty canonical provider identity;
- `plugin_version`: non-empty version string equal to the manifest version;
- `sdk_compatibility`: value equal to the validated manifest contract;
- `artifact_digest`: lowercase `sha256:` plus 64 hexadecimal characters;
- `origin`: normalized `https://` registry origin or explicit `local:` origin identifier;
- `signing_key_id`: lowercase `ed25519:sha256:` plus 64 hexadecimal characters;
- `signature`: unpadded base64url Ed25519 signature.

The signed bytes are the ASCII domain separator `ansiblectl-plugin-provenance-v1`, one newline, and
the UTF-8 encoding of the statement without `signature`, serialized as JSON with lexicographically
sorted keys, no insignificant whitespace, no duplicate keys, no floats, and no Unicode
normalization performed by the verifier. Producers MUST emit canonical NFC strings; a verifier
MUST reject non-NFC signed strings rather than transform them.

The signing-key identifier is the SHA-256 digest of the exact 32 raw Ed25519 public-key bytes. The
artifact digest covers the exact artifact bytes before extraction or import.

## Verification order

The verifier MUST perform these steps in order and stop at the first failure:

1. Parse bounded JSON and reject duplicate or unknown fields.
2. Validate schema, field types, lengths, encodings, and canonical string forms.
3. Resolve exactly one trusted key by `signing_key_id` without network access.
4. Verify the Ed25519 signature over the domain-separated canonical payload.
5. Stream the artifact through SHA-256 and compare the exact digest.
6. Compare provider identity, plugin version, and SDK compatibility with the validated manifest.
7. Match the normalized origin, provider, key, version/digest, and permission ceiling against
   unattended policy.
8. Return a typed decision before any archive extraction, Python import, or plugin callback.

Files MUST be regular, non-symlink inputs. Verification MUST use bounded statement and policy sizes,
stream artifact hashing, and stable reads that reject replacement during inspection.

## Unattended policy

Policy schema version 1 contains managed `deny` and `allow` rule lists plus optional local
restriction rules. One rule contains provider identity and may constrain exact version, artifact
digest, signing-key identifier, normalized origins, and named permissions.

Evaluation is deny-overrides and order-independent. A plugin is allowed only when:

- no deny rule matches;
- exactly one effective allow rule matches identity, provenance, and origin;
- every requested permission is within that rule's permission ceiling; and
- every local restriction also permits the resulting authority.

Missing policy, no match, multiple conflicting matches, unknown permissions, or attempted local
authority expansion is denial. Non-interactive evaluation never prompts, reads grants from the
environment, persists approval, or falls back to an earlier interactive decision.

## Stable decisions and reasons

A public decision contains schema version, provider identity, plugin version, artifact digest,
opaque signing-key identifier, normalized origin, requested/granted/denied permission names,
boolean trusted status, and stable reasons drawn from:

- `PROVENANCE_INVALID`;
- `SIGNING_KEY_UNTRUSTED`;
- `SIGNATURE_INVALID`;
- `ARTIFACT_DIGEST_MISMATCH`;
- `MANIFEST_PROVENANCE_MISMATCH`;
- `ORIGIN_UNTRUSTED`;
- `POLICY_REQUIRED`;
- `POLICY_DENIED`;
- `POLICY_AMBIGUOUS`;
- `PERMISSION_CEILING_EXCEEDED`.

Public output MUST NOT contain raw keys, signatures, credentials, artifact or policy paths, parser
exceptions, environment values, or policy source text. Human, JSON, and YAML output use the same
typed decision.

## Verification

- Canonicalization and domain separation have fixed-vector tests.
- Every stable failure reason has a contract test.
- A one-byte artifact change produces `ARTIFACT_DIGEST_MISMATCH` before import.
- Unknown keys and invalid signatures are indistinguishable from raw cryptographic details in
  public output.
- Deny overrides allow independent of rule order.
- Unattended evaluation never prompts or imports plugin code.
- Symlink, replacement-race, oversized-input, duplicate-key, and malformed-encoding tests fail
  safely.
- Existing manifest discovery and interactive permission preflight remain backward compatible.

## Non-goals

- Registry search, download, dependency resolution, or installation.
- Trust on first use, online key discovery, certificate authorities, or automatic revocation.
- Transparency-log availability guarantees.
- A hosted policy control plane or remote API.
- Executing plugin code in a sandbox.
