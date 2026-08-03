# Ansiblectl Engineering Principles

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Effective date | 2026-08-03 |
| Owner | Ansiblectl maintainers |

## 1. Purpose and authority

This document defines the engineering principles that govern ansiblectl. It is
normative: implementations, technical specifications, architecture decisions,
and project processes **MUST** conform to it.

The repository is the authoritative source for this document. A change to a
principle requires review and a version update. The terms **MUST**, **MUST
NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as
described by RFC 2119.

When normative artefacts disagree, the following order of precedence applies:

1. Approved requirements
2. Engineering Principles
3. Architecture Handbook
4. Architecture Decision Records (ADRs)
5. Technical Specifications
6. Source code and tests

Informative material, including tutorials, examples, and the README, does not
override normative artefacts.

## 2. Principles

### EP-01 — Requirements precede implementation

Every user-visible capability MUST trace to an approved requirement. The
requirement defines the problem and acceptance criteria before implementation
details are selected.

### EP-02 — Architecture is intentional and enforceable

The system MUST have explicit dependency and boundary rules. Violations of
those rules are defects, not accepted technical debt, and MUST be corrected or
recorded as a time-bound exception.

### EP-03 — Decisions are durable and discoverable

Significant architectural decisions MUST be captured in an ADR before or with
their implementation. ADRs are immutable historical records; a changed
decision is superseded by a new ADR rather than silently rewritten.

### EP-04 — Specifications are executable commitments

Each significant component, integration, and public behaviour MUST have a
technical specification proportionate to its risk. Specifications MUST define
observable behaviour, interfaces, constraints, and verification expectations.

### EP-05 — Keep the core small; extend through stable boundaries

The core MUST contain only capabilities that require long-term, coordinated
stewardship. Feature-specific integrations SHOULD be delivered through defined
extension points. Plugins MUST depend on public SDK contracts, never internal
implementation details.

### EP-06 — Dependencies point inward

User interfaces, infrastructure, and plugins MAY depend on application and
domain contracts. Domain logic MUST NOT depend on CLI, infrastructure, or a
plugin implementation. Dependencies MUST be visible through explicit
interfaces and construction, not global state.

### EP-07 — Public APIs are contracts

Every public CLI command, configuration field, SDK surface, plugin contract,
and machine-readable output MUST be documented and versioned. Breaking changes
MUST occur only in a major release and MUST include migration guidance.

### EP-08 — Prefer explicit, typed, validated data

Configuration, boundary inputs, and persisted data MUST be validated at their
boundary. Internal behaviour SHOULD use explicit types and models rather than
unstructured dictionaries or implicit conventions.

### EP-09 — Secure by default and minimise authority

The project MUST apply least privilege, validate untrusted input, and avoid
writing secrets to source control, logs, diagnostics, or ordinary command
output. Plugins and integrations MUST receive only the capabilities they need.

### EP-10 — Fail safely and explain clearly

Failures MUST preserve safety and data integrity. Errors exposed to users MUST
state what failed, why it matters, and the next safe action when known, without
exposing secrets or unnecessary internal detail.

### EP-11 — Automate verification

Every feature MUST have automated tests at the appropriate level. Every defect
MUST include a regression test unless such a test is demonstrably infeasible;
that exception MUST be documented in the change review.

### EP-12 — Quality gates are part of the product

Changes MUST pass the project’s required formatting, static analysis, tests,
coverage, security, and documentation checks before merge. A failing required
check MUST NOT be bypassed except through a documented maintainer exception.

### EP-13 — Documentation evolves with behaviour

Documentation is a deliverable, not a follow-up task. A change that alters
public behaviour, operations, architecture, or contributor workflow MUST
update the corresponding documentation in the same review.

### EP-14 — Operability is a design concern

The software MUST be diagnosable in normal operation. Logging, configuration
validation, predictable exit behaviour, and actionable diagnostics MUST be
considered in the design of each operational capability.

### EP-15 — Reproducibility beats hidden environment state

Given declared inputs, supported operations SHOULD behave predictably across
supported environments. The project MUST make relevant configuration, tool
versions, and side effects explicit.

### EP-16 — Design for human operators

The CLI and its output MUST be understandable, scriptable, and safe to use.
Destructive or high-impact operations MUST make their target and consequence
clear and SHOULD require deliberate confirmation unless explicitly run in a
documented non-interactive mode.

### EP-17 — Backward compatibility earns trust

Deprecations MUST provide a supported transition path and a stated removal
version or date. Compatibility promises apply only to documented public
surfaces; internal modules remain free to evolve.

### EP-18 — Small, reviewable changes preserve quality

Changes SHOULD be narrowly scoped, independently verifiable, and traceable to
their requirement, ADR, or issue. Refactoring MUST preserve behaviour unless a
behavioural change is explicitly documented and tested.

### EP-19 — Ownership is shared; stewardship is explicit

Everyone may improve documentation and quality. Maintainers are responsible
for the integrity of public contracts, architecture, release decisions, and
the long-term health of the project.

### EP-20 — Learn without losing history

Incidents, regressions, and difficult trade-offs SHOULD produce durable
improvements: tests, documentation, guardrails, or decisions. The project
MUST favour systemic prevention over repeatedly treating symptoms.

## 3. Change lifecycle

The default lifecycle for a material change is:

```text
Requirement → Design/ADR → Technical specification → Implementation
→ Automated verification → Documentation → Review → Release
```

The scale of the artefacts MUST match the change’s risk and scope. A small bug
fix does not require a new ADR; a new architectural boundary, public contract,
or compatibility commitment does.

## 4. Definition of done

A change is complete only when its applicable requirements are met, automated
tests pass, documentation is current, public contracts are documented, and any
required ADR or technical specification has been reviewed. Release notes and
migration guidance are required for externally observable changes.

## 5. Compliance and exceptions

Reviewers MUST treat these principles as acceptance criteria. A temporary
exception MUST state its rationale, owner, scope, and expiry or removal plan in
the relevant review or ADR. Permanent exceptions require an ADR.

## 6. Revision policy

Minor clarifications that do not alter intent increment the minor version.
Changes that add, remove, or materially alter a principle increment the major
version. Superseded versions remain in repository history.
