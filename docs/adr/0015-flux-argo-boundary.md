# 0015. Flux owns the Argo CD control plane, Argo CD owns its custom resources

**Status:** Proposed
**Date:** 2026-08-15
**Deciders:** @argocd, @flux, @cto

## Context

`gitops-argocd` states the boundary between the two GitOps controllers in prose:

> Flux owns the platform; Argo owns what runs on it. [...] **A resource has exactly
> one controller.** If Argo reconciles it, Flux must not. Overlap is not redundancy —
> it is two controllers reverting each other.

That rule is correct and is not in dispute. It is also not yet actionable, because it
does not answer the question Wave 6 opens with: **Argo CD is itself a thing that runs
on the platform.** A Deployment, a StatefulSet, a set of CRDs and four ConfigMaps have
to be installed by something before any `Application` can exist. "Flux owns the
platform, Argo owns what runs on it" places Argo CD on both sides of its own boundary.

The question is not academic, because of one detail of the upstream chart. The
`argo-cd` Helm chart **renders `argocd-cm` and `argocd-rbac-cm` itself**, from
`configs.cm` and `configs.rbac` values. Those two ConfigMaps hold the SSO connector
and the RBAC policy — precisely the configuration the `argocd` workstream will iterate
on, and precisely what `gitops-argocd#1` is about. Any boundary drawn between "the
install" and "the configuration" cuts through a resource the chart emits as one unit,
which is the failure mode the README rule exists to prevent.

The repository layout `gitops-argocd/README.md` publishes — `apps/`,
`applicationsets/`, `projects/` — contains no directory for a Helm release, a chart
source, or a namespace. The README has, in effect, already assumed this decision
without recording it.

`gitops-argocd` is empty today, so this is being decided before there is anything to
migrate. That will not be true in a week.

## Decision

The boundary is drawn at **`kind`**, not at directory or concern.

- **Flux installs and owns the Argo CD control plane.** The `HelmRepository`, the
  `HelmRelease`, everything the chart renders — Deployments, Services, CRDs, RBAC, and
  the `argocd-cm` / `argocd-rbac-cm` ConfigMaps — plus the `argocd` namespace and the
  sealed OAuth secret. These live in `gitops-flux` under
  `infrastructures/base/argo-cd/` and `infrastructures/dev/25c-shared/argo-cd/`,
  following the same three-step component pattern as every other add-on.

- **Argo CD owns every `argoproj.io` custom resource.** `AppProject`,
  `ApplicationSet`, `Application`, and later `Workflow` / `WorkflowTemplate`. These
  live in `gitops-argocd` and Flux never applies them.

| Kind | Controller | Repository |
|---|---|---|
| `HelmRepository`, `HelmRelease` | Flux | `gitops-flux` |
| Argo CD Deployments, Services, CRDs | Flux (via chart) | `gitops-flux` |
| `argocd-cm`, `argocd-rbac-cm` (SSO, RBAC) | Flux (via chart values) | `gitops-flux` |
| `Namespace` `argocd`, `app-dev`, `app-stage`, `app-prod` | Flux | `gitops-flux` |
| `AppProject`, `ApplicationSet`, `Application` | Argo CD | `gitops-argocd` |
| `Workflow`, `WorkflowTemplate`, `CronWorkflow` | Argo CD | `gitops-argocd` |

The handover is **one object**: a single `Application` shipped by Flux, pointing at
`gitops-argocd` with directory recursion. Everything downstream of it is Argo's.
That object is the only place the two controllers meet, and it is deliberately the
smallest possible seam — Flux creates it and never looks inside.

Ownership of the Argo CD component directories in `gitops-flux` goes to
`@Ubuntu-25c-market-prep/argocd` via CODEOWNERS, matching the entries `istio`,
`scaling` and `utils` already have there:

```
/infrastructures/base/argo-cd/                @Ubuntu-25c-market-prep/argocd
/infrastructures/dev/25c-shared/argo-cd/      @Ubuntu-25c-market-prep/argocd
```

**These two lines must sit *below* the file's `*` entry, and in the natural place
they would not.** CODEOWNERS is last-matching-pattern-wins, and `gitops-flux` ends
with

```
*     @Ubuntu-25c-market-prep/flux @Ubuntu-25c-market-prep/cto
```

so every per-component entry above it — `istio`, `scaling`, `utils`, and the
`flux` delivery paths — is inert today, and `@flux` plus `@cto` own the whole
tree. Added alongside the other component entries, the two lines above would
produce a diff that reads correctly and changes nothing.

This is demonstrable rather than theoretical, and not specific to `gitops-flux`.
`infra-aws` has the same shape: `infra-aws#54` changes only `/ecr/`, whose
CODEOWNERS entry names `@infra`, and GitHub auto-requested `@cto` alone.

Reordering those files is deliberately **out of scope here** — it changes review
rights for six workstreams that have not been consulted, and it should be its own
pull request against each repository. But this ADR's mitigation depends on it, so
it must not be assumed to already work.

The repository a file sits in decides which controller applies it. CODEOWNERS decides
who reviews it. Those are different questions and this ADR answers both deliberately.

## Alternatives considered

**Argo CD bootstraps and manages itself.** Install once with `helm install` or
`kubectl apply`, then declare an `Application` that manages the `argocd` namespace,
so the whole workstream lives in one repository. This is the common upstream pattern
and it is what the mentor reference material for this workstream does. Rejected on two
counts. The bootstrap step is imperative and unreproducible — a cluster rebuild starts
with someone remembering a command, which is exactly what ADR 0002's single cluster
makes expensive to get wrong. More seriously, a self-managing Argo CD upgrading its own
CRDs can deadlock: the sync that replaces the CRDs is executed by the controller being
replaced, and recovering means the manual `kubectl apply` the pattern was supposed to
eliminate, performed under pressure.

**Split at concern rather than kind — Flux installs the chart, `gitops-argocd` ships
`argocd-cm` and `argocd-rbac-cm`.** Superficially the most attractive option, because
it puts SSO and RBAC in the repository whose name matches them, and it keeps
`gitops-argocd#1` inside `gitops-argocd`. Rejected because it is the one option the
README's rule forbids outright. The chart renders those ConfigMaps whether or not a
second copy exists, so both controllers would hold a claim on the same object and
revert each other on their respective intervals — Flux every 20h, Argo continuously.
The symptom would be RBAC that silently reverts hours after a merge, which is a bad
thing to debug and a worse thing to debug during an access incident. Suppressing the
chart's copy (`configs.cm.create: false`) technically resolves the conflict, at the
cost of running the chart in a configuration upstream does not test and losing the
values-schema validation that would have caught the field error in `gitops-flux#93`.

**Give Argo CD its own Flux `GitRepository` and let Flux reconcile `gitops-argocd`
directly.** Rejected because it makes Flux the controller for `Application` objects,
which inverts the entire point of adopting a second GitOps controller: product
delivery would once again be gated on the Flux reconcile interval and the `flux`
workstream's review. It also revives the second-source cost ADR 0011 named — an
additional `GitRepository`, `Kustomization` and `dependsOn` to bootstrap and monitor.
Under this ADR that cost does not appear at all: Argo CD reads `gitops-argocd` with
its own credentials, and Flux's single `GitRepository` is untouched.

**Defer the decision and let it emerge from the first pull request.** Rejected because
both repositories are empty right now, which is the cheapest this decision will ever
be. The `argocd` and `flux` workstreams would otherwise discover the boundary by
merging two PRs that both claim `argocd-cm`.

## Consequences

- **`gitops-argocd#1` is mostly a pull request against `gitops-flux`, and that will
  look wrong.** An issue titled `[argocd] Install Argo CD with SSO and RBAC per
  workstream`, filed in `gitops-argocd`, produces a diff in a different repository
  touching a chart. Reviewers should expect this and the PR should link here. If this
  ADR is not merged first, that PR is unreviewable.

- **The `argocd` workstream's most-iterated file lives in the `flux` repository, and
  this is the real cost.** RBAC policy changes — adding a team, granting a role, fixing
  someone's access — are changes to `configs.rbac` in a `HelmRelease`. They inherit
  `gitops-flux` branch protection and the Flux reconcile interval, currently 20h, so an
  access fix is not immediate without `flux reconcile`. The CODEOWNERS entries above are
  intended to keep review with `@argocd` rather than `@flux` — but they only address who
  approves, never where the file lives or how fast it lands, **and they do not work at
  all unless that file is reordered first**. Treat the reordering as a prerequisite of
  this ADR, not a tidy-up that can follow it. If RBAC churn becomes routine, the honest
  answer is a follow-up ADR moving to `argocd-rbac-cm` managed outside the chart — not
  a quiet second copy in `gitops-argocd`.

- **A CODEOWNERS file that describes an ownership model it is not enforcing is worse
  than not having one.** `gitops-flux`'s opens with a comment explaining that component
  configuration belongs to the workstream that runs the component, and lists twelve path
  entries doing exactly that. None of them are in force. Everyone reading that file
  believes review is distributed; in practice two teams approve everything, and the
  reviewer of a `kube-prometheus-stack` schema error is whoever the catch-all named —
  which is one plausible reading of how `gitops-flux#93` merged. This ADR does not fix
  it, but it should not be discovered a third time.

- **Argo CD inherits `gitops-flux`'s blast radius, and it is currently on fire.**
  `gitops-flux#93`: the `infrastructure` Kustomization has been failing since
  2026-08-15 on an invalid field in an unrelated `HelmRelease`, and kustomize-controller
  applies the path as a unit. Under this ADR a broken `kube-prometheus-stack` blocks
  Argo CD from installing at all. That coupling is accepted — it is the same coupling
  every other add-on already lives with — but it means Wave 6 now has a dependency on
  the health of a monitoring file, and `gitops-flux#93` is a prerequisite for
  `gitops-argocd#1` rather than someone else's problem.

- **Upgrading Argo CD is a `gitops-flux` PR bumping a pinned chart version.** This is
  a gain: it inherits the pinning discipline and the "chart versions always pinned"
  convention rather than inventing a parallel one. It also means an Argo CD upgrade
  rolls pods on the Flux interval, and the `argocd` workstream does not control the
  timing.

- **A cluster rebuild is fully declarative.** `flux bootstrap` reaches Argo CD, which
  reaches the business applications, with no imperative step anywhere. This is the
  property the self-management alternative gives up.

- **The bootstrap `Application` is a single point of failure with no alarm on it.** If
  it is deleted or misconfigured, Argo CD keeps running and simply stops learning about
  new applications — no error, no failed reconcile, just silence. It needs the same
  treatment as any other silent-failure surface: alerting on `Application` count or
  sync age, which belongs with the `monitoring` workstream and is not free.

- **Pruning cuts both ways at the seam.** Flux prunes what leaves `gitops-flux`;
  deleting the bootstrap `Application` file removes the object, and Argo CD's own
  `prune: true` then removes everything it had created. That chain is correct and is
  also a single-file mistake away from deleting every business workload. The bootstrap
  `Application` warrants a comment saying so.
