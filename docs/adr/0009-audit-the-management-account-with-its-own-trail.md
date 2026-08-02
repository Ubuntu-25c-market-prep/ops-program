# 0009. Audit the management account with its own trail, not an organisation trail

**Status:** Proposed
**Date:** 2026-08-02
**Deciders:** @cto, @security

## Context

`infra-aws/bootstrap` creates a multi-region CloudTrail trail in the workload
account `808540602855`, with log file validation, SSE-KMS encryption, and
delivery to both S3 and CloudWatch Logs. Dev is fully audited.

Nothing else is. Staging, Prod and the management account have only CloudTrail
Event history — a 90-day, in-console, non-exportable record that cannot be
queried at scale, cannot be alarmed on, and cannot be retained.

That gap is not evenly distributed. Staging and Prod are frozen by the
`u25c-org-dormant-freeze` SCP (ADR 0007) and nothing happens in them. The
management account is the opposite: it is where Organizations, SCPs, IAM Identity
Center, budgets and the cost-freeze action live. **The highest-privilege actions
in the entire organisation are the ones currently not durably logged** — adding a
person to `u25c-cto`, detaching a guardrail SCP, raising the budget ceiling.

The obvious fix is an organisation trail, which captures every member account
plus management into one bucket. It was attempted three times and failed three
times:

1. **A delegated administrator cannot convert an existing account-level trail
   into an organisation trail.** That is management-account only, per footnote 2
   of the CloudTrail delegated-administrator capability table. The trail must be
   replaced, not updated.
2. **Replacing it requires `cloudtrail:DeleteTrail`, which `u25c-org-guardrails`
   denies.** Each attempt therefore costs a break-glass SCP detach from the
   management account and a window with no trail at all.
3. **`CreateTrail` then fails with `InsufficientEncryptionPolicyException`** with
   every documented requirement satisfied: both trail-owner ARNs in the bucket
   policy and the KMS encryption context, `kms:Decrypt` for the S3 Bucket Key,
   and all four member accounts in the encryption context.

Two genuine defects were found and fixed on the way (infra-aws#26): an
organisation trail's ARN belongs to the **management** account even when a
delegated administrator creates it, so the `aws:SourceArn` presented to S3, KMS
and the CloudWatch Logs role is that account's; and the missing `kms:Decrypt` was
a latent gap unrelated to organisation trails.

The remaining hypothesis is that an organisation trail cannot use an SSE-KMS key
owned by a member account. AWS documents that the trail's S3 bucket "can belong
to any account" and says nothing equivalent about the key.

Two constraints shape what we do next. Every further attempt costs a guardrail
detach and an audit gap, so guessing is expensive. And an organisation trail's
whole marginal value here is *the management account* — Dev is already covered,
and the other two accounts are inert.

## Decision

**Create a second, independent account-level trail in the management account.
Do not pursue the organisation trail.**

It lives in `infra-aws/organization/`, which already runs with management-account
credentials, and writes to its own bucket and KMS key in `909783398044`. The Dev
trail is untouched — no replacement, no `DeleteTrail`, no guardrail detach, no
window without audit logging.

`organization_id` in `infra-aws/bootstrap` stays empty, and the three findings
above stay recorded at the resource.

This is a decision about *coverage*, not about organisation trails being wrong.
Revisit it when a second workload account exists.

## Alternatives considered

**Organisation trail with the key and bucket moved into management** — the
configuration AWS clearly supports, and what the failed attempts were reaching
for. Rejected for now because it is a larger change that fixes a problem we do
not have: it centralises audit for four accounts, three of which are Dev
(already covered) and two frozen shells. It also cannot be validated without
another detach-and-gap cycle, and if the KMS hypothesis is wrong we learn that
only after moving the bucket.

**Organisation trail with SSE-KMS dropped in favour of SSE-S3** — probably the
cheapest way to test the hypothesis, since removing KMS removes the suspected
cause. Rejected on merit: it trades a working encryption-and-access-control story
for an experiment. The KMS key policy is what governs *who can read the logs*,
which is not something to give up to make a deployment succeed.

**Accept the account-level Dev trail and log nothing else** — zero work, and the
status quo. Rejected because it leaves SCP detachments, Identity Center group
changes and budget-ceiling edits with no durable record. Those are precisely the
actions an audit trail exists for, and in a programme where one person holds
management-account admin, "trust the CTO" is not an access-control model.

**A dedicated Log Archive account** — what AWS Control Tower does, and the right
answer at real scale. Rejected on the same grounds as ADR 0003: another account
means another set of per-account charges for a programme running one cluster on a
$200/month ceiling.

## Consequences

- The management account gets durable, validated, encrypted audit logging. The
  actions that can disable every other guardrail become reviewable.
- **Cost is effectively zero.** The first copy of management events per account
  per region is free, and this is that account's first trail. Only S3 storage is
  charged, in pennies.
- **Two trails and two buckets instead of one.** Anyone investigating an incident
  spanning both accounts queries two places. With one workload account this is a
  nuisance; with five it would be the wrong design, which is the trigger to
  revisit.
- **A new member account is not automatically covered.** An organisation trail's
  best property is exactly what we are giving up. Adding a workload account means
  remembering to add a trail — write it into the account-vending checklist when
  one exists, because nobody will remember.
- **SCPs do not protect this trail.** They have no effect in the management
  account, so `ProtectAudit` cannot stop its deletion the way it does in Dev.
  Only the two members of `u25c-cto` have access there, which narrows the blast
  radius to two people but does not eliminate it. Accepted knowingly.
- The organisation-trail findings do not expire. If someone revisits this, the
  three blockers and the untested KMS hypothesis are in
  `infra-aws/bootstrap/main.tf` and infra-aws#2 — **read them before attempting a
  fourth time**, because each attempt costs a guardrail detach and an audit gap.
