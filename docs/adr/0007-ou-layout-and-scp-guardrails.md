# 0007. Two OUs, guardrails on the OUs and never on the root

**Status:** Accepted
**Date:** 2026-08-02
**Deciders:** @cto, @security

## Context

The organisation had no organisational units. All five accounts hung directly off
the root, which meant service control policies could only be attached in two
places: to the root, where they would also have covered the management account,
or to individual accounts, one attachment per account forever.

Sixteen people are about to share one workload account. The cost ceiling
(ADR 0003) protects against the *bill*; nothing yet protected against the shapes
of mistake that do not show up on a bill until the next statement — a cluster
built in `eu-west-1` that no dashboard or budget filter can see, an `m5.24xlarge`
launched by someone reading a blog post, a long-lived access key committed to a
public repository.

Two constraints shape everything below:

- **SCPs have no effect on the management account.** This is the same fact
  ADR 0003 turned on. Here it cuts the other way: the management account is the
  only place from which a policy that locks everyone out can be undone.
- **SCPs apply to every principal in the target**, including the account root
  user, `OrganizationAccountAccessRole`, and the CTO. There is no bypass role.

## Decision

Two organisational units under root `r-e8kk`:

```
├── u25c-workloads   → Dev (808540602855)
└── u25c-dormant     → Staging, Prod
```

The management account stays at the root, as does one SUSPENDED account that AWS
will not let us move. Guardrails attach to the **OUs**, never to the root.

`u25c-org-guardrails` on the workloads OU denies: the account root user; every
region except `us-east-1`, with the usual carve-out for services that have no
regional endpoint; EC2 instance types outside a costed allow-list; deleting or
silencing CloudTrail; deleting the state and audit buckets; and creating IAM
users, access keys or login profiles.

`u25c-org-dormant-freeze` on the dormant OU denies everything except inspection.

A `TAG_POLICY` on the workloads OU encodes the five tags from `CONVENTIONS.md`.
It is **report-only** — no `enforced_for` blocks.

## Alternatives considered

**No OUs, attach policies per account** — works today with one workload account,
and becomes a manual step every time an account is added. Rejected because the
attachment point should describe intent ("this is where work happens"), not
enumerate current membership.

**A deeper hierarchy** — Security / Infrastructure / Sandbox / Workloads, the
shape most landing-zone guides start from. Rejected as aspirational: with one
workload account, four of those OUs would be empty and the diagram would describe
an organisation that does not exist. The two OUs we have each hold accounts and
each carry a different policy.

**Guardrails on the root** — one attachment, covers everything. Rejected because
it also covers the management account and would remove the only place a bad
policy can be undone from. The saving is one `aws_organizations_policy_attachment`
resource; the cost is the escape hatch.

**Enforcing tag policy** — rejected for now, not on merit. An enforcing tag
policy rejects resource creation outright, which converts one missing tag into a
failed apply halfway through a wave, for a team learning Terraform. Revisit when
FinOps showback shows the account is already compliant.

**Closing Staging and Prod instead of freezing them** — cheaper conceptually, and
irreversible. ADR 0003 explicitly kept the decision reversible; the dormant OU
makes "unused" an enforced property rather than an intention.

## Consequences

- One region, enforced. Anything built outside `us-east-1` fails at the API, not
  at the invoice.
- The instance allow-list gates EKS managed node groups and Karpenter as well as
  direct `RunInstances` calls, because autoscaling reaches EC2 through a
  service-linked role and the SCP applies to that role too. **Removing a size the
  cluster depends on will look like a Karpenter bug, not a policy change.** The
  list must keep `t3.medium` and `t3.large` for Wave 2.
- **This will block a legitimate change at some point, and the fix is to change
  the policy, not to find a role that bypasses it.** This is not theoretical: the
  first thing the guardrail denied was our own conversion of the CloudTrail trail,
  because `cloudtrail:DeleteTrail` is on the deny list and Terraform needed to
  replace the trail. The break-glass is `detach_guardrails_command` from the
  management account, then re-apply `organization/` to restore.
- Denying `iam:CreateAccessKey` organisation-wide makes "no static credentials" a
  property of the account rather than a convention people are asked to follow. It
  will also block the first person who tries to create a service account the old
  way, which is the point.
- The tag policy reports rather than enforces, so non-compliant resources will
  exist. Someone has to read the Resource Groups compliance view for it to mean
  anything; nothing pages.
