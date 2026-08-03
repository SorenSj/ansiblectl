# Ansiblectl Architecture Handbook

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Effective date | 2026-08-03 |
| Governing principles | [Engineering Principles v1.0](../engineering-principles/engineering-principles-v1.0.md) |
| Owner | Ansiblectl maintainers |

## 1. Purpose and scope

This handbook defines the target architecture of ansiblectl: a local-first,
extensible command-line platform for managing Ansible automation. It is the
authoritative architectural specification for the core product. Technical
Specifications define individual capabilities; ADRs explain consequential
decisions without overriding this handbook.

The architecture supports a small, stable core and independently evolving
integrations. It does not mandate a daemon, web application, or remote control
plane. Such capabilities require a future ADR and technical specification.

## 2. Architectural goals

The system MUST prioritise, in order:

1. Safe and understandable automation for operators.
2. A maintainable, testable core with clear boundaries.
3. A stable public CLI and plugin SDK.
4. Explicit configuration, validated inputs, and reproducible execution.
5. Extension through plugins rather than growth of the core.

Initial non-goals are re-implementing Ansible’s execution engine, making all
internal modules public extension points, requiring hosted services for normal
local use, and introducing distributed coordination without a documented need.

## 3. System context

```text
Operator / CI
     │
     ▼
ansiblectl CLI ──────────────┐
     │                       │
     ▼                       ▼
Application services     Plugin commands
     │                       │
     └──────────┬────────────┘
                ▼
          Domain contracts
                │
                ▼
 Infrastructure adapters / plugin providers
                │
                ▼
  Filesystem · Git · Ansible · secret stores · external APIs
```

The CLI is the initial user interface. CI callers use the same public command
and machine-readable output contracts; they do not receive a separate internal
API.

## 4. Layers and responsibilities

### 4.1 CLI (`ansiblectl.cli`)

The CLI parses commands, renders user-facing output, maps exit codes, and
creates the application composition root. It MUST NOT contain domain rules or
direct infrastructure access other than bootstrapping.

### 4.2 Application (`ansiblectl.application`)

Application services implement use cases such as validating a workspace,
resolving configuration, preparing an execution, or coordinating a provider.
They orchestrate domain contracts and ports. They MUST NOT depend on a
concrete adapter or plugin implementation.

### 4.3 Domain (`ansiblectl.domain`)

The domain layer contains concepts, policies, value objects, errors, and port
definitions that express ansiblectl’s business rules. It MUST remain free of
CLI frameworks, persistence frameworks, network clients, and plugin loading
details.

### 4.4 Infrastructure (`ansiblectl.infrastructure`)

Infrastructure implements domain ports for local files, subprocess execution,
Git, Ansible, configuration sources, caching, and other external systems. It
MUST be replaceable in tests and MUST NOT import the CLI.

### 4.5 Plugins (`ansiblectl.plugins`)

The plugin runtime discovers, validates, loads, and isolates extensions.
Plugins provide optional commands, providers, event handlers, or output
integrations through the public SDK. A plugin MUST NOT import internal core
modules.

### 4.6 SDK (`ansiblectl.sdk`)

The SDK is the only supported public Python surface for plugin authors. It
contains versioned contracts, context capabilities, models, and testing
utilities. It MUST NOT expose internal service locators or concrete adapters.

## 5. Dependency rules

| From | May depend on |
| --- | --- |
| CLI | Application, Domain, SDK public contracts |
| Application | Domain |
| Domain | Python standard library and domain-owned abstractions |
| Infrastructure | Application and Domain |
| Plugin runtime | SDK public contracts, Application and Domain integration ports |
| Third-party plugin | SDK public contracts only |
| SDK | Domain-owned public models and contracts only |

Domain MUST NOT depend on CLI, Infrastructure, Plugin runtime, or third-party
plugins. Infrastructure MUST NOT depend on CLI. A third-party plugin importing
an `ansiblectl` module outside `ansiblectl.sdk` is an architecture violation.

The project MUST add automated import-boundary validation before the first
implementation release. Exceptions require an ADR or a time-bounded reviewed
exception under Engineering Principle EP-02.

## 6. Composition and dependency injection

The CLI composition root constructs concrete adapters and injects them into
application services. Services and plugins MUST receive declared dependencies
through constructor arguments or an explicit SDK context. Global mutable
registries and hidden singleton services are prohibited.

A context supplied to a plugin is capability-based: it exposes only public
services and permissions granted to that plugin. Plugin code MUST NOT construct
its own privileged core adapters.

## 7. Extension architecture

The plugin lifecycle is:

```text
Discover → Validate manifest and compatibility → Resolve permissions
→ Load → Initialise → Register capabilities → Run → Shut down
```

Plugins MUST declare a name, version, compatible SDK range, capabilities, and
required permissions in a manifest. Discovery or validation failure MUST
prevent the affected plugin from running while preserving a clear diagnostic.
The core MAY continue when an optional plugin fails, but MUST report that state.

Initial public extension categories are command plugins, provider plugins,
event subscribers, and output/report integrations. New categories require an
ADR when they change the SDK’s compatibility or security model.

## 8. Data, configuration, and workspace boundaries

A workspace is the explicit local boundary for ansiblectl operation. All
configuration resolution, repository discovery, and relative path handling
MUST occur in a known workspace context.

Configuration is layered and typed. Its precedence order and file formats MUST
be specified before implementation. Parsers MUST reject invalid data at the
boundary and provide location-aware diagnostics. Secrets are references to
secret providers, not values stored in normal configuration or logs.

## 9. Execution and external systems

Ansiblectl orchestrates Ansible; it does not embed Ansible semantics in the
domain layer. All process execution MUST pass through a defined execution port
that captures arguments, working directory, environment policy, lifecycle, and
structured result. Shell construction from unvalidated strings is prohibited.

External adapters MUST apply timeouts where appropriate, classify transient
failures, and avoid leaking credentials in errors or logs. Destructive
operations MUST expose their target and require an explicit safe invocation.

## 10. Events and observability

The system MAY publish domain-relevant events to decouple optional observers;
events are not a replacement for direct use-case collaboration. Event payloads
MUST be typed, versioned if public, and free of secrets.

Operational behaviour MUST provide structured logging and predictable exit
codes. A correlation or execution identifier SHOULD flow through an operation.
Human-readable and machine-readable output MUST be designed separately.

## 11. Error model and security

Errors cross layer boundaries as typed, meaningful failures. The application
layer maps expected domain and adapter failures into CLI outcomes; the CLI owns
rendering and exit codes. Unexpected failures MUST be safely reported with an
actionable diagnostic.

The architecture follows least privilege. Secrets MUST be retrieved only when
needed, kept out of ordinary logs and diagnostics, and never persisted in
project configuration. Plugins MUST receive explicit permissions rather than
ambient access to the host process.

## 12. Verification requirements

| Concern | Minimum verification |
| --- | --- |
| Domain | Unit tests for policies and value objects |
| Application | Use-case tests against fake ports |
| Infrastructure | Adapter contract and integration tests |
| CLI | Command, output, and exit-code tests |
| SDK and plugins | Compatibility, manifest, and plugin tests |
| Architecture | Automated import-boundary validation |

Architecture tests MUST fail when a forbidden dependency is introduced. Public
contracts MUST have documentation and compatibility tests before being stable.

## 13. Evolution rules

This handbook establishes the stable shape, not every implementation detail.
Any change to a layer, dependency rule, public extension contract, or the
security model requires an ADR and a handbook update when it changes the target
architecture. Component-level choices belong in Technical Specifications.
