# Node Placement

**Owner:** `@scaling` · **Consumers:** every workstream that runs a workload
**Decision:** [ADR 0013](adr/0013-node-capacity-from-karpenter-pools.md) ·
**AZ constraint:** [ADR 0006](adr/0006-single-az-node-placement.md)

Node capacity on `u25c-shared` comes from five Karpenter NodePools split by
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
| `prod` | `u25c.io/pool=prod:NoSchedule` | **on-demand only** | amd64 only | `WhenEmpty`, 30m | 4 vCPU / 16 GiB | 8 CPU / 32 GiB |

All five are pinned to `us-east-1b` per ADR 0006.

**Which one:**

- **`apps`** — business workloads in `app-dev` / `app-stage` / `app-prod`. It is
  untainted, so this is where anything lands that asks for nothing. Start here.
- **`platform`** — platform control planes: Flux, cert-manager, external-dns,
  KEDA, Teleport, Istio. Singletons that should be moved rarely.
- **`observability`** — anything holding state on an RWO EBS volume. Consolidates
  only when genuinely empty, because moving the pod detaches the volume.
- **`burst`** — retryable work: KEDA-scaled workers, Jobs, ETL. Spot-only, and
  nodes disappear about a minute after the work does.
- **`prod`** — the `app-prod` namespace. The only pool that never takes spot, and
  the only one with no burstable instance types: Karpenter buys the cheapest type
  that fits, so leaving t3/t3a available would mean it picked burstable every
  time, and a burstable node that exhausts its CPU credits throttles to 20% of a
  vCPU with latency as the only symptom. **It is not the default for app-prod** —
  see below.

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

## app-prod does not use the `prod` pool automatically

Worth stating plainly, because it surprises people: **a NodePool cannot select by
namespace.** Nothing about running in `app-prod` routes a workload to the `prod`
pool. Without the selector and toleration below, an app-prod Deployment lands on
the untainted `apps` pool exactly like dev and stage — **and can be scheduled
onto spot**.

```yaml
      nodeSelector:
        u25c.io/pool: prod
      tolerations:
        - key: u25c.io/pool
          value: prod
          effect: NoSchedule
```

Those live in the Argo CD repository with the workload, not in `gitops-flux`.
The platform provides the pool; routing to it is an app-side change.

Check where prod is actually running rather than assuming:

```bash
kubectl get pods -n app-prod -o wide
kubectl get nodes -L u25c.io/pool,karpenter.sh/capacity-type
```

## Migrating a workload onto a pool

The pools are opt-in and currently near-empty. Nothing moves until you change
your workload. Migrate **one workload at a time** and verify each before the
next — the failure modes below are all quiet ones.

### 1. Check the image has an arm64 variant

Only matters for `platform`, `observability` and `burst`, which are
mixed-architecture. `apps` and `prod` are amd64-only today — see the note at the
end of this section.

**Business app images live in ECR** (`25c-project/<app>`), which is private, so
`docker manifest inspect` fails with a 401 unless you have run
`aws ecr get-login-password | docker login` first. Ask ECR directly instead:

```bash
aws ecr batch-get-image \
  --repository-name 25c-project/<app> \
  --image-ids imageTag=<tag> \
  --accepted-media-types "application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  --query 'images[0].imageManifest' --output text \
  | jq -r '.manifests[]? | .platform | "\(.os)/\(.architecture)"'
```

Expect one line per architecture:

```
linux/amd64
linux/arm64
```

**No output at all** means the tag is a single-architecture image rather than an
index — `aws ecr describe-images --image-ids imageTag=<tag> --query
'imageDetails[].imageManifestMediaType'` will show
`...image.manifest.v1+json` instead of `...image.index.v1+json`. For public
images, `docker manifest inspect <image>` still works.

If the image is amd64-only, either pin `kubernetes.io/arch: amd64` alongside
your pool selector, or you will get `exec format error` on some nodes and not
others.

> **`apps` and `prod` are amd64-only on an assumption that no longer holds.**
> Both pools were built expecting student-built, amd64-only images. Checked
> 2026-08-25, `25c-project/storefront:0.1.0` publishes **both** `linux/amd64`
> and `linux/arm64`, and the ECR layer's own config says images are built
> multi-arch and promoted by tag rather than rebuilt. Adding `arm64` to those
> two pools would take the Graviton saving. Not changed here because it affects
> workloads `@argocd` owns — raise it with `@scaling` if you want it.



### 2. Check it fits

`platform` tops out at **2 vCPU / 8 GiB per node**; the rest at 4 vCPU / 16 GiB.
Subtract roughly 130m CPU / 360Mi that DaemonSets take on every node before your
pod starts. A pod larger than its pool's biggest instance sits `Pending` with no
obvious cause.

### 3. Set a priorityClass

Do not skip this. On 2026-08-24 a `system-node-critical` DaemonSet rolled out
across full nodes and preempted four Kyverno pods, which had **no priorityClass
and therefore priority 0**. They became unschedulable and Karpenter had to buy a
node to hold them.

Anything that matters should say so:

```yaml
      priorityClassName: system-cluster-critical   # platform components
```

A workload at priority 0 on a full node is evictable by anything with a class.

### 4. Add the selector and toleration

Both. The selector alone leaves you unschedulable on a tainted pool; the
toleration alone lets you land anywhere.

```yaml
      nodeSelector:
        u25c.io/pool: platform
      tolerations:
        - key: u25c.io/pool
          value: platform
          effect: NoSchedule
```

### 5. Check your PodDisruptionBudget

If the workload is **single-replica** — most on this cluster are — a
`minAvailable: 1` PDB permits *zero* voluntary evictions and will deadlock both
consolidation and spot drain. Use `maxUnavailable: 1`, or raise replicas to 2
first.

### 6. Verify it actually moved

The manifest saying the right thing is not evidence:

```bash
kubectl get pods -n <ns> -o wide
kubectl get nodes -L u25c.io/pool,karpenter.sh/capacity-type
kubectl get pods -A --field-selector status.phase=Pending
```

If it is `Pending`, read the event — `untolerated taint` means a missing
toleration, `Insufficient memory` means step 2.

### Known limitation before you migrate in bulk

**Karpenter nodes currently cap at 17 pods**, against 110 on the managed node
group — the prefix-delegation fix reached the managed group only
(gitops-flux#126, open). Until that is fixed, each pool node holds far fewer
pods than its CPU and memory would suggest, so a bulk migration buys more nodes
than you would expect. One workload at a time is the safe pace regardless.

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
