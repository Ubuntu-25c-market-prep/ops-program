# 0010. One repository per delivery boundary, not per component

**Status:** Proposed
**Date:** 2026-08-03
**Deciders:** @cto, @pm, @infra, @flux

## Context

The programme created ten repositories in one sitting, before any code existed.
The split was drawn along **components** — one repository per thing the platform
runs. Two days later, seven of the ten contain a README, a CODEOWNERS file and a
call to the shared security workflow. No Terraform, no manifests, no charts.

Ten repositories are not free. Each one carries a CODEOWNERS file, a branch
protection configuration, a copy of the 35-label taxonomy, and a place for issues
to hide. `scripts/bootstrap-labels.sh` exists solely to apply the same labels ten
times. The backlog seeder has already created 62 issues in four repositories that
contain no code and, on the current wave plan, will contain none for weeks.

The cost is paid per repository per change, and it compounds: wiring a single
add-on into the cluster today means two pull requests in two repositories, with
no way for either to be reviewed against the other and no way for CI to plan one
against the other.

The component split also produced a boundary nobody defends on its merits. The
values for Karpenter live in `platform-addons`; the `HelmRelease` that consumes
them lives in `gitops-flux`. Both are reconciled by the same controller, on the
same cadence, from the same cluster state. The boundary between them is
administrative, not operational.

## Decision

Six repositories, drawn along **delivery boundaries**.

> A repository boundary is justified when something about *how or when code
> reaches production* differs across it — a separate build pipeline, a separate
> controller, a separate credential, a separate blast radius. It is not justified
> by which component the code happens to configure.

| Repository | Absorbs | Delivery boundary it represents |
|---|---|---|
| `infra-aws` | `infra-modules` | Terraform, applied by CI with the AWS apply role |
| `gitops-flux` | `platform-addons`, `platform-observability`, `platform-security` | Reconciled by Flux |
| `gitops-argocd` | — | Reconciled by Argo CD |
| `apps-business` | — | Built by CI into images; not reconciled by anything |
| `ops-program` | — | Not delivered; programme record |
| `.github` | — | Cannot be merged: GitHub requires this exact name |

Ownership that previously came from repository boundaries now comes from
CODEOWNERS paths. Every path entry from the absorbed repositories is carried over
unchanged.

Modules are sourced by relative path. Per-module version tags (`vpc/v1.2.0`) are
discontinued.

### Why `apps-business` stays out of `gitops-argocd`

The same reasoning that merges `platform-addons` into `gitops-flux` would appear
to merge `apps-business` into `gitops-argocd`. It does not, and the asymmetry is
the point of the rule rather than an exception to it.

`apps-business` has a build pipeline. It produces container images, and the tag
of a newly built image must be written back into whatever Argo CD reads. If the
source and the delivery config share a repository, that write-back is a commit to
the same repository that triggered the build — a loop, held open only by
`[skip ci]` hygiene and path filters that someone will eventually get wrong.

Nothing in `gitops-flux` is built from source. Helm values are configuration, not
artefacts; there is no pipeline writing tags back into them. The loop does not
exist, so neither does the reason to split.

### What this does not change

**ADR 0004 stands unchanged.** State segmentation is a property of directories,
not repositories: one state file per layer, one backend block per directory,
dependencies flowing downward through SSM parameters. Every argument in
`terraform-state-strategy.md` — lock contention, plan time, blast radius,
per-prefix IAM — survives this decision untouched. Repository count was never
what bought state segmentation, and merging repositories does not spend it.

No repository is renamed. `infra-aws` keeps its name, so the OIDC subject claim
in `iam/main.tf` remains valid and no trust policy widens.

## Alternatives considered

**Keep all ten** — costs nothing today and is the status quo. Rejected because
the cost is not paid today; it is paid on every add-on wired, every label
bootstrap, every cross-repository sub-issue, for the length of the programme. The
cheapest moment to consolidate is while seven repositories are still empty, and
that moment expires as soon as the Wave 2 epics land.

**A single repository for everything** — one CODEOWNERS, one board, one clone.
Rejected on blast radius. `infra-aws` holds the OIDC trust for the AWS apply
role; putting application source in the same repository makes every workflow in
it a candidate path to `terraform apply`. The repository boundary is a real
security control there, and the `aws-apply` environment gate is a second one
rather than a replacement for it. The Argo write-back loop above applies as well.

**Seven repositories, keeping `infra-modules` separate** — honours that
repository's own documented rationale: modules version independently, so one
consumer can hold `vpc/v1.2.0` while another moves to `v1.3.0`. Rejected because
that argument requires several consumers on different cadences and there is
exactly one, with no second planned. What the tag cycle bought was hypothetical;
what it cost was a mandatory two-pull-request dance per module change and no way
to change a module and its caller atomically, so breaking changes surfaced at
adoption rather than at review.

This decision **supersedes the "Why a separate repository" section of
`infra-modules/README.md`**, which is carried into `infra-aws/modules/README.md`
with the reasoning inverted and the reversal path documented.

**Merging `ops-program` in as well** — would put every issue in one repository
and remove cross-repository sub-issues entirely, which is the single largest
source of friction the split created. Rejected for now because the programme
record has a different audience and a different review population than the code,
and because the sub-issue hop is tolerable at six repositories. Worth revisiting
if it is still annoying in a month.

## Consequences

- Wiring an add-on is one pull request. A values change cannot merge without the
  `HelmRelease` that consumes it, and CI can plan a module against its caller.
- `bootstrap-labels.sh` and `bootstrap-codeowners.sh` shrink from ten targets to
  six. Branch protection is configured in six places instead of ten.
- **CODEOWNERS becomes load-bearing.** It is now the only thing separating six
  workstreams inside `gitops-flux`. Previously a mis-scoped path entry leaked
  review rights within one component's repository; now it leaks them across the
  whole platform tree. Path entries are reviewed by `@cto` accordingly.
- **`gitops-flux` becomes the busiest repository in the org.** Merge contention
  moves from structurally impossible to merely unlikely. Directory ownership
  keeps engineers off each other's files, but `main` is a single protected branch
  with linear history, and six workstreams landing work in the same week will
  feel it. This is the thing that will hurt later.
- Issues re-created in the surviving repositories take new numbers. Existing
  `Closes <repo>#<n>` references to the archived repositories dangle.
- Source repositories are **archived, not deleted** — their issues stay readable
  and inbound links keep resolving.
- Without version tags, `terraform plan` is the only thing standing between a
  module change and its consumers. The `paths:` filter that makes `modules/**`
  trigger a plan is therefore load-bearing, and is commented as such.
- Reversible. The module contract forbids `backend` blocks, `provider` blocks and
  hardcoded account ids, so `modules/` can be extracted back into its own
  repository as a normal split if a second consumer appears. The same is true of
  each tree inside `gitops-flux`.
