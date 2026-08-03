# ADR-0002: Python Runtime and Packaging

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Ansiblectl orchestrates Ansible and needs a mature ecosystem for command-line
applications, typed validation, testing, package distribution, and plugins.
The implementation language must support a clear SDK while remaining accessible
to the operators and automation engineers most likely to extend the product.

The language decision is consequential: it affects the Ansible integration,
contributor experience, packaging model, static analysis, and plugin ecosystem.

## Decision

Ansiblectl core and its supported plugin SDK will be implemented in **Python**.
The project will support Python 3.12 and later within the actively maintained
Python release line. The exact supported version matrix is part of release
documentation and will be verified in CI.

The project will use standard Python packaging metadata in `pyproject.toml`
and distribute installable artifacts as wheels. The canonical command-line
entry point will be declared through package metadata. Tooling choices must
preserve this standard packaging model and may be replaced without changing the
public CLI or SDK contract.

Code must use type annotations for public APIs and for internal boundaries.
Static type checking, formatting/linting, and pytest-based automated testing
are mandatory quality gates. Runtime models and configuration boundaries will
be validated by an implementation selected in a future ADR or Technical
Specification; unvalidated dictionaries are not a substitute for a public
model.

Ansible interaction occurs through explicit infrastructure adapters. The
domain layer must not import Ansible or depend on Ansible's internal Python
APIs.

## Rationale

Python is the implementation language of Ansible and is already familiar to
the intended contributor community. It provides direct access to Ansible-aware
libraries and a mature ecosystem for packaging, testing, terminal UX,
validation, and developer tooling.

The language enables a typed, documented SDK without requiring plugin authors
to cross a language boundary. Standard `pyproject.toml` metadata and wheels
avoid coupling the product to a single dependency-management tool while
supporting conventional installation and distribution.

## Consequences

### Positive

- Strong alignment with Ansible and its contributor ecosystem.
- Lower friction for integrations and plugin development.
- Mature tools for tests, type checking, linting, packaging, and CLI output.
- Standard package metadata makes the build and installation model portable.
- The implementation can provide both ergonomic Python APIs and a stable CLI.

### Costs and constraints

- Python runtime and dependency versions require explicit support testing.
- Static types need disciplined enforcement to provide value.
- Plugin compatibility must be managed across Python and SDK versions.
- Care is required to keep Ansible-specific concerns at the infrastructure
  boundary rather than allowing them to leak into the domain.

## Alternatives considered

### Go

Rejected. Go produces simple static binaries and has strong CLI tooling, but
it would introduce a language boundary to Ansible's primary ecosystem and make
deep integration and plugin contribution less approachable for the expected
users.

### Rust

Rejected. Rust offers excellent safety and distribution properties, but its
learning curve and distance from Ansible's Python ecosystem would slow core
and plugin development without solving an initial product requirement.

### Node.js/TypeScript

Rejected. TypeScript provides a productive CLI experience but does not align
with Ansible's implementation ecosystem or its most natural integration
surface. It would add a second runtime for Ansible-facing automation.

### C# or Java

Rejected. Both have mature ecosystems but create the same integration and
community mismatch as other non-Python choices, with no compensating initial
requirement.

### Shell scripts around Ansible

Rejected. Shell is useful for narrow glue tasks but lacks the typed models,
testability, packaging, and stable extension contracts required for a durable
automation platform.

## Compliance

Before the first implementation release, the repository MUST define its exact
supported Python matrix, dependency-locking strategy, type checker, linter,
formatter, test runner, and build backend in project configuration. Those
tools remain implementation choices; changes to them do not require a new ADR
unless they alter a public contract or the supported runtime policy.

## Related decisions

- A future ADR will define the configuration and validation model.
- A future ADR will define plugin SDK compatibility and distribution.
- A future Technical Specification will define the CLI foundation and exit
  code contract.
