# 0008. Four permission sets, not fifteen

**Status:** Accepted
**Date:** 2026-08-02
**Deciders:** @cto, @security

## Context

The `aws-foundation` epic says "Configure IAM Identity Center with permission
sets per workstream" — fifteen workstreams, so fifteen permission sets, each
scoped to the services that workstream touches. It is sized `L` in the backlog,
and correctly so.

Attempting it surfaces the problem. A per-workstream policy has to be written
before anyone knows what the workstream actually needs, by someone who is not on
that workstream, for a wave that has not started. Scoping `istio` means guessing
at the ACM, ELB, Route 53 and EC2 permissions Istio's ingress gateway will want.
Guess low and the person is blocked at 22:00 with an `AccessDenied` and no
authority to widen their own policy. Guess high and the fifteen policies converge
on PowerUser with extra maintenance.

Meanwhile the workload account already has two other permission ceilings, both
enforced regardless of what any permission set says: the `u25c-org-guardrails`
SCP on the workloads OU (ADR 0007), and a permissions boundary.

## Decision

Four permission sets:

| Permission set | Group | Accounts | Policies |
|---|---|---|---|
| `u25c-PlatformAdmin` | `u25c-cto` | Dev, management | `AdministratorAccess` |
| `u25c-PlatformEngineer` | `u25c-engineers` | Dev | `PowerUserAccess` + scoped IAM, under `u25c-engineer-boundary` |
| `u25c-ReadOnly` | `u25c-all` | Dev, management | `ReadOnlyAccess` |
| `u25c-Billing` | `u25c-billing` | management | `Billing`, `AWSBillingReadOnlyAccess` |

Least privilege is the intersection of three layers, not the narrowness of one:

1. **Permission set** — what you may attempt.
2. **SCP on the workloads OU** — what the account will allow anyone to do.
3. **Permissions boundary** — what any role you create may inherit.

`PowerUserAccess` stops at IAM, and half this programme is IRSA, Pod Identity and
OIDC trust policies, so IAM role and policy management is added back — but
`iam:CreateRole` and everything that attaches permissions to a role are
conditioned on `iam:PermissionsBoundary` matching `u25c-engineer-boundary`. An
engineer can create the roles their workstream needs and cannot create one more
privileged than themselves.

The fifteen `u25c-ws-*` groups are still created, mirroring the GitHub teams.
They carry no permission set.

Sign-in name is the GitHub handle. Assignments are to groups, never to users.

## Alternatives considered

**Fifteen per-workstream permission sets** — what the backlog asks for. Rejected
on the reasoning above: fifteen policies authored in advance of the work they
gate, by people not doing the work, with a blocked engineer as the failure mode
and no on-call authority to unblock them. Revisitable: the workstream groups
exist, so attaching a scoped permission set to `u25c-ws-bedrock` later is a data
change, not a redesign.

**One `AdministratorAccess` tier for everyone** — simplest, and defensible given
the SCP and the $200 ceiling. Rejected because the programme exists to teach
platform engineering, and "everyone is an administrator" is the practice it
should be teaching people to avoid. The boundary is also the only thing stopping
sixteen people from creating roles that outlive their sessions.

**Skip the permissions boundary** — one fewer moving part, and a two-call path
from PowerUser to administrator: create a role with `AdministratorAccess`, assume
it. Rejected because it makes the engineer tier indistinguishable from the admin
tier for anyone who reads the IAM documentation.

## Consequences

- Adding someone to a workstream is a group membership change. It never requires
  touching an account assignment.
- **A boundary is an intersection, not a deny list.** `u25c-engineer-boundary`
  allows `*` and subtracts; a policy containing only `Deny` statements grants
  nothing and would give every engineer a session with zero permissions. Anyone
  editing it needs to know that before they "tidy up" the `Allow`.
- Cross-module dependency: the boundary is a customer-managed policy that must
  exist **in the workload account**, created by `infra-aws/iam`, referenced by
  name from `infra-aws/identity` which runs in management. `iam/` must be applied
  first or the assignment fails.
- The three-layer model means an `AccessDenied` has three possible sources. The
  error message names the SCP when that is the cause; a boundary denial does not
  say so, and will read as an inexplicable permission failure. This is the thing
  that will cost someone an afternoon.
- `user_name` is immutable in the identity store: changing it destroys the user
  along with their password and registered MFA device. Accounts that predate the
  handle convention keep their original sign-in name rather than being renamed.
- Terraform cannot set passwords and AWS exposes no API for issuing a one-time
  password, so onboarding has an irreducible manual step per person. See
  `runbooks/onboard-to-aws.md`.
