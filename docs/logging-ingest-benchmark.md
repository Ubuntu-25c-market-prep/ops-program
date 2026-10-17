# Logging Ingest Benchmark

How much log data the `u25c-shared` cluster produces, what it costs to store
and run, and how that compares with the programme budget. Measured 4 to 10
September 2026, the first seven full days after the collector fixes
(gitops-flux #166, #167, #169). Earlier data is unusable: most of it was the
collector's own retry noise.

Closes gitops-flux [#43](https://github.com/Ubuntu-25c-market-prep/gitops-flux/issues/43),
part of epic [#28](https://github.com/Ubuntu-25c-market-prep/ops-program/issues/28).

> **The one-sentence version:** the whole logging stack costs about $40 a
> month, a fifth of the $200 budget, and the cost does not move with log
> volume at this scale. A third of all log lines come from two components
> stuck in error loops; fixing them is worth more than any filter.

## What the cluster logs

| day | documents | stored |
|---|---|---|
| 2026-09-04 | 244,133 | 122 MB |
| 2026-09-05 | 241,581 | 124 MB |
| 2026-09-06 | 273,890 | 139 MB |
| 2026-09-07 | 348,456 | 166 MB |
| 2026-09-08 | 396,024 | 187 MB |
| 2026-09-09 | 230,728 | 102 MB |
| 2026-09-10 | 223,799 | 104 MB |

Seven days: 1.96 million documents, 944 MB. About 280,000 lines and 135 MB a
day on average, half a kilobyte per line. The rise to 187 MB on the 8th was
installation noise from components added that week (`teleport-agent`,
`platform-auth`, an `istiod` restart), which log heavily at startup. The
steady rate is the 9th and 10th: about 230,000 lines and 100 MB a day.

Retention is seven days (ILM policy `logs-retention`), so Elasticsearch holds
about 1 GB at any time. ILM was confirmed working on 10 September: indices
from 30 August to 3 September were deleted on schedule.

## Who produces it

| namespace | documents | share |
|---|---|---|
| monitoring | 521,099 | 27% |
| keda | 333,814 | 17% |
| kube-system | 303,821 | 16% |
| argocd | 232,632 | 12% |
| platform-auth | 200,231 | 10% |

Five namespaces make 81% of all lines. All of them are platform components.
The application namespaces (`app-dev`, `lab-demo`, `lab-loadgen`) are under
0.1% combined. Logging cost on this cluster is the platform talking to
itself; app teams are not yet a factor.

Two pods alone are 34% of everything:

- `keda-admission-webhooks` (namespace `keda`): 333,675 lines. Every minute it
  logs `limitranges is forbidden: User "system:serviceaccount:keda:keda-webhook"
  cannot watch resource "limitranges"` followed by a stack trace of about
  twenty lines. Its ClusterRole `keda-operator-webhook` grants `list` on
  LimitRanges but not `watch`; the code needs both. KEDA 2.20.2.
- `alertmanager` (namespace `monitoring`): 323,541 lines. Every few seconds it
  logs `Notify attempt failed, will retry later` with `535 5.7.8 Username and
  Password not accepted` from Gmail. No alert email has been delivered for at
  least the whole measured week. Five alerts were firing at the time of
  measurement, including `KubeMemoryOvercommit` and `PrometheusHighMemory`.

Both pods are `Running` and look healthy in `kubectl`. Only their log volume
gives them away. With both fixed, steady ingest drops to roughly 65 MB a day.

## What it costs

Prices are from the September 2026 bill, US East (N. Virginia). Elasticsearch
runs on the `observability` node, a `t3.medium` on-demand instance shared with
Prometheus, Grafana and Alertmanager. Its share is split by memory request:
2 GiB of the 3,276 MiB requested on the node, 62%.

| item | arithmetic | per month |
|---|---|---|
| observability node, whole | $0.0416/h × 730 h | $30.37 |
| Elasticsearch share of it | 62% | $18.83 |
| Elasticsearch disk, 30 GiB gp3 | 30 × $0.08 | $2.40 |
| **Elasticsearch** | | **about $21** |
| Kibana, 2 GiB slice of a platform node | same method, estimate | $15 to $19 |
| Fluent Bit, 128 MiB on each of five nodes | estimate | about $3 |
| **Logging stack** | | **about $40** |

## Against the budget

The programme budget `u25c-org-monthly` is $200. August closed at $156.81.
September was at $109.93 on the 10th, on pace for about $330.

Elasticsearch is about 10% of the budget and the full logging stack about
20%. Both are fixed costs: at 100 MB a day, log volume changes nothing. The
September overrun is not caused by logging.

## Headroom

- Disk: 1 GB used of 30 GiB. Ingest would have to grow thirty times before
  it mattered, and a bigger disk costs $0.08 per GiB. Retention could be
  raised from 7 to 30 days at no cost.
- Memory: 2 GiB on a single small node. This is the real limit. Elasticsearch
  will slow down under heavier search or ingest before it runs out of disk.
- If application namespaces start producing real traffic, re-run the
  measurement below. The per-namespace table is the early warning.

## Recommendations

1. Fix the two error loops at the source, in the monitoring and keda
   workstreams. Do not drop them in Fluent Bit: dropping error loops at the
   collector hides real problems, which is the opposite of the pipeline's job.
2. Leave the disk and retention as they are until volume changes. There is no
   saving to be had; the cost is the node, not the data.
3. Re-run this benchmark when app namespaces go live, or if a daily index
   passes 500 MB.

## How to repeat it

All queries run inside the Elasticsearch pod, because it has no route from
outside the cluster.

```bash
PW=$(kubectl --context u25c-shared -n platform-logging get secret platform-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
es() { kubectl --context u25c-shared -n platform-logging exec platform-es-default-0 -c elasticsearch -- curl -sk -u "elastic:$PW" -H 'Content-Type: application/json' "https://localhost:9200$1" "${@:2}"; }
```

Per-day totals:

```bash
es '/_cat/indices/logs-*?v&h=index,docs.count,store.size&s=index'
```

Share per namespace, then per pod:

```bash
es '/logs-*/_search?size=0' -d '{"aggs":{"ns":{"terms":{"field":"kubernetes.namespace_name.keyword","size":30}}}}'
es '/logs-*/_search?size=0' -d '{"aggs":{"pod":{"terms":{"field":"kubernetes.pod_name.keyword","size":10}}}}'
```

Read five lines from any pod that stands out:

```bash
kubectl --context u25c-shared -n <namespace> logs <pod> --tail=5
```

Node share, from the node Elasticsearch is on:

```bash
N=$(kubectl --context u25c-shared -n platform-logging get pod platform-es-default-0 -o jsonpath='{.spec.nodeName}')
kubectl --context u25c-shared describe node $N | grep -A16 'Non-terminated Pods'
```

Budget: AWS console, management account, Budgets, `u25c-org-monthly`.
