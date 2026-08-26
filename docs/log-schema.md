# Log Schema

What a log line must look like for the platform to index it well, and what the
logging pipeline does to every line regardless.

> **The one-sentence version:** print JSON with `timestamp`, `level` and
> `message`; the pipeline attaches where it came from; everything conforming is
> fully searchable in Kibana, everything else is stored as a plain blob.

This document is the contract behind the EFK pipeline (epic
[#28](https://github.com/Ubuntu-25c-market-prep/ops-program/issues/28)). Its
field names are what the Fluent Bit configuration maps every source into —
change them here first, config second, never the reverse.

---

## 1. Who this binds

In order of how mechanically the rules apply:

1. **The pipeline itself** (`ws:logging`) — the Fluent Bit configuration
   implements this schema: it parses JSON lines, renames known variants to the
   canonical field names below, and attaches the Kubernetes fields.
2. **Platform components** — whoever configures a component (Helm values,
   flags) enables its JSON log output where the vendor provides one. Most
   already default to it (Flux, Elasticsearch); some need a flag (Istio).
3. **Application authors** — configure your logging library once per app to
   emit the format below. Nothing enforces this at admission; the consequence
   of skipping it is §5.

## 2. Format

One JSON object per line, printed to stdout/stderr. No multi-line log
statements — a stack trace goes *inside* a field (§4), not across lines.

```json
{"timestamp":"2026-08-22T09:14:02Z","level":"error","message":"payment failed for user 448"}
```

## 3. Required fields

| Field | Rule | Why this exact rule |
|---|---|---|
| `timestamp` | RFC 3339 / ISO 8601, **UTC**, e.g. `2026-08-22T09:14:02Z` | One time zone across the fleet, or "what happened at 14:03" has three answers |
| `level` | exactly one of `debug` `info` `warn` `error`, lowercase | A fixed vocabulary is what makes "show all errors" reliable |
| `message` | human-readable text | The part a person reads |

Anything a language's standard logging library can produce in one line of
setup. That is deliberate: a three-field demand gets obeyed.

## 4. Optional standard fields

Not required — but if the information exists, it goes in these names, not
invented ones:

| Field | Contents |
|---|---|
| `trace_id` | Request correlation id, as issued by the tracing stack (`ws:tracing` interface) |
| `error.stack` | Stack trace on `level: error`, as a single JSON string |

Extra app-specific fields are allowed (`user_id`, `order_id`, ...): lowercase
`snake_case`, values that are strings or numbers, no nested objects beyond
`error.*`.

## 5. What the pipeline does to every line

Attached automatically by Fluent Bit at collection time — no application ever
writes these, and they cannot be spoofed by the line's content:

| Field | Source |
|---|---|
| `kubernetes.namespace` | where the pod runs |
| `kubernetes.pod` / `kubernetes.container` | which pod, which container |
| `kubernetes.labels.*` | the workload's labels, including `u25c.io/workstream` and `u25c.io/owner` |

Then one of two paths:

- **Line parses as JSON** → fields extracted, known variants renamed to the
  canonical names (`ts`/`time` → `timestamp`, `msg` → `message`,
  `severity` → `level`), fully searchable.
- **Line does not parse** → stored whole in a single `log` field with only the
  Kubernetes fields attached. Still retained, but not filterable by level,
  time or any field. Non-conforming logs are second-class by consequence, not
  by punishment.

## 6. Limits and prohibitions

- **Line size cap: 32 KiB — over-long lines are dropped, not truncated.**
  Fluent Bit's `tail` input reads a line into a buffer of at most
  `Buffer_Max_Size`; with `Skip_Long_Lines On` anything larger is skipped
  whole and a warning is written to the collector's own log. There is no
  truncate-and-forward mode, so a 40 KiB line does not arrive in part — it
  does not arrive at all. Keep log lines small; put bulk payloads somewhere
  that is not the log stream.
- **No secrets in log lines** — no passwords, tokens, keys, full card numbers.
  Logs are retained for weeks and readable by every workstream; a secret in a
  log is a secret published. No tooling reliably detects this — you are the
  control, same as with public repositories.
- **Do not log at `debug` in production namespaces** by default; it is noise
  paid for in storage and ingest (§ cost note in the epic: Elasticsearch is
  the most expensive add-on on the platform).

## 7. Examples

Conforming (app):

```json
{"timestamp":"2026-08-22T09:14:02Z","level":"info","message":"order created","order_id":"A-4471","trace_id":"7f3a2b"}
```

Conforming (error with stack):

```json
{"timestamp":"2026-08-22T09:14:03Z","level":"error","message":"payment failed","error.stack":"PaymentError: declined\n  at charge (payment.go:88)"}
```

Non-conforming — stored as a blob, unsearchable by field:

```
ERROR!! 22.08.2026 payment failed somewhere
```
