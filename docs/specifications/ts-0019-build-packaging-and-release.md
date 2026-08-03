# TS-0019: Build, Packaging, and Release

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines reproducible build artifacts, version source, release checks, and publication prerequisites.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. The version MUST have one authoritative source in package metadata.
2. Builds MUST create standard Python wheel artifacts.
3. A release MUST run the required quality gates and record release notes.
4. Artifacts MUST be traceable to a source revision and dependency set.
5. Publication credentials MUST be handled as secrets and never embedded in artifacts or logs.

## Interfaces and data

The release workflow consumes a clean tagged source revision and produces inspectable wheel and metadata artifacts.

After a build, `dist/build-metadata.json` records the Git source revision and
SHA-256 digest of `uv.lock`; publication credentials are not included.

Release validation requires a dated `CHANGELOG.md` entry matching the package
version. A pushed `v*` tag must equal `v<package-version>` before CI uploads the
wheel, source archive, and build metadata as a retained workflow artifact.
This initial workflow does not publish to a package index and uses no
publication credentials.

Artifact inspection requires exactly one wheel and source archive, verifies
their exact names and required package surfaces against package metadata, rejects unsafe source
archive paths, and verifies that build metadata matches both the current Git revision and the
SHA-256 digest of `uv.lock` before a tagged artifact is uploaded.

## Verification

- A clean checkout builds the same package metadata.
- Release validation fails when required checks fail.
- An artifact inspection test confirms version and source revision metadata.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.
