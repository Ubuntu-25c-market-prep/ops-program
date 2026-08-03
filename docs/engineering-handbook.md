# Engineering Handbook

How this programme works day to day. Sixteen people, fifteen workstreams, one
cluster — the practices below exist to keep that from turning into fifteen
people waiting on one.

---

## 1. Ownership

Every repository path has exactly one owning workstream, expressed in
`CODEOWNERS` and enforced by branch protection. Ownership means three things:

- **You review it.** Nothing merges into your paths without your approval.
- **You are called about it.** If it breaks, the owning workstream is first.
- **You decide its interface.** Other workstreams consume what you publish, not
  your internals.

Shared repositories are split by directory, not shared as a free-for-all:
`gitops-flux/addons/istio/` belongs to `@istio`, `gitops-flux/addons/velero/` to
`@velero`. Six workstreams work in one repository without merge contention
because none of them touch the same files.

Since ADR 0010 this is how ownership works everywhere, not just in one repository.
Repositories are drawn on delivery boundaries; **directories and `CODEOWNERS` are
what separate workstreams.** A path entry is therefore a real permission grant —
review it like one.

If you need something in another workstream's path, open an issue against them.
Do not edit it and request review — that inverts ownership and puts the reviewer
in the position of blocking a change that is already written.

---

## 2. The unit of work

```
Epic (ops-program)
└── Task (the repo where the work lands)
    └── Branch → Pull request → Review → Merge
```

- **Epics** live in `ops-program` and own their tasks as cross-repository
  sub-issues. An epic is a workstream's slice of a wave.
- **Tasks** live where the code lands. A task that touches two repositories is
  two tasks.
- **One task, one pull request.** A pull request that closes three issues was
  three pull requests that got merged into one by accident.

Branches are `<type>/<issue-number>-<slug>`, commits are Conventional Commits
scoped to the workstream. Full detail in [CONVENTIONS.md](../CONVENTIONS.md).

---

## 3. Definition of done

A task is done when all of these are true. Not four of five.

- [ ] Merged through a reviewed pull request
- [ ] **Applied and observed working** — not "the plan looked right"
- [ ] Cost impact stated, if any
- [ ] Documented where it affects another workstream
- [ ] Runbook written, if it can page someone
- [ ] The issue is closed by the merge, not by hand

The second one carries the most weight. Terraform that plans cleanly and has
never been applied is a hypothesis.

---

## 4. Waves

Work is sequenced into waves because the dependency chain is real: the landing
zone gates the cluster, the cluster gates Flux, Flux gates every add-on, Istio
gates ZeroTrust.

A wave is not a deadline. It is a statement about what is *possible* yet. Picking
up a Wave 5 task while Wave 3 is unfinished usually means discovering halfway
that the thing you need does not exist.

If you are blocked, say so on the issue with the `blocked` label and the
`needs:<workstream>` marker. The programme board has a Blocked view, and the
weekly leads sync works through it. Silently waiting is the failure mode.

---

## 5. Pull requests

**Size.** A reviewer's attention is finite and roughly constant. A 100-line pull
request gets a real review; a 2,000-line one gets a rubber stamp. Split by
concern — configuration separate from refactor, one add-on at a time.

**Description.** Say what changed and why, link the issue, state what you
actually ran to verify. "Should work" is not verification.

**Review turnaround.** Same working day. If you cannot review properly today, say
so on the pull request so the author can find someone else rather than assume.

**Reviewing.** Distinguish the three kinds of comment so the author knows what
blocks:

| Prefix | Meaning |
|---|---|
| `blocking:` | Must change before merge |
| `suggestion:` | Worth considering, author decides |
| `nit:` | Cosmetic, never blocks |

**Approving.** Approving means you would be comfortable being paged for this
change. If you have not understood it, ask rather than approve.

---

## 6. Interfaces between workstreams

Anything another workstream depends on is an interface, and interfaces are
written down before they are built. The published set today:

| Workstream | Publishes |
|---|---|
| `security` | Account structure, IAM roles, policy exemption process |
| `infra` | VPC and CIDR allocation, cluster endpoint, ECR registries |
| `flux` | Add-on onboarding path, GitOps directory contract |
| `argocd` | Application delivery path, promotion between namespaces |
| `istio` | Gateway and VirtualService conventions, mTLS posture |
| `monitoring` | Metric naming, alert routing, SLO template |
| `tracing` | Instrumentation contract |
| `utils` | Certificate issuance, DNS records, secret sealing |

Changing an interface is a pull request against the interface documentation
**first**, reviewed by every consuming workstream, then the implementation. A
breaking change discovered by a consumer at apply time is a process failure, not
bad luck.

---

## 7. Decisions

Anything that is expensive to reverse gets an ADR in [`adr/`](adr/) — a new
layer, a tool choice, a boundary change, a security posture.

An ADR is short: context, the decision, the alternatives rejected, the
consequences you are accepting. Its value is future-you understanding why the
obvious-looking alternative was not chosen.

ADRs are immutable once accepted. Changing your mind means a new ADR that
supersedes the old one, not an edit.

---

## 8. Cost

Every pull request that adds ongoing AWS spend states the expected monthly
delta. Nodes, NAT gateways, VPC endpoints, load balancers, storage and retention
all count.

There is a hard-ish ceiling: a budget action attaches a deny SCP to the workload
account when spend crosses the threshold. It blocks new resource creation; it
does not stop what is already running. Treat it as a brake, not a safety net.

Costs that surprise people, in order of how often they surprise people:

1. **EKS extended support** — $0.60/hr, a 6× jump per cluster. An expired
   version costs more than the entire observability stack.
2. **Public-subnet nodes** — there are no NAT gateways ([ADR 0005](adr/0005-public-subnets-no-nat.md)),
   so nodes carry public IPs and the security group is the only barrier. IMDSv2
   with hop limit 1 is mandatory, not advisory.
3. **Cross-AZ traffic** — $0.02/GB round trip. A service mesh will route across
   AZs unless told not to.
4. **Observability retention** — Prometheus, Loki and Elasticsearch on EBS grow
   without bound unless tiering is designed in up front.

Monthly cost review is owned by `@finops`.

---

## 9. Security posture

- **No static AWS credentials, anywhere.** CI reaches AWS through GitHub OIDC
  with trust conditioned on repository and branch. Pull requests may plan; only
  the protected branch may apply.
- **Repositories are public.** Never commit `.tfvars`, state, kubeconfigs, key
  material, or bare account ids. Push protection and the CI forbidden-files
  check are backstops, not the control — the control is you.
- **One cluster means one OIDC provider.** Every IRSA trust policy must be
  conditioned on `namespace:serviceaccount`, or a pod in a dev namespace can
  assume a production role. Kyverno enforces this; do not rely on convention.
- **Least privilege is per-path.** State access is per-prefix, deploy roles are
  per-repository, and CODEOWNERS is per-directory. If you need broader access to
  do your work, that is a design conversation, not a permissions ticket.

---

## 10. When something breaks

1. **Stop the bleeding first.** Roll back, scale down, detach the policy.
   Understanding can wait; impact cannot.
2. **Say it out loud early.** A problem announced at 20% confidence is cheaper
   than one announced at 100% an hour later.
3. **Write the incident note the same day**, while you still remember the
   ordering. What happened, what you saw, what you did, what you would need to
   have known.
4. **The fix is not the last step.** The last step is the thing that would have
   caught it — an alert, a policy, a test, a runbook.

No blame in incident notes. The question is always what made the mistake easy to
make, never who made it.
