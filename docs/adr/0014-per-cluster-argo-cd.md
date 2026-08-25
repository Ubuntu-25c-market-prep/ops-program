# 0014. One Argo CD per cluster, and a repository layout where clusters are additive

**Status:** Proposed
**Date:** 2026-08-20
**Deciders:** @argocd, @flux, @cto

> ADR number 0013 is left for the Teleport decision promised in `gitops-flux#99`.

## Context

ADR 0002 chose one EKS cluster with `dev`, `stage` and `prod` as namespaces, on
cost. It also said what comes next, in its own words:

> **One cluster now, split prod later** — the pragmatic middle. Still the intended
> path once real traffic exists; this ADR does not close it off.

That path is now expected to arrive: roughly one dev, three UAT and seven
production clusters. `terraform-infra-v2` already carries a directory per
environment, so the infrastructure side has started.

Nothing about the cluster count changes today. What changes today is that
`gitops-argocd` is being written now, and it can be written so the tenth cluster
is a new directory rather than a refactor. Deciding after the fact costs a
migration of every `Application` in flight.

Two questions have to be answered before the layout can be fixed: **how many Argo
CDs**, and **what varies per cluster**.

## Decision

### 1. Each cluster runs its own Argo CD

Installed by that cluster's Flux, exactly as ADR 0015 already describes, and
reconciling only the cluster it runs on. There is no hub, and no Argo CD ever
holds credentials for a cluster other than its own.

The consequence worth stating explicitly, because it is the field that usually
rots: `AppProject.spec.destinations[].server` stays
`https://kubernetes.default.svc` **permanently**. It is not a single-cluster
shortcut to be generalised later.

### 2. `gitops-argocd` mirrors the `gitops-flux` layout

```
clusters/<env>/<cluster>/     what THIS cluster's Argo CD reconciles
projects/base/                the AppProject - identical on every cluster
applicationsets/base/<env>/   one directory per environment
apps/<app>/base/              environment-neutral workload
apps/<app>/overlays/<env>/    namespace, image tag, replicas, limits
```

Adding a cluster is a new directory under `clusters/`. Nothing under `base/` or
`apps/` is touched, which is the same property `gitops-flux` already has and the
reason the shape is worth copying rather than inventing.

### 3. A cluster's entrypoint decides which environments it may run

`clusters/<env>/<cluster>/kustomization.yaml` lists the ApplicationSets that
cluster installs. Today's single cluster lists all three. A dedicated production
cluster would list only `applicationsets/base/prod`, and would therefore be
**incapable of generating a dev Application** — not because policy forbids it,
but because the generator that would create one is not installed there.

### 4. Environment stays in the overlay path, not the cluster path

`apps/<app>/overlays/<env>/`, not `overlays/<env>/<cluster>/`. Seven production
clusters share one prod overlay. Per-cluster differences arrive as parameters
from the `clusters` generator, which reads labels and annotations off the cluster
Secret — the mechanism already used to keep the ECR registry host out of this
public repository.

Seven near-identical overlay directories would be seven places to forget the same
change.

## Consequences

- **The second cluster is a directory, not a project.** Its Flux bootstraps its
  Argo CD; its entrypoint names its environments; `base/` is untouched.
- **No central blast radius.** The design that would concentrate credentials for
  every production cluster in one component is the one being rejected here.
- **Nine Argo CD installs to upgrade** rather than one. Real cost, accepted:
  they are Flux HelmReleases from a shared `base/`, so a version bump is one file
  and nine reconciles.
- **No single pane of glass.** Nine UIs. `rancher` is the workstream that owns
  that problem; this ADR does not solve it and should not pretend to.
- **`app-*` namespace names become partly redundant** once environment is implied
  by the cluster — `app-prod` on a production cluster says it twice. Kept anyway:
  it costs nothing, keeps manifests identical across both topologies, and avoids
  a rename during the migration that matters most.
- **ADR 0002 is not superseded.** One cluster remains correct today. This decides
  only that the tooling will not have to be rebuilt when that changes.

## Alternatives considered

**A hub Argo CD managing every cluster.** One UI, one RBAC policy, one upgrade —
genuinely attractive, and what most tutorials show. Rejected because the hub must
hold credentials to all nine clusters, which makes one compromised `Application`
a path into production, and because it does not mirror Flux: an operator would
have to hold two different mental models for the two controllers.

**Per-cluster overlay directories** (`overlays/<env>/<cluster>/`). Rejected as
premature: seven production clusters are expected to differ in scale, not in
shape, and the `clusters` generator already supplies per-cluster values. Revisit
if a real difference appears that a parameter cannot express.

**Defer until the second cluster exists.** Rejected on cost of delay. The layout
is free to choose now and expensive to change once Applications are running.
