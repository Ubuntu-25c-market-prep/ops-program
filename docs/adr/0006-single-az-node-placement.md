# 0006. Two AZs of subnets, all node capacity in one

**Status:** Accepted
**Date:** 2026-08-01
**Deciders:** @cto, @infra

Refines [ADR 0005](0005-public-subnets-no-nat.md), which decided public subnets
and no NAT but did not settle Availability Zone count.

## Context

This is a learning platform with no external customers and no availability
commitment. Spreading across three AZs buys resilience nobody is paying for, and
costs real money: cross-AZ traffic is billed at $0.01/GB in each direction, and a
service mesh generates a great deal of it.

There is a hard constraint. From the EKS networking requirements:

> The subnets that you specify when you create or update a cluster **must be in
> at least two different Availability Zones.**

So a genuinely single-AZ cluster cannot be created. However, cluster subnets and
node subnets are separate concerns — the same document notes you can deploy nodes
to subnets you did not specify at cluster creation.

## Decision

- **Subnets in 2 AZs.** The minimum EKS permits, satisfying the cluster
  requirement for its control plane network interfaces.
- **All node capacity in one AZ.** Karpenter NodePools are constrained to a
  single AZ; managed node groups reference only that AZ's subnet.
- **Load balancers in the node AZ.**

## Alternatives considered

**Three AZs, nodes spread** — the production-shaped answer. Rejected: cross-AZ
data transfer for no availability benefit that matters here.

**One AZ everywhere** — what was originally asked for. Not possible; EKS rejects
a cluster whose subnets do not span two AZs.

**Two AZs, nodes spread across both** — halves the cross-AZ cost rather than
eliminating it, and keeps AZ-failure resilience. A reasonable middle, rejected
because partial resilience still cannot survive an AZ loss without more replicas
than this platform runs.

## Consequences

- **Cross-AZ traffic drops to near zero** for pod-to-pod, which is where the
  volume is. Roughly $50/month, plus the node count reduction from not needing
  replicas spread across AZs. Platform estimate moves to about **$1,900/month**.
- **An AZ outage takes the entire platform down.** This is accepted, explicitly.
  There is no HA story and nobody should claim one.
- **EBS volumes get simpler, not harder.** Volumes are AZ-bound; with one node AZ
  a stateful pod can always reschedule onto a node that can mount its volume. The
  usual "pod is Pending because its PV is in another AZ" failure disappears —
  a real benefit for Prometheus, Elasticsearch and Velero restores.
- **Karpenter must be constrained.** A NodePool without an AZ requirement will
  happily provision into the second AZ and quietly reintroduce cross-AZ charges.
  This is the most likely way this decision silently stops holding.
- Some control-plane-to-node traffic still crosses AZs when the EKS network
  interface lands in the other AZ. Small, and not avoidable given the two-AZ
  requirement.
- Istio topology-aware routing becomes a no-op rather than a necessity. Leave it
  configured — it costs nothing and matters again the moment a second AZ is used.

## Reversal cost

Low, unusually. Adding node capacity in the second AZ is a Karpenter NodePool
change, because the subnets already exist. This is the cheapest decision here to
undo, which is part of why it is acceptable.
