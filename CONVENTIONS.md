# Naming and Working Conventions

Binding for every repository in `Ubuntu-25c-market-prep`. Changes go through an ADR in
`docs/adr/`.

## Repositories

Format: `<layer>-<domain>`, lowercase kebab-case.

Layers: `infra` · `platform` · `gitops` · `apps` · `ops`

GitHub organisations are flat — there are no subgroups — so the layer prefix is what
produces visual grouping in the repository list.

One repository per **delivery boundary**, not per component — see
[ADR 0010](docs/adr/0010-one-repository-per-delivery-boundary.md). A new repository
needs a reason that changes how or when code reaches production: a separate build
pipeline, controller, credential or blast radius. "It is a different component" is
not one; that is what directories and CODEOWNERS are for.

| Repo | Layer | Owns |
|---|---|---|
| `infra-aws` | infra | Terraform for AWS: Org, IdC, VPC, EKS, ECR, Bedrock, plus `modules/` |
| `platform-security` | platform | Kyverno, Policy Reporter, ZeroTrust |
| `gitops-flux` | gitops | Flux desired state and the platform config it delivers — add-ons, observability |
| `gitops-argocd` | gitops | Argo CD / Workflows — business app delivery config |
| `apps-business` | apps | Business application source and its image pipeline |
| `ops-program` | ops | Epics, backlog manifest, ADRs, runbooks |
| `.github` | ops | Org profile, shared workflows, templates |

`platform-security` is the one component repository the delivery-boundary rule keeps —
see [ADR 0011](docs/adr/0011-carve-platform-security-back-out.md). It is not an exception
to the rule but an application of it: admission control decides what may run, so its
review population is a **separate blast radius** rather than a separate component.

`platform-addons`, `platform-observability` and `infra-modules` were archived by
ADR 0010 and stay archived.

## Teams

One team per workstream, slug matching the workstream name, plus `cto`, `pm` and
`platform-all`. Eighteen total.

`infra` `security` `scaling` `argocd` `flux` `monitoring` `logging` `tracing` `utils`
`velero` `rancher` `finops` `istio` `zerotrust` `bedrock` `cto` `pm` `platform-all`

Teams are referenced in CODEOWNERS as `@Ubuntu-25c-market-prep/<slug>`.

## Branches

`main` is protected: one approving review, CODEOWNERS review required, linear history,
no force pushes, conversations resolved before merge.

Work branches: `<type>/<issue-number>-<slug>`

Types: `feat` `fix` `chore` `docs` `refactor` `test` `ci`

```
feat/42-karpenter-spot-nodepool
fix/118-istio-gateway-tls
```

## Commits

[Conventional Commits](https://www.conventionalcommits.org/). Scope is the workstream slug.

```
<type>(<scope>): <subject>

feat(scaling): add Graviton Spot NodePool with consolidation
fix(istio): correct gateway TLS secret reference
chore(ops): update CODEOWNERS
```

## Tags and releases

SemVer, `vX.Y.Z`.

Terraform modules are **not** tagged. They live in `infra-aws/modules/`, are sourced
by relative path, and version with the repository that calls them (ADR 0010).

## Issues

Title: `[<workstream>] <imperative summary>`

```
[istio] Enable STRICT mTLS in platform namespaces
[finops] Configure AWS Budgets and cost anomaly detection
```

Epics live in `ops-program`; their tasks live in the repo where the work lands and are
linked as GitHub **sub-issues**. Sub-issues work across repositories, which is what makes
this split possible.

## Pull requests

Title follows the commit convention. Body must contain `Closes #<n>` referencing the task
issue — cross-repo references use `Closes Ubuntu-25c-market-prep/ops-program#42`.

## Labels

Applied identically in every repository. Managed by `scripts/bootstrap-labels.sh`.

| Prefix | Values |
|---|---|
| `ws:` | the 15 workstream slugs |
| `type:` | `epic` `story` `task` `bug` `spike` `toil` `docs` |
| `pri:` | `P1` `P2` `P3` |
| `size:` | `S` `M` `L` `XL` |
| `env:` | `dev` `stage` `prod` |
| standalone | `blocked` `needs-review` `good-first-task` |

## AWS resources

Format: `u25c-<env>-<component>[-<suffix>]`

```
u25c-prod-vpc
u25c-prod-eks
u25c-prod-nat-1a
u25c-shared-ecr
u25c-tfstate-<account-id>
```

Every resource carries these tags. FinOps showback and Kyverno tag enforcement both
depend on them:

| Tag | Example |
|---|---|
| `Org` | `u25c` |
| `Env` | `dev` \| `stage` \| `prod` \| `shared` |
| `Workstream` | `istio` |
| `ManagedBy` | `terraform` |
| `Repo` | `infra-aws` |

## Terraform

State lives in `u25c-tfstate-<account-id>` with key `<env>/<component>/terraform.tfstate`
and native S3 locking. One directory per environment — **no workspaces**.

Modules live in `infra-aws/modules/` and are sourced by relative path (ADR 0010):

```hcl
module "vpc" {
  source = "../modules/vpc"
}
```

A module and its callers therefore change in one reviewed commit, and CI plans the
change against its real caller before merge. `modules/**` is in the workflow `paths:`
filters for exactly that reason — remove it and a module change merges unplanned.

## Kubernetes

Namespaces: `platform-<component>` for platform services, `app-<name>` for business
workloads — `platform-istio`, `platform-monitoring`, `app-storefront`.

Every workload carries the standard `app.kubernetes.io/*` labels plus:

```yaml
u25c.io/workstream: istio
u25c.io/owner: istio
```

Helm release names match the namespace component.

## Environments

One EKS cluster; environments are namespaces separated by ResourceQuota, LimitRange,
default-deny NetworkPolicy and Karpenter NodePool taints.

Because there is one OIDC provider, **every IRSA trust policy must be conditioned on
`namespace:serviceaccount`**. Without that condition a dev-namespace pod can assume a
prod role. This is enforced by Kyverno, not by convention.

## Hybrid placement

Everything starts in AWS. Add-ons are packaged so they can move to the home k3s cluster
later: Helm release plus per-environment value overlays, with no AWS-only assumption
(IRSA, ALB annotations, EBS storage classes) outside `values-aws.yaml`.

Standing constraint: home-hosted runners must never hold AWS OIDC credentials capable of
`terraform apply`. Build and test runners may move; deploy runners stay in-VPC with trust
policies conditioned on repository and branch.
