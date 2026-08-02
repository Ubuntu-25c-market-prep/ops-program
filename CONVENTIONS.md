# Naming and Working Conventions

Binding for every repository in `Ubuntu-25c-market-prep`. Changes go through an ADR in
`docs/adr/`.

## Repositories

Format: `<layer>-<domain>`, lowercase kebab-case.

Layers: `infra` · `platform` · `gitops` · `apps` · `ops`

GitHub organisations are flat — there are no subgroups — so the layer prefix is what
produces visual grouping in the repository list.

| Repo | Layer | Owns |
|---|---|---|
| `infra-aws` | infra | Terraform for AWS: Org, IdC, VPC, EKS, ECR, Bedrock |
| `infra-modules` | infra | Reusable, tag-versioned Terraform modules |
| `platform-addons` | platform | Cluster add-ons: core, scaling, utils, velero, rancher, istio |
| `platform-observability` | platform | Monitoring, logging, tracing, finops |
| `platform-security` | platform | Kyverno, Policy Reporter, ZeroTrust |
| `gitops-flux` | gitops | Flux desired state — platform apps |
| `gitops-argocd` | gitops | Argo CD / Workflows — business apps |
| `apps-business` | apps | Business application source |
| `ops-program` | ops | Epics, backlog manifest, ADRs, runbooks |
| `.github` | ops | Org profile, shared workflows, templates |

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

SemVer, `vX.Y.Z`. Terraform modules in `infra-modules` are tagged per module:
`<module>/vX.Y.Z` — for example `vpc/v1.2.0`.

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

Module sources pin a tag, never a branch:

```hcl
module "vpc" {
  source = "git::https://github.com/Ubuntu-25c-market-prep/infra-modules.git//vpc?ref=vpc/v1.2.0"
}
```

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
