# 0004. Terraform state segmented by layer

**Status:** Accepted
**Date:** 2026-08-01
**Deciders:** @cto, @infra, @security

## Context

Sixteen engineers across fifteen workstreams share one AWS account. State locks
are per-state file, plan time scales with resource count, and state access is
per-bucket-prefix. A single state file makes all three of those a shared
bottleneck, and makes least privilege impossible.

## Decision

One state file per layer, ordered by change frequency and blast radius.
Dependencies flow strictly downward. Layers publish outputs to SSM Parameter
Store; consumers read parameters rather than each other's state.

Full detail in [terraform-state-strategy.md](../terraform-state-strategy.md).

## Alternatives considered

**One state for everything** — simplest on day one. Rejected: one apply blocks
all 16 engineers, a bad plan can destroy the VPC from an unrelated change, and
everyone who can apply anything can apply everything.

**Terraform workspaces per environment** — rejected because environments are
namespaces in one cluster (ADR 0002), so there is nothing to separate. Workspaces
also hide which environment you are in behind CLI state rather than directory
structure, which is exactly the ambiguity to avoid with 16 people.

**`terraform_remote_state` as the default coupling** — still permitted where the
coupling is intentional, but not the default: it grants the consumer read access
to the producer's entire state, including values that are effectively secrets, to
read one string.

## Consequences

- Independent release cadence per layer; the VPC is not re-planned because an
  add-on changed.
- Per-prefix state permissions become possible, so deploy roles can be scoped.
- More directories, more backend blocks, more `init` invocations.
- Cross-layer values need an explicit published contract, which is more work up
  front and considerably less breakage later.
- A layer that is not in the strategy document's table does not exist.
