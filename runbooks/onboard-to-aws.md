# Runbook: onboard a person to AWS

Not an incident. This is the procedure for giving someone their AWS sign-in, and
for the person receiving it.

## Symptom

A new person is on the roster, or an existing one cannot sign in to AWS. They
have a GitHub account and no AWS credentials.

## Impact

They can read the board and push to GitHub, and cannot see the account any of it
describes. Blocking for anyone on a Wave 1+ task in `infra-aws`.

## Immediate action — for the person being onboarded

You will be sent two things: your **username** and a **one-time password**. You
will not receive an email from AWS; the password comes to you directly, over
GitHub or Slack.

1. Open **https://ubuntu-25c.awsapps.com/start**
2. Username: **your GitHub handle**, exactly as it appears in `program/roster.yaml`.
   Case matters. If yours is `Nikita-DS22`, type `Nikita-DS22`.
3. Password: the one-time password you were sent. You will be asked to set your
   own immediately. Do that before doing anything else.
4. Register an MFA device when prompted. An authenticator app on your phone is
   fine. **Do not skip this** — you will not be able to sign in again without it,
   and re-registering means going back to step 1 with a new one-time password.
5. You now see one or more roles. Click one to open the console, or use
   **Access keys** on the same row for CLI credentials.

Which roles you see depends on your groups. Most people see two:

| Role | What it is for |
|---|---|
| `u25c-PlatformEngineer` on Dev | Your working role. Everything except IAM escalation. |
| `u25c-ReadOnly` on Dev and management | Looking at something you are not on the hook for. Also where you can see the budget. |

If you are on the `finops` workstream you also see `u25c-Billing` on the
management account. If you are CTO you see `u25c-PlatformAdmin`.

### CLI setup

```bash
aws configure sso
# SSO start URL:  https://ubuntu-25c.awsapps.com/start
# SSO region:     us-east-1
# registration scopes: sso:account:access
```

Pick the account and role when prompted, and name the profile `u25c`. Then:

```bash
aws sso login --profile u25c
aws --profile u25c sts get-caller-identity
```

## Diagnosis — when sign-in or a command fails

**"Your authentication information is incorrect"** — the username is the GitHub
handle, not an email address, and it is case-sensitive. One person's sign-in name
differs from their handle for historical reasons; check the `sign_in_names`
output of `infra-aws/identity` before assuming anything.

**Signed in, but no roles listed** — you are in the directory and not in an
access group. Someone with `u25c-PlatformAdmin` runs:

```bash
aws identitystore list-group-memberships-for-member \
  --identity-store-id d-90660f563d \
  --member-id UserId=<your user id>
```

Empty or `u25c-all` only means your roster entry has no workstreams. That is the
model working as intended — ask the PM to assign one.

**`AccessDenied` inside a role.** Three different ceilings can produce this, and
only one of them says so in the message:

1. **The SCP.** The error names it: `with an explicit deny in a service control
   policy: ...p-eamyld9j`. You are trying to do something the account forbids for
   everyone — most often working in a region other than `us-east-1`, launching an
   instance type outside the allow-list, or creating an IAM user or access key.
   Read [ADR 0007](../docs/adr/0007-ou-layout-and-scp-guardrails.md). The fix is a
   pull request against `infra-aws/organization`, not a wider role.
2. **The permissions boundary.** Does **not** announce itself. If you are creating
   a role and the denial mentions no policy at all, you are probably missing
   `--permissions-boundary arn:aws:iam::808540602855:policy/u25c-engineer-boundary`.
   Every role you create must carry it.
3. **The permission set.** Everything else. `u25c-PlatformEngineer` is PowerUser
   plus scoped IAM; it genuinely cannot do a few things, and widening it is a
   pull request against `infra-aws/identity`.

## Resolution — for the CTO, issuing the credential

Terraform creates the user, the group memberships and the account assignments.
It cannot create the password: **AWS exposes no API for issuing a one-time
password.** This step is manual, per person, in the console.

1. IAM Identity Center → **Users** → select the person.
2. **Reset password** → **Generate a one-time password and share the password
   with the user**.
3. Copy the password. Send it to them with their username, over GitHub or Slack.
   It is single-use and forces a reset on first sign-in, so this is an acceptable
   channel; a reusable password would not be.

To add someone new, or move them between workstreams, edit
`infra-aws/identity/people.tf` — keeping it consistent with
`program/roster.yaml`, which is the source of truth — then:

```bash
cd infra-aws/identity && terraform plan   # management-account credentials
```

Confirm the plan adds only memberships before applying. A plan that proposes to
*replace* an `aws_identitystore_user` is a bug: `user_name` is immutable, and a
replacement destroys that person's password and registered MFA device. Use
`sign_in_name_overrides` instead.

## Prevention

- **One-time passwords only.** Never send a password that survives first use.
- **MFA at first sign-in.** Enforced in Identity Center → Settings →
  Authentication. Verify it is still set to require registration; it is a console
  setting with no Terraform resource and nothing detects it being turned off.
- **Never assign a permission set to a user.** Assignments go to groups. A direct
  user assignment is invisible when you audit group membership, and outlives the
  person's involvement. One such assignment predates this configuration and
  should be removed by hand once every CTO has signed in through
  `u25c-PlatformAdmin`.
- **Keep `people.tf` and `roster.yaml` in step.** Nothing enforces this. It is
  checked during onboarding review, which is the only time anyone looks.
