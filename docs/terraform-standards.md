# Terraform Standards

Binding for every `.tf` file in the organisation. Deviations need an ADR.

State segmentation is a separate document: [terraform-state-strategy.md](terraform-state-strategy.md).

---

## 1. File layout

Every root module and every reusable module has the same shape. Predictability
beats cleverness — a reviewer should know where to look before opening the
directory.

```
<component>/
├── main.tf                    # resources, grouped by comment banner
├── variables.tf               # inputs, every one with description + type
├── outputs.tf                 # outputs, every one with description
├── versions.tf                # required_version, providers, backend
├── terraform.tfvars.example   # committed, filled with placeholders
└── README.md                  # what this owns, how to run it
```

Split `main.tf` only when it exceeds roughly 400 lines, and split by domain
(`network.tf`, `iam.tf`, `logging.tf`), never by resource type (`s3.tf` holding
six unrelated buckets tells a reader nothing).

---

## 2. Versions and pinning

```hcl
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}
```

- `required_version` is a floor, not a pin. We track Terraform minors.
- Providers use `~>` — patch and minor float, major does not.
- **`.terraform.lock.hcl` is committed** in every root module. It pins provider
  hashes; without it "the same code" produces different plans on different
  machines.
- Module sources are **relative paths** into `infra-aws/modules/` (ADR 0010):

```hcl
module "vpc" {
  source = "../modules/vpc"
}
```

Modules used to live in their own repository and pin a tag, on the reasoning that
a `ref` pointing at `main` means your infrastructure changes when someone else
merges. With one consumer that protection was never exercised, and the cost was
that a module and its caller could not change in the same commit.

The protection is now CI rather than a tag: `modules/**` is in the workflow
`paths:` filters, so a module change plans every layer that calls it *before*
merge instead of surprising the next person to bump a `ref`. Read the plan. A
change that replaces a resource is still breaking even when the interface is
identical.

An external module — one this programme does not own — still pins a version.

---

## 3. Providers

Every root module pins the account it is allowed to touch:

```hcl
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]

  default_tags {
    tags = {
      Org        = var.org_prefix
      Env        = "shared"
      Workstream = "infra"
      ManagedBy  = "terraform"
      Repo       = "infra-aws"
    }
  }
}
```

`allowed_account_ids` turns a wrong-credentials apply from a half-finished
disaster into an immediate error. It is not optional.

`default_tags` is how the tagging standard is enforced in practice — set it once
per root module rather than tagging each resource by hand.

---

## 4. Naming inside Terraform

| Thing | Rule | Example |
|---|---|---|
| Resource name | Singular, snake_case, describes the role not the type | `aws_s3_bucket.tfstate` not `aws_s3_bucket.tfstate_bucket` |
| Single-instance module resource | `this` | `aws_vpc.this` |
| Variable | snake_case, no type in name | `retention_days` not `retention_days_number` |
| Output | snake_case, names the value | `state_bucket`, `apply_role_arn` |
| Local | snake_case, for values used 2+ times | `local.name` |
| Data source | Matches the resource naming rule | `data.aws_partition.current` |

Never repeat the provider in a resource name — `aws_s3_bucket.aws_logs` reads as
`aws_s3_bucket.aws_logs`, which says "aws" twice and "logs" once.

---

## 5. Variables

Every variable has a `description` and a `type`. No exceptions — a variable
without a description is an undocumented API.

Validate anything with a knowable shape:

```hcl
variable "account_id" {
  description = "AWS account this configuration is allowed to run against."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account id."
  }
}
```

Defaults are for values that are genuinely safe everywhere. A default that is
wrong in production is worse than a required input, because it fails silently.

Never default a variable to a real account id, a real CIDR, or a real email.

---

## 6. Conditionals and iteration

- `for_each` over a map is the default. Keys are stable, so adding an element
  does not re-create its neighbours.
- `count` only for genuine on/off:

```hcl
resource "aws_ce_anomaly_monitor" "services" {
  count = var.anomaly_monitor_arn == "" ? 1 : 0
  ...
}
```

- Never `count = length(var.some_list)` over a list whose order can change.
  Removing the first element re-creates every resource after it.

---

## 7. Safety

```hcl
resource "aws_s3_bucket" "tfstate" {
  bucket = local.bucket

  lifecycle {
    prevent_destroy = true
  }
}
```

`prevent_destroy` goes on anything whose loss is not recoverable by re-applying:
state buckets, KMS keys, data stores, backup targets.

`ignore_changes` is for values a controller legitimately owns outside Terraform —
a thumbprint AWS rotates, a replica count an autoscaler manages. It is not a way
to silence a diff you do not understand.

---

## 8. Secrets

- **State contains secrets.** Any attribute of any resource is in there in plain
  text. This is why state is KMS-encrypted, versioned, TLS-only and access is
  per-prefix.
- Never put a secret in a `.tfvars`, a default, or a `locals`.
- Secrets come from Secrets Manager or SSM SecureString, read at apply time.
- Non-rotating config belongs in **SSM Parameter Store standard tier** — it is
  free, where Secrets Manager is $0.40 per secret per month.
- `terraform output` of a sensitive value must be marked `sensitive = true`.

---

## 9. Comments

Comment the **why**, never the what. `# create an S3 bucket` above
`resource "aws_s3_bucket"` is noise.

```hcl
# AWS provisions a Default-Services-Monitor automatically, and the limit is one
# DIMENSIONAL monitor per account. Reuse the existing one when its ARN is given
# rather than failing on a limit that cannot be raised.
```

A comment that explains a constraint, a workaround, or a non-obvious ordering is
worth more than the code it sits above. A comment that restates the resource type
is a maintenance liability.

Banner comments group sections of `main.tf`:

```hcl
###############################################################################
# Terraform state backend
###############################################################################
```

---

## 10. Before you open a pull request

```bash
terraform fmt -recursive        # non-negotiable, CI checks it
terraform init -backend=false
terraform validate
terraform plan                  # read it, all of it
```

CI additionally runs gitleaks, a forbidden-files check, and Trivy IaC scanning.
A Trivy HIGH or CRITICAL is fixed, not suppressed. If a finding genuinely does
not apply, suppress it inline **with the reason**:

```hcl
# The access-log bucket cannot log its own access without generating an infinite
# feedback loop of log entries, which AWS explicitly warns against.
#trivy:ignore:AWS-0089
```

An unexplained ignore is treated as an unfixed finding in review.

---

## 11. Reviewing Terraform

The reviewer's job is not to check formatting — CI does that. It is to answer:

1. **Does the plan match the description?** A pull request titled "add a subnet"
   whose plan destroys a NAT gateway fails review regardless of code quality.
2. **What is the blast radius if this is wrong at 3am?**
3. **Is anything here another layer's job?** See the state strategy.
4. **Does it hardcode something that belongs in a variable** — an account id, a
   CIDR, a region, an ARN?
5. **What does this cost?** Anything adding ongoing spend states the monthly
   delta in the pull request. Nodes, NAT, endpoints, load balancers, storage and
   retention all count.

---

## 12. IRSA trust policies

Every role a pod assumes is scoped to exactly one service account in exactly one
namespace. No exceptions, no wildcards.

```hcl
data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:${var.namespace}:${var.service_account}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}
```

Both conditions are required.

**`:sub`** names the service account. Omit it and the trust policy says only
"any identity from this OIDC provider" — which is every pod in the cluster,
including a pod in a namespace someone else owns. There is one cluster and one
OIDC provider here (ADR 0002, ADR 0003), so a missing `:sub` is not a
theoretical weakness. It is a role assumable from anywhere in the cluster.

**`:aud`** pins the token audience to `sts.amazonaws.com`, so a projected
service-account token minted for some other audience cannot be replayed against
STS.

**`StringEquals`, never `StringLike`.** A wildcard anywhere in a `:sub` value
reopens exactly the hole the condition closes.
`system:serviceaccount:prod-*:*` trusts every service account in every namespace
beginning `prod-`. If a role genuinely needs to serve more than one service
account, list them — `values` is a list.

This does not apply to the GitHub Actions OIDC roles in `iam/`. Those federate a
different provider with a different subject format, and the plan role uses
`StringLike` deliberately so a new repository does not require a Terraform
change. The apply role does not, and the reasoning is recorded there.

### Naming

Put the namespace in the role name where it is not already obvious:
`u25c-dev-karpenter-controller` for the `karpenter` namespace reads correctly.
`u25c-dev-ebs-csi` for a service account in `kube-system` does not, and the
Kyverno guardrail in `platform-security` (`restrict-irsa-cross-namespace`) flags
it as non-compliant even though the trust policy is correct. That policy is in
Audit mode; the mismatch needs resolving before it moves to Enforce.

### Reviewing

For any new role a pod will assume, check three things in the trust policy
before approving:

1. A `:sub` condition exists, and it names a specific namespace and service
   account.
2. An `:aud` condition exists and equals `sts.amazonaws.com`.
3. Both use `StringEquals`.

The failure mode is silent. A role missing `:sub` works exactly as intended for
the workload it was written for, and goes on working while being assumable by
anything else in the cluster. Nothing surfaces at plan time, at apply time, or
in the application logs. It is only visible by reading the trust policy, which is
why it is on this list rather than left to a linter.

### Audit, 18 August 2026

Every IRSA trust policy in `infra-aws` at the time of writing:

| Role | Namespace | `:sub` | `:aud` | Test |
|---|---|---|---|---|
| `modules/karpenter` controller | `karpenter` | yes | yes | `StringEquals` |
| `modules/cert-manager` controller | `cert-manager` | yes | yes | `StringEquals` |
| `modules/eks` EBS CSI | `kube-system` | yes | yes | `StringEquals` |
| `thanos` | monitoring | yes | yes | `StringEquals` |

All four pass. Two of them — cert-manager and thanos — were written days apart by
different people with none of the above written down, and both got it right by
copying the module next door. That is the convention propagating by example, and
it works until someone writes a role in a layer with no neighbour to copy.
