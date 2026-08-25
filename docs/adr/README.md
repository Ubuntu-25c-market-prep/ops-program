# Architecture Decision Records

An ADR records a decision that is expensive to reverse, and *why the obvious
alternative was not chosen*. That second part is the whole value — six months
from now the code shows what was decided, and only the ADR shows what was
considered and rejected.

## When to write one

- A new Terraform layer, repository, or account
- A tool choice with lock-in (mesh, GitOps controller, observability backend)
- A change to a boundary between workstreams
- A security posture decision
- Anything you would be annoyed to have to re-argue

Not for: routine configuration, reversible tweaks, anything a comment covers.

## Process

1. Copy `template.md` to `NNNN-short-slug.md`, next number, no gaps.
2. Open a pull request. Consuming workstreams review it.
3. Merged means **Accepted**.
4. ADRs are immutable once accepted. Changed your mind? Write a new one that
   supersedes it and mark the old one `Superseded by NNNN`.

## Index

| # | Decision | Status |
|---|---|---|
| [0001](0001-github-over-gitlab.md) | GitHub over GitLab for source and planning | Accepted |
| [0002](0002-single-cluster.md) | One EKS cluster, environments as namespaces | Accepted |
| [0003](0003-single-workload-account.md) | One workload account, management kept empty | Accepted |
| [0004](0004-terraform-state-segmentation.md) | Terraform state segmented by layer | Accepted |
| [0005](0005-public-subnets-no-nat.md) | Public subnets only, no NAT gateway, IPv4 | Accepted |
| [0006](0006-single-az-node-placement.md) | Two AZs of subnets, all node capacity in one | Accepted |
| [0007](0007-ou-layout-and-scp-guardrails.md) | Two OUs, guardrails on the OUs and never on the root | Accepted |
| [0008](0008-identity-center-four-tier-access.md) | Four permission sets, not fifteen | Accepted |
| [0009](0009-audit-the-management-account-with-its-own-trail.md) | Audit the management account with its own trail, not an organisation trail | Proposed |
| [0010](0010-one-repository-per-delivery-boundary.md) | One repository per delivery boundary, not per component | Proposed · amended by 0011 |
| [0011](0011-carve-platform-security-back-out.md) | Carve platform-security back out of gitops-flux | Proposed |
| [0014](0014-per-cluster-argo-cd.md) | One Argo CD per cluster, and a repository layout where clusters are additive | Proposed |
| [0012](0012-opencost-over-kubecost.md) | OpenCost over Kubecost for Kubernetes cost visibility | Proposed |
| [0013](0013-node-capacity-from-karpenter-pools.md) | Node capacity from Karpenter pools split by failure tolerance | Proposed |
| [0015](0015-flux-argo-boundary.md) | Flux owns the Argo CD control plane, Argo CD owns its custom resources | Proposed |
