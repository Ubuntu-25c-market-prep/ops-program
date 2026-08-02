# 0002. One EKS cluster, environments as namespaces

**Status:** Accepted
**Date:** 2026-08-01
**Deciders:** @cto, @infra

## Context

The reference design was three clusters (dev, stage, prod). Three control planes
are $219/mo before a single node, and the platform add-on set — Istio, Kyverno,
KEDA, Velero, OpenTelemetry, Prometheus, EFK, Argo, Flux, Rancher, Kubecost —
would run three times over.

## Decision

One EKS cluster. `dev`, `stage` and `prod` are namespaces within it.

## Alternatives considered

**Three clusters** — proper isolation, an upgrade rehearsal surface, and no
shared-tenancy risk. Rejected on cost: roughly $830/mo more, most of it
duplicated platform add-ons rather than workload capacity.

**One cluster now, split prod later** — the pragmatic middle. Still the intended
path once real traffic exists; this ADR does not close it off.

## Consequences

- Saves roughly $830/mo, about half from running one add-on set instead of three.
- **No upgrade rehearsal surface.** EKS, Istio and Kyverno upgrades land on the
  only cluster there is. Mitigation: an ephemeral cluster from the same Terraform
  for rehearsal, destroyed after — dollars per run, not $73/mo standing.
- **One OIDC provider.** Every IRSA trust policy must be conditioned on
  `namespace:serviceaccount` or a dev pod can assume a prod role. This is the
  decision's sharpest edge and is enforced by Kyverno, not convention.
- Hard tenancy between namespaces becomes mandatory: default-deny
  NetworkPolicies, ResourceQuotas, LimitRanges, PodSecurity admission, and
  separate Karpenter NodePools with taints so prod never lands on shared Spot.
