# ADR-0001: Architectural Style and Governance

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Governing documents | [Engineering Principles v1.0](../engineering-principles/engineering-principles-v1.0.md), [Architecture Handbook v1.0](../architecture/architecture-handbook-v1.0.md) |

## Context

Ansiblectl is intended to grow from a local command-line tool into an
extensible automation platform. It needs a design that keeps the core
maintainable while allowing integrations and feature areas to evolve without
turning every internal module into a compatibility commitment.

Without explicit governance, convenient implementation shortcuts would cause
the CLI, domain rules, external APIs, and plugins to become coupled. That would
make testing difficult, turn internal refactors into breaking changes, and
leave contributors without a reliable way to decide where a new capability
belongs.

## Decision

Ansiblectl adopts a **layered, ports-and-adapters architecture with a
plugin-first extension model**.

The core is divided into CLI, Application, Domain, Infrastructure, Plugin
runtime, and SDK layers as defined by the Architecture Handbook. Dependencies
point toward Domain contracts; concrete infrastructure and third-party plugins
remain at the edge.

The CLI is the composition root. It constructs concrete adapters and injects
them into application services. Domain logic is independent of CLI frameworks,
external clients, persistence tools, and plugin loading.

The SDK is the sole supported Python extension surface. First-party and
third-party plugins use it rather than importing internal core modules. The
core remains intentionally small; feature-specific integrations should be
implemented as plugins where that does not compromise safety, usability, or a
stable operator experience.

Engineering Principles, the Architecture Handbook, ADRs, Technical
Specifications, code, tests, and informative documentation have the authority
order defined in Engineering Principles v1.0. A material architectural change
requires an ADR. Architecture boundary violations are defects.

## Rationale

This style preserves a strong domain model while keeping Ansible, Git, secret
stores, filesystems, and external services replaceable and testable. It also
creates a narrow, versionable SDK that can support an ecosystem without
committing the entire implementation to backward compatibility.

The approach fits a CLI-first product: commands remain thin, use cases are
testable without terminal concerns, and infrastructure can be tested through
adapter contracts. It provides enough structure for a growing project without
requiring a distributed system or a framework-heavy microservice architecture.

## Consequences

### Positive

- Core use cases can be tested with fake ports and without external systems.
- Plugin authors receive a clear, stable boundary.
- Internal refactoring is possible without breaking plugins or the public CLI.
- Security and capability limits can be applied at extension boundaries.
- Architecture rules can be validated automatically in CI.

### Costs and constraints

- New features require deliberate placement and, when material, design
  documentation before implementation.
- Dependency injection and explicit interfaces add some initial ceremony.
- The SDK must be versioned and maintained with more care than internal code.
- A plugin model introduces lifecycle, compatibility, and permission concerns
  that must be implemented before plugins are broadly enabled.

## Alternatives considered

### Monolithic CLI application

Rejected. It has a lower initial cost but encourages direct coupling between
commands, business rules, and external systems. It does not create a credible
extension boundary or preserve refactoring freedom.

### Service-oriented or microservice architecture

Rejected for the initial product. Ansiblectl is local-first, and distributed
deployment, service discovery, remote authentication, and operational
complexity are not justified by current requirements. A future remote service
would be an additive architectural decision.

### Plugin-only core with minimal domain model

Rejected. A completely generic host would shift essential automation policy to
plugins and make consistent operator behaviour, security, and compatibility
harder to maintain. The domain and application layers remain core-owned.

### Framework-led architecture

Rejected. The project will select libraries to implement specific boundaries,
but no framework may dictate the domain model or public SDK. This keeps
framework replacement feasible and maintains explicit architecture rules.

## Compliance

Before the first implementation release, the project MUST provide automated
import-boundary validation and a documented public-SDK policy. Pull requests
that introduce a new public extension point, cross a layer boundary, or change
the security model MUST reference a new or superseding ADR.

## Related decisions

- Future ADRs will select the implementation language and packaging approach.
- Future ADRs will define plugin compatibility, manifest, permissions, and
  event semantics.
