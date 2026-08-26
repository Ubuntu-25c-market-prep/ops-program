# Documentation

Standards and practice for the platform programme. Everything here is binding —
deviations need an ADR, not a conversation.

## Start here

New to the programme? Read in this order:

1. **[Engineering Handbook](engineering-handbook.md)** — how we work. Ownership,
   the unit of work, definition of done, review, interfaces, incidents.
2. **[CONVENTIONS.md](../CONVENTIONS.md)** — every naming rule in one place:
   repositories, branches, commits, issues, labels, AWS resources, Terraform
   state keys, Kubernetes namespaces.
3. **[Terraform Standards](terraform-standards.md)** — file layout, pinning,
   variables, safety, secrets, review criteria.
4. **[Terraform State Strategy](terraform-state-strategy.md)** — the layer model,
   state keys, how layers pass values, and the rules for adding one.
5. **[Log Schema](log-schema.md)** — what a log line must look like, what the
   pipeline attaches to it, and what happens to lines that don't conform.
6. **[Secret Management](secret-management.md)** — IRSA first, sealed-secrets for
   what is left, where the controller key lives, and how everything rotates.
7. **[Node Placement](node-placement.md)** — the `@scaling` contract for
   putting a workload on a node: the five pools, the selector and toleration,
   and the five constraints that bite.
8. **[Gateway API and VirtualService Conventions](gateway-conventions.md)** — how app teams
   route traffic through the mesh: ownership boundary, naming, TLS.
9. **[ADRs](adr/)** — why things are the way they are.

## Quick reference

| Question | Answer |
|---|---|
| Where does my epic live? | `ops-program`. Tasks live in the repo where the code lands. |
| Which repo owns this path? | `CODEOWNERS` in that repo. One workstream per path. |
| What is my branch called? | `<type>/<issue-number>-<slug>` |
| Where does state for a new component go? | `shared/<component>/terraform.tfstate` — and add it to the layer table |
| How do I get a value from another layer? | Read its SSM parameter under `/u25c/<scope>/<component>/` |
| Can I commit this? | Not if it is a `.tfvars`, state, kubeconfig, key material, or a bare account id |
| Which node will my workload run on? | [node-placement.md](node-placement.md) — `apps` unless you ask for another |
| Who approves my pull request? | The workstream that owns the path, per CODEOWNERS |
| This adds cost — what do I do? | State the monthly delta in the pull request |
| I disagree with a standard | Write an ADR. That is the mechanism, and it is a legitimate one. |

## The five things that cause the most damage

Learn these before your first pull request.

1. **Committing a secret to a public repository.** These repos are public. Push
   protection and CI checks are backstops; you are the control.
2. **An IRSA trust policy without a `namespace:serviceaccount` condition.** One
   cluster means one OIDC provider — an unconditioned role is assumable from any
   namespace, including dev.
3. **Applying without reading the plan.** A pull request titled "add a subnet"
   whose plan destroys a NAT gateway is caught by reading, and by nothing else.
4. **Letting the EKS version lapse into extended support.** $0.60/hr — a 6× jump,
   more per month than the entire observability stack.
5. **Editing another workstream's path instead of opening an issue.** It inverts
   ownership and makes the reviewer block work that is already written.

## Layout

```
ops-program/
├── CONVENTIONS.md          naming, binding across all repos
├── docs/
│   ├── engineering-handbook.md
│   ├── node-placement.md      node pools, the placement contract
│   ├── terraform-standards.md
│   ├── terraform-state-strategy.md
│   ├── log-schema.md
│   ├── secret-management.md
│   ├── gateway-conventions.md
│   └── adr/                architecture decision records
├── program/
│   ├── roster.yaml         person → GitHub account → workstreams
│   └── backlog.yaml        epics and tasks, seeded from here
├── runbooks/               operational procedures
└── scripts/                bootstrap and seeding automation
```
