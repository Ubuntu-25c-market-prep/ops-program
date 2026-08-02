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
