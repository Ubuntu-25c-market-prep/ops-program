# 0011. Carve `platform-security` back out of `gitops-flux`

**Status:** Proposed
**Date:** 2026-08-05
**Deciders:** @cto, @security, @zerotrust, @flux
**Amends:** [0010](0010-one-repository-per-delivery-boundary.md) — partially, for
`platform-security` only

## Context

ADR 0010 consolidated ten repositories into six and archived `platform-addons`,
`platform-observability`, `platform-security` and `infra-modules`. Its reasoning holds
and is not in dispute here. This ADR revisits exactly one of the four merges.

ADR 0010 named the cost of the merge in its own Consequences:

> **CODEOWNERS becomes load-bearing.** It is now the only thing separating six
> workstreams inside `gitops-flux`. Previously a mis-scoped path entry leaked review
> rights within one component's repository; now it leaks them across the whole platform
> tree. Path entries are reviewed by `@cto` accordingly.

That consequence is acceptable for add-on values and dashboards. It is not acceptable for
the security tree, and the reason is specific to this platform rather than general
security nervousness.

The platform runs **one cluster with one OIDC provider**, and environments are namespaces
rather than accounts (ADR 0002, ADR 0003). Everything a separate account would normally
enforce — a dev pod not reaching a prod service, a dev service account not assuming a
prod role — is enforced instead by Kyverno admission policy and default-deny
Authorization/NetworkPolicies. `CONVENTIONS.md` already states this outright: the IRSA
namespace condition "is enforced by Kyverno, not by convention."

So inside `gitops-flux`, the three `/security/*` path entries are the last control
standing between six workstreams and the rules that decide what may run. A single
mis-scoped path — a `/security/` that should have been `/security/kyverno/`, a trailing
glob, a reordering, since CODEOWNERS is last-match-wins — hands admission-policy approval
to whoever the broader entry names. The reviewer of that mistake is reviewing a
`CODEOWNERS` diff, not a policy diff.

ADR 0010's own test for a repository boundary is:

> a separate build pipeline, a separate controller, a separate credential, a separate
> **blast radius**

Admission control is a separate blast radius. The test was met before the merge and the
merge did not notice.

## Decision

Seven repositories. `platform-security` is un-archived and re-owns Kyverno, Policy
Reporter and ZeroTrust — `kyverno/`, `policy-reporter/`, `zerotrust/`, with the same path
ownership those directories carried before ADR 0010.

This **upholds ADR 0010's rule rather than overturning it**. The rule was never "fewer
repositories"; it was "a boundary needs a reason that changes how or when code reaches
production". Security policy has one. `platform-addons`, `platform-observability` and
`infra-modules` do not, and they **stay archived** — none of them holds a control that
decides what may run, and the review rights that leak inside them leak onto Helm values.

`gitops-flux` keeps `clusters/`, `addons/` and `observability/`, and drops its
`/security/*` CODEOWNERS entries and its `security/` tree.

The zerotrust task *"Condition every IRSA trust policy on namespace and service
account"* stays in `infra-aws`. It is Terraform applied by the AWS apply role, which is a
different delivery boundary again — the same reasoning, applied consistently.

## Alternatives considered

**Leave it merged and tighten review on `CODEOWNERS` instead** — require `@cto` plus
`@security` on any diff touching the file, which is close to free and changes nothing
structurally. Rejected because it makes a single reviewable file the only control, which
is precisely the failure mode being designed out. It also degrades quietly: the rule
lives in a branch-protection setting nobody re-reads, and it protects the file while
saying nothing about a `HelmRelease` in `clusters/` that reconciles the security tree
from somewhere else.

**Carve out all four archived repositories** — the clean revert. Rejected on merit, not
effort. ADR 0010 is right about `platform-addons`, `platform-observability` and
`infra-modules`: their split was drawn per component, the wiring cost it imposed was real
and recurring, and nothing about how their code reaches production differs. Reverting
them to undo one mistake would reintroduce three.

**Keep the policies in `gitops-flux` but give the security tree its own repository *and*
leave a copy of the paths in CODEOWNERS** — belt and braces. Rejected because two
authorities over the same paths is not two controls, it is an ambiguity, and the copy
that is wrong is the one nobody is reading.

**Move only the Kyverno tasks and leave ZeroTrust in `gitops-flux`** — smaller change.
Rejected because mesh identity and admission policy are the same control surface in a
single-cluster design; splitting them puts half the enforcement inside the blast radius
this ADR exists to shrink.

## Consequences

- Admission policy has a review population that cannot be widened by an unrelated
  CODEOWNERS edit. Branch protection on `platform-security` — one approving review,
  CODEOWNERS review required, linear history — applies to policy changes on its own.
- **Flux now needs a second source, and this is the real cost.** `gitops-flux` was
  designed around one `GitRepository`. Security manifests living elsewhere means a second
  `GitRepository` plus its own `Kustomization` under `clusters/platform/sources/`, with an
  explicit `dependsOn` so policy reconciles in a defined order relative to the add-ons it
  governs. That is one more source to bootstrap, authorise and monitor, and a second place
  a reconcile can wedge. Nothing exists to rewire today — the trees are empty — but the
  `flux` epic must land this, and it should not be discovered during bootstrap.
- **Issue numbers are restored, not re-minted.** ADR 0010 accepted that existing
  `Closes platform-security#n` references would dangle. Because the original issues were
  closed rather than deleted, they are reopened in place: `platform-security#1`–`#11` keep
  their numbers and those references resolve again. The `gitops-flux` copies created by
  the ADR 0010 execution are closed as not planned and point at the originals.
- The `platform` layer prefix comes back for exactly one repository. A one-member layer
  looks like an inconsistency in the repo list, and it is; the alternative is renaming the
  repository, which throws away the restored issue references for cosmetics.
- **Two reversals in three days is the thing to actually worry about.** The programme has
  now moved this boundary twice before any policy exists to sit behind it. The cost so far
  has been issue churn rather than migrated code, which is why it was worth doing now, but
  the next boundary change should wait for something concrete to be behind it. If a third
  argument arrives, it needs code, not a diagram.
- `bootstrap-labels.sh` and `bootstrap-codeowners.sh` go from six targets to seven. Both
  still exclude the three genuinely archived repositories, and that exclusion is still
  load-bearing — the label API fails the whole run on a read-only repo.
