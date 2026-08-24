# Node Placement

**Owner:** `@scaling` · **Consumers:** every workstream that runs a workload
**Decision:** [ADR 0013](adr/0013-node-capacity-from-karpenter-pools.md) ·
**AZ constraint:** [ADR 0006](adr/0006-single-az-node-placement.md)

Node capacity on `u25c-shared` comes from four Karpenter NodePools split by
**failure tolerance**, not by team. This page is the contract for putting a
workload on one. Changing it is a pull request here first, reviewed by consuming
workstreams — see [Engineering Handbook §6](engineering-handbook.md).

## The pools

| Pool | Taint | Capacity | Arch | Consolidates | Largest node | Pool cap |
|---|---|---|---|---|---|---|
| `apps` | **none** | spot + on-demand | amd64 only | `WhenEmptyOrUnderutilized`, 5m | 4 vCPU / 16 GiB | 16 CPU / 64 GiB |
| `platform` | `u25c.io/pool=platform:NoSchedule` | spot + on-demand | arm64 + amd64 | `WhenEmptyOrUnderutilized`, 15m | **2 vCPU / 8 GiB** | 8 CPU / 32 GiB |
| `observability` | `u25c.io/pool=observability:NoSchedule` | spot + on-demand | arm64 + amd64 | `WhenEmpty`, 30m | 4 vCPU / 16 GiB | 8 CPU / 32 GiB |
| `burst` | `u25c.io/pool=burst:NoSchedule` | **spot only** | arm64 + amd64 | `WhenEmptyOrUnderutilized`, 1m | 4 vCPU / 16 GiB | 16 CPU / 64 GiB |

All four are pinned to `us-east-1b` per ADR 0006.

**Which one:**

- **`apps`** — business workloads in `app-dev` / `app-stage` / `app-prod`. It is
  untainted, so this is where anything lands that asks for nothing. Start here.
- **`platform`** — platform control planes: Flux, cert-manager, external-dns,
  KEDA, Teleport, Istio. Singletons that should be moved rarely.
- **`observability`** — anything holding state on an RWO EBS volume. Consolidates
  only when genuinely empty, because moving the pod detaches the volume.
- **`burst`** — retryable work: KEDA-scaled workers, Jobs, ETL. Spot-only, and
  nodes disappear about a minute after the work does.

## Placing a workload

Nothing schedules onto a tainted pool without **both** a selector and a
toleration. Setting only one of the two is the most common mistake.

```yaml
spec:
  template:
    spec:
      nodeSelector:
        u25c.io/pool: platform
      tolerations:
        - key: u25c.io/pool
          value: platform
          effect: NoSchedule
```

For `apps`, the `nodeSelector` alone is enough — there is no taint to tolerate.

Verify it landed where you intended:

```bash
kubectl get pods -n <ns> -o wide
kubectl get nodes -L karpenter.sh/nodepool,karpenter.sh/capacity-type
```

## Five things that will bite you

**1. Your image needs an arm64 variant.** Three pools are mixed-architecture and
Karpenter buys whichever is cheaper. A single-arch image will start on some nodes
and `CrashLoopBackOff` on others, which reads as a flaky workload rather than an
architecture problem. Check first:

```bash
docker manifest inspect <image> | grep -c 'linux/arm64'
```

If it has no arm64 build, pin it explicitly rather than hoping:

```yaml
      nodeSelector:
        u25c.io/pool: platform
        kubernetes.io/arch: amd64
```

**2. PodDisruptionBudgets can deadlock the cluster.** A `minAvailable: 1` PDB on
a **single-replica** Deployment permits zero voluntary evictions. Consolidation
and spot drain both stop, indefinitely, and it presents as Karpenter being
broken. Almost every workload on this cluster is single-replica today. Use
`maxUnavailable: 1`, or raise replicas to 2 first.

**3. Spot reclaims are a two-minute drain, not a crash.** Karpenter cordons and
drains on the EC2 rebalance notice. Your pod still restarts — handle `SIGTERM`,
set a sane `terminationGracePeriodSeconds`, and do not assume local disk
survives. If a workload genuinely cannot tolerate this, say so in an issue
against `@scaling` rather than working around it locally.

**4. EBS volumes are stuck in their AZ.** All pools are in `us-east-1b`. A PVC
provisioned in `us-east-1a` will never schedule onto a pool node, and the pod
sits `Pending` with a volume-node-affinity conflict. Volumes in the wrong AZ must
be recreated, not migrated.

**5. Pods larger than the biggest instance sit `Pending` silently.** `platform`
tops out at 2 vCPU / 8 GiB per node, and usable capacity is lower — every node
loses about 130m CPU / 360Mi to DaemonSets before your pod starts. Anything
bigger belongs on `apps` or `burst`, or needs a pool change.

## If no pool fits

Open an issue in `gitops-flux` labelled `ws:scaling`, describing the failure
tolerance of the workload rather than the resources you want. Adding a fifth pool
is a `@scaling` change and it must carry the same `topology.kubernetes.io/zone`
requirement — ADR 0006 names a missing zone requirement as the most likely way
that decision silently stops holding.

## What is not covered here

`karpenter-karpenter` and CoreDNS run on the managed node group on purpose. If
Karpenter ran only on Karpenter-managed nodes and consolidation removed the last
one, nothing would exist to launch its replacement. Do not "tidy" them onto a
pool.
