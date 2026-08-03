# TS-0011: Plugin Runtime Lifecycle

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines plugin loading, initialisation, capability registration, failure isolation, and shutdown.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. The runtime MUST discover and validate a plugin manifest before loading code.
2. Plugin initialisation MUST receive only an explicit SDK context and granted capabilities.
3. Capability registration MUST be atomic: a failed plugin MUST not leave partial registrations.
4. Optional plugin failures MUST be reported but MUST NOT prevent unrelated core commands from running.
5. The runtime MUST call shutdown for initialised plugins during normal termination.

## Interfaces and data

The runtime manages PluginDescriptor and PluginInstance records and exposes only public registered capabilities to the application composition root.

The initial runtime receives an already validated descriptor and an explicit
capability set. It calls plugin initialisation before changing the registry;
an optional failure records only the plugin identity and exception class. On
normal shutdown, initialised plugins are shut down in reverse load order.

Manifest discovery and permission preflight remain code-free CLI stages. A
filesystem code loader is not exposed until an explicit entrypoint and loading
isolation contract is defined.

## Verification

- A plugin failing during initialisation registers no command or provider.
- A healthy plugin continues when another optional plugin fails.
- Shutdown is tested for an initialised plugin.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.
