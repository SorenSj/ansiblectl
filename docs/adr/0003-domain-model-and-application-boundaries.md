# ADR-0003: Domain Model and Application Boundaries

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md), [ADR-0002](0002-python-runtime-and-packaging.md) |

## Context

Ansiblectl coordinates concepts that are meaningful independent of any one
command, provider, or external tool: workspaces, projects, inventories, hosts,
repositories, playbooks, executions, configuration, and secret references.
These concepts must remain consistent when accessed through the CLI, a plugin,
or a future API.

If command handlers or infrastructure adapters own the rules for these
concepts, the project will duplicate behaviour, make testing dependent on
external systems, and make a public SDK difficult to define.

## Decision

Ansiblectl will use an explicit domain model and application-service boundary.

The **domain layer** owns core concepts, invariants, policies, value objects,
domain errors, and abstract ports. It defines what is valid and meaningful in
the product, but does not perform terminal I/O, filesystem access, network
calls, subprocess execution, persistence, or plugin discovery.

The **application layer** owns use cases. A use case coordinates domain models
and ports to accomplish an operator intent, such as initialising a workspace,
validating configuration, synchronising a repository, resolving inventory, or
preparing an Ansible execution. It is invoked by an entry point and returns
structured results or typed failures; it does not render terminal output.

The CLI, plugin runtime, and future API adapters are delivery mechanisms. They
translate external input into an application command or query and render the
result. Infrastructure adapters implement the ports required by application
and domain code.

The initial domain vocabulary is:

| Concept | Meaning |
| --- | --- |
| Workspace | Explicit local operating boundary for ansiblectl |
| Project | Named automation unit within a workspace |
| Configuration | Validated, layered settings for an operation |
| Inventory | Declarative set of hosts and groups |
| Host | Addressable managed target with metadata |
| Repository | Version-controlled source of automation content |
| Playbook | Ansible automation entry point |
| Execution | Requested or completed invocation with its outcome |
| Secret reference | Identifier for a value owned by a secret provider |
| Plugin | Independently versioned extension with declared capabilities |

This vocabulary is a starting point, not a promise that every concept receives
a separate persistence model or package. A concept becomes a first-class domain
type when it has invariants, lifecycle, policy, or public-contract value.

## Rationale

An explicit domain model separates stable product rules from changing delivery
and integration details. It lets the project test use cases without a terminal,
Git repository, Ansible installation, or remote provider. It also gives plugin
authors and future API consumers a common language without exposing internals.

Application services prevent the domain from becoming a command dispatcher and
prevent command handlers from becoming an unstructured business-logic layer.
The boundary is lightweight: it favours clear Python modules and typed
interfaces over a framework or ceremony for its own sake.

## Consequences

### Positive

- Product rules have one authoritative home.
- Use cases can be exercised with fakes at adapter boundaries.
- CLI, plugin, and future API behaviour can share the same use cases.
- Public models and errors can be documented without exposing infrastructure.
- Refactoring an adapter does not require rewriting domain policy.

### Costs and constraints

- Contributors must distinguish a domain rule from an orchestration concern.
- Some small features may initially need an application service and test fake
  before a concrete adapter exists.
- The model must avoid speculative abstractions; not every noun merits an
  entity or repository abstraction.
- Public domain types require compatibility discipline when exposed through
  the CLI or SDK.

## Alternatives considered

### CLI-centred command handlers

Rejected. This is quick for initial commands but couples operator interaction,
business rules, and integrations. It makes non-CLI delivery mechanisms and
repeatable tests more difficult.

### Active-record or persistence-centred model

Rejected. The initial product must not assume a database or bind core concepts
to a storage technology. Persistence is an infrastructure concern behind a
port.

### Fully generic resource model

Rejected. Treating every concept as an interchangeable resource loses the
invariants and ergonomics that make automation safe. Shared abstractions may be
introduced later where evidence shows they are useful.

### Domain-driven-design framework

Rejected. The project adopts useful DDD ideas—ubiquitous language, invariants,
and bounded responsibilities—without adopting a framework or a rigid tactical
pattern catalogue.

## Compliance

New capability specifications MUST identify the responsible layer and the
domain concepts they introduce or change. Pull requests MUST NOT put domain
policy in CLI handlers or concrete adapters. A new public domain model,
cross-cutting domain concept, or material change to the vocabulary requires an
ADR or Technical Specification proportionate to its impact.

## Related decisions

- A future ADR will define the concrete configuration model.
- A future ADR will define inventory and execution semantics.
- A future Technical Specification will define the first CLI use cases.
