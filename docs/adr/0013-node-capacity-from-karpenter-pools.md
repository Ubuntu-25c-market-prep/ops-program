# 0013. Node capacity comes from Karpenter pools split by failure tolerance

**Status:** Proposed
**Date:** 2026-08-24
**Deciders:** @scaling, @cto

Refines [ADR 0006](0006-single-az-node-placement.md), which fixed all node
capacity in one Availability Zone but did not settle what provisions it.

## Context

Node capacity came from a single EKS managed node group: fixed size, on-demand,
paying for peak at all times. Cost is the binding constraint on this platform,
not availability — and a fixed group cannot scale to zero for work that is
genuinely bursty.

The workloads are not alike in what they can survive, and that difference is not
organisational:

- Prometheus holds state on an RWO EBS volume. Moving it detaches and reattaches
  that volume and leaves a gap in the scrape record.
- The Flux and Istio control planes are singletons. Restarting them is visible.
- Queue workers, Jobs and ETL are retryable by construction. Losing one costs
  nothing.

Measured on 2026-08-22: spot runs 35–61% of on-demand in this region, averaging
about 45%. Every node also pays a flat DaemonSet tax of 130m CPU / 360Mi memory
regardless of size, which puts a real floor under how many nodes are worth
running.

## Decision

- **Karpenter provisions node capacity.** The managed node group shrinks to a
  bootstrap floor running Karpenter's own controller and CoreDNS.
- **Five NodePools, split by failure tolerance rather than by team:**
  `platform`, `observability`, `apps`, `burst`, `prod`.
- **Spot-first everywhere except `prod`**, which is on-demand only; `burst` is
  spot-only with no on-demand fallback.
- **Four pools are tainted; `apps` is untainted** and is the default landing
  zone, so a workload that specifies nothing still schedules.
- **`prod` additionally excludes burstable instance families.** Karpenter buys
  the cheapest type that fits, so leaving t3/t3a available would mean it chose
  burstable every time; a burstable node that exhausts its CPU credits under
  sustained load throttles to 20% of a vCPU, and the symptom is latency rather
  than an error.
- **Placement is a published interface**, not per-team convention: the
  `u25c.io/pool` label and its matching toleration, documented in
  [node-placement.md](../node-placement.md) and owned by `@scaling`.

Per ADR 0006 every pool carries a `topology.kubernetes.io/zone` requirement
pinning it to `us-east-1b`.

## Alternatives considered

**A capacity-type selector on the apps pool instead of a separate `prod` pool** —
leave app-prod on the shared apps pool and have each workload set
`karpenter.sh/capacity-type: on-demand`. Rejected because it is a per-workload
opt-in that every team has to remember, and forgetting it is silent: the pod
simply runs on spot. A tainted pool fails loudly instead — a workload that gets
the toleration wrong stays `Pending` where someone will see it.

**One pool for everything** — the simplest thing that works, and tempting at this
size. Rejected because a single consolidation policy cannot serve both ends of
the range: Prometheus needs `WhenEmpty` with a 30m delay to protect its volume,
while burst nodes should disappear about a minute after the queue drains. One
policy would either churn the observability volume or pay for idle burst nodes.

**A pool per workstream** — the obvious org-chart split, and what was proposed
first. Rejected on two grounds. It multiplies always-on nodes by the number of
teams, and each of those nodes pays the 130m/360Mi DaemonSet tax before running
anything. More fundamentally it encodes the wrong axis: two teams' workloads may
have identical failure tolerance, and one team's rarely does.

**On-demand only** — what production would do. Rejected on cost, and we should be
honest that it is cost rather than merit: spot at ~45% of on-demand, applied to
the two pools that never scale to zero, is where most of a small always-on
cluster's money is. The accepted risk is set out below.

**Keep the managed node group and nothing else** — no new moving parts to learn
or operate. Rejected because a fixed-size group pays for peak continuously and
cannot scale to zero, which forecloses the burst case entirely.

## Consequences

**A NodePool cannot select by namespace.** This is the sharpest edge of the
design and it catches people: running in `app-prod` does not route a workload to
the `prod` pool. Without an explicit nodeSelector and toleration, an app-prod
Deployment lands on the untainted `apps` pool like dev and stage, and can be
scheduled onto spot. The platform provides capacity; routing to it is always a
workload-side change, and for business apps that change lives in the Argo CD
repository rather than in gitops-flux.

**Workloads without a priorityClass are evictable by anything that has one.**
Observed 2026-08-24: a `system-node-critical` DaemonSet rolled out across nodes
whose memory was fully reserved and preempted four priority-0 pods, which then
had nowhere to schedule and forced an unplanned node purchase. Pool membership
does not protect against this - a priorityClass does.

**Every workstream now has to place its workloads.** Landing on a tainted pool
requires both a `nodeSelector` and a matching toleration. The untainted `apps`
pool keeps the default safe, so nothing breaks by omission — but nothing lands on
`platform` or `observability` by accident either. The pools stay inert until
workloads opt in.

**Three of five pools are mixed arm64/amd64** (`apps` and `prod` are amd64-only).. Any image without a `linux/arm64`
variant must set an explicit `kubernetes.io/arch` requirement or it will fail to
start on a Graviton node. This is the most likely first failure for a team
shipping a single-architecture image, and it will surface as `CrashLoopBackOff`
on some nodes and not others.

**Spot means a planned two-minute drain, not a power cut.** The controller runs
with an interruption queue, so Karpenter cordons and drains on the EC2 rebalance
notice. Single-replica workloads still restart, and on this cluster almost
everything is single-replica.

**This is the part that will hurt later:** a `minAvailable: 1` PodDisruptionBudget
on a single-replica Deployment blocks all voluntary eviction. It will deadlock
both consolidation and spot drain, and it will look like Karpenter is broken.
Use `maxUnavailable: 1`, or raise the replica count first.

**Maximum schedulable pod size differs by pool** and is smaller than people
expect — `platform` tops out at 2 vCPU / 8 GiB. A workload larger than its pool's
biggest instance type will sit `Pending` with no obvious cause.

**EBS volumes are AZ-bound.** Combined with ADR 0006, a PVC provisioned in
`us-east-1a` can never schedule onto a pool node. Existing volumes in the wrong
AZ have to be recreated, not moved.

**Karpenter's controller, CoreDNS and Flux stay on the managed node group.** If
Karpenter ran only on Karpenter-managed nodes and consolidation removed the last
one, nothing would exist to launch a replacement. Flux is the sharper case: the
NodePools that would host it are delivered by it, so a bad NodePool change could
make the pool unschedulable and leave no way to push the fix through Git. The
managed node group is a bootstrap floor, not redundancy - and at one node it is
a single point of failure for all three at once.

**Cost, stated honestly:** this is close to cost-neutral today. Four pools take
the cluster from two nodes to three, and each new node pays the DaemonSet tax.
The saving arrives later, when `apps` and `burst` carry variable load and `burst`
scales to zero. It is an architecture decision, not a cost optimisation, and
should not be defended as one.
