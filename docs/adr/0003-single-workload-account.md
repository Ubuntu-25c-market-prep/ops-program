# 0003. One workload account, management account kept empty

**Status:** Accepted
**Date:** 2026-08-01
**Deciders:** @cto, @security

## Context

The organisation `o-4r6t0s4e7i` already had Dev, Staging and Prod member
accounts. With one cluster (ADR 0002), per-environment accounts add per-account
AWS Config, GuardDuty and Security Hub charges for no isolation benefit.

The obvious simplification — run everything in the management account — collides
with a hard AWS constraint: **SCPs have no effect on the management account.**
The budget-action freeze that enforces the cost ceiling would be inert there.

## Decision

`808540602855` (Dev) is the single workload account. `909783398044` stays
management-only: Organizations, Identity Center, budgets and the freeze SCP.
Staging and Prod remain dormant.

`336449003124` is Aslan's personal homelab account and is **out of scope
permanently** — it holds live homelab credentials and backups.

## Alternatives considered

**Everything in the management account** — one account, no role switching.
Rejected because the cost freeze cannot protect it, which defeats the guardrail
the programme explicitly asked for.

**Keep per-environment accounts** — real isolation, but roughly $150/mo in
duplicated Config/GuardDuty/Security Hub for environments that are namespaces in
one cluster anyway.

## Consequences

- Saves roughly $150/mo.
- The freeze SCP genuinely blocks new spend in the workload account.
- One cross-account hop: `budgets/` runs in management but keeps state in the
  workload account's bucket, granted via `state_reader_account_ids` in both the
  bucket policy and the KMS key policy.
- Engineers assume `OrganizationAccountAccessRole` into the workload account.
- Staging and Prod stay available if per-environment accounts are ever wanted
  back — this decision is reversible, unlike closing them.
