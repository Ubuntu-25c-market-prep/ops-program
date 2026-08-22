# 0012. OpenCost over Kubecost for Kubernetes cost visibility

**Status:** Proposed
**Date:** 2026-08-21
**Deciders:** @finops

## Context

The finops epic (wave 5) names Kubecost. Two things have changed since it was
written.

Thanos is deployed — `infra-aws/thanos` provisions the S3 bucket and the
kube-prometheus-stack sidecar ships blocks to it. **Long-term metric retention,
which is what Kubecost's paid tier sells, we now have for free.**

Kubecost's free tier caps retention at 15 days. The monthly cost review this
workstream owns needs month-over-month comparison, so 15 days is not enough on
its own.

The programme runs under a $200/month ceiling and this cluster is planned to
live two to three months.

## Decision

Install **OpenCost** — the CNCF project — not Kubecost.

## Alternatives considered

**Kubecost, free tier** — same core, since Kubecost is built on OpenCost, plus a
better UI out of the box. Rejected on the 15-day retention cap: the review this
epic exists to produce compares one month against the previous one.

**Kubecost, paid tier** — solves retention, but we would be paying for retention
we already own in Thanos, from a budget with no room for it. Rejected on cost,
not on merit — the product is better.

**Neither; use Cost Explorer only** — Cost Explorer answers "which *service*
cost what". It cannot answer "which namespace" or "which workstream", because
AWS bills instances and does not see pods. Rejected: per-namespace showback is
the point of the epic.

## Consequences

- **Dashboards are ours to build.** OpenCost is a Prometheus exporter with a
  minimal UI; Kubecost would have shipped Grafana dashboards. This is real
  additional work and we are accepting it.
- **Cost history is only as good as the Thanos bucket.** Its lifecycle rule
  expires blocks at 90 days, so cost data older than that is gone. Acceptable
  for a two-to-three-month programme; it would not be for a longer one.
- **Install it now, not when the platform is finished.** OpenCost cannot compute
  cost for time before it was running — there is no backfill. Every week we wait
  is a week of per-namespace cost we can never recover. Its dependencies are
  already met: kube-prometheus-stack, kube-state-metrics and Grafana are all
  deployed.
- **Workstream-level showback still depends on labels.** Splitting by namespace
  works out of the box; splitting by workstream needs the Kyverno label
  enforcement from the security epic. Namespace-level is useful on its own in
  the meantime.
- **This supersedes the tool choice only.** ADR 0002 lists Kubecost in its
  add-on inventory. That record stays exactly as written, per the immutability
  rule in `docs/adr/README.md`.
