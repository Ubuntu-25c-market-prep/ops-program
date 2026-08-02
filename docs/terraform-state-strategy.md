# Terraform State Strategy

How state is segmented, why, and the rules for changing it.

> **The one-sentence version:** one state file per layer, layers ordered by how
> often they change and how much they would hurt if destroyed, dependencies
> flowing strictly downward, and never two teams sharing a state file.

---

## 1. Why not one state file

A single state for the whole platform looks simpler on day one and becomes the
main source of incidents by month three.

| Problem | What it looks like with 16 people |
|---|---|
| **Blast radius** | A malformed change to a Helm values file can produce a plan that destroys the VPC. There is no structural reason it cannot. |
| **Lock contention** | State locks are per-state. One `terraform apply` blocks all 15 other engineers, including people touching unrelated resources. |
| **Plan time** | Refresh walks every resource. A 900-resource state takes minutes per plan, on every pull request, forever. |
| **Coupled release cadence** | Add-ons change daily; the VPC changes twice a year. Sharing state forces the slow thing to be re-planned at the speed of the fast thing. |
| **Permission granularity** | State access is bucket-prefix granular. One state means everyone who can apply anything can apply everything. |
| **Recovery** | Corrupting one state file loses one layer. Corrupting *the* state file loses the platform. |

Splitting state is not an optimisation. It is what makes least privilege,
independent release cadence, and survivable mistakes possible at all.

---

## 2. The layer model

Layers are ordered by **change frequency** and **blast radius**, which correlate:
the things that hurt most to lose are the things that change least.

| # | Layer | Directory | State key | Changes | Owner |
|---|---|---|---|---|---|
| 0 | Bootstrap | `infra-aws/bootstrap` | `shared/bootstrap/terraform.tfstate` | Almost never | `@cto` |
| 1 | Governance | `infra-aws/budgets` | `management/budgets/terraform.tfstate` | Rarely | `@cto` |
| 2 | Identity | `infra-aws/iam` | `shared/iam/terraform.tfstate` | Rarely | `@security` |
| 3 | Network | `infra-aws/network` | `shared/network/terraform.tfstate` | Rarely | `@infra` |
| 4 | Registry | `infra-aws/ecr` | `shared/ecr/terraform.tfstate` | Occasionally | `@infra` |
| 5 | Cluster | `infra-aws/eks` | `shared/eks/terraform.tfstate` | Occasionally | `@infra` |
| 6 | AI services | `infra-aws/bedrock` | `shared/bedrock/terraform.tfstate` | Rarely | `@bedrock` |

Layer 1 is the only one that runs in the **management account**
(`909783398044`). Organizations, SCPs and budget actions exist nowhere else.
Every other layer runs in the **workload account** (`808540602855`).

### Where Terraform stops

Layers 7 and above are **not Terraform**. Cluster add-ons and applications are
delivered by GitOps — Flux for platform, Argo CD for business apps.

```
Terraform  →  provisions the cluster and everything under it
GitOps     →  provisions everything running inside the cluster
```

The boundary is deliberate. Add-ons change many times a week; Terraform is a poor
fit for that cadence, and a `terraform apply` that reconciles Kubernetes objects
competes with the GitOps controller that is also reconciling them. Pick one owner
per resource. If a resource lives in the cluster, GitOps owns it.

The one permitted exception is IAM roles for service accounts: the role is AWS,
so Terraform owns it, and the ServiceAccount annotation referencing it is
GitOps. Both sides are documented in the layer that owns them.

---

## 3. State key convention

```
<scope>/<component>/terraform.tfstate
```

- `scope` — `shared` for the workload account, `management` for the management
  account. When per-environment accounts return, this becomes `dev`, `stage`,
  `prod`.
- `component` — matches the directory name exactly. No abbreviations.

Bucket: `u25c-tfstate-808540602855`, versioned, KMS-encrypted, TLS-only, with
`prevent_destroy` on the bucket itself.

Locking is **native S3** (`use_lockfile = true`, Terraform ≥ 1.10). There is no
DynamoDB lock table; do not add one.

Every backend block looks like this and differs only in `key`:

```hcl
terraform {
  backend "s3" {
    bucket       = "u25c-tfstate-808540602855"
    key          = "shared/<component>/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    kms_key_id   = "arn:aws:kms:us-east-1:808540602855:key/cee2883d-7322-41b3-bd0c-f71e1effe89f"
    use_lockfile = true
  }
}
```

---

## 4. How layers talk to each other

Dependencies flow **downward only**. Layer 5 may read from layer 3. Layer 3 may
never read from layer 5. If you find yourself wanting to, the layering is wrong —
raise an ADR rather than working around it.

There are two ways to pass values between layers. We use both, for different
things.

### Preferred: published parameters

The producing layer writes its outputs to SSM Parameter Store under a namespaced
path. Consumers read them with a data source.

```hcl
# Producer — infra-aws/network
resource "aws_ssm_parameter" "vpc_id" {
  name  = "/u25c/shared/network/vpc_id"
  type  = "String"
  value = module.vpc.vpc_id
}

# Consumer — infra-aws/eks
data "aws_ssm_parameter" "vpc_id" {
  name = "/u25c/shared/network/vpc_id"
}
```

Why this is the default:

- The consumer needs **no access to the producer's state file**. State contains
  every attribute of every resource, including values that are effectively
  secrets. `terraform_remote_state` grants all of it to read one string.
- The published set is an **explicit contract**. Refactoring internals of the
  network layer does not break the cluster layer as long as the parameters keep
  their meaning.
- Parameters are readable by things that are not Terraform — scripts, CI,
  Backstage, a human debugging at 2am.

### Permitted: remote state data source

```hcl
data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "u25c-tfstate-808540602855"
    key    = "shared/network/terraform.tfstate"
    region = "us-east-1"
  }
}
```

Acceptable when the coupling is intentional and both layers share an owner.
Requires the consumer's role to have read access to that specific state prefix —
never blanket bucket read.

### Not permitted

- Reading another layer's state to *write* to it.
- Two layers managing the same resource.
- Hardcoding an ID that another layer produces. If it comes from another layer,
  read it; do not paste it.

---

## 5. Rules

1. **One state per layer.** Never two teams in one state file.
2. **A layer that changes daily does not share state with one that changes
   yearly.** Change frequency is the primary split axis.
3. **Dependencies flow downward.** No cycles, no upward reads.
4. **`prevent_destroy` on anything stateful** — state buckets, KMS keys, data
   stores. Losing them is not recoverable by re-applying.
5. **No manual state manipulation without a second pair of eyes.**
   `terraform state rm`, `mv` and `import` are reviewed like code: say what you
   are doing and why in the pull request before you run it.
6. **Never commit a state file, a backup, or a `.tfvars`.** CI blocks all three;
   the block is a backstop, not the control.
7. **Re-running plan must be free of side effects.** If a plan mutates anything,
   that is a bug in the configuration.
8. **Empty diff means empty diff.** A layer that never reaches a clean plan is
   broken and gets fixed before new work lands on top of it.

---

## 6. Adding a layer

1. Open an ADR describing what it owns and why it is not part of an existing
   layer.
2. Create the directory. Its name is the component name and the state key.
3. Add a `CODEOWNERS` path entry so review routes to the owning workstream.
4. Add the backend block; only `key` differs from every other layer.
5. Publish outputs other layers will need as SSM parameters under
   `/u25c/<scope>/<component>/`.
6. Add it to the table in section 2 in the same pull request.

A layer that is not in the table does not exist.

---

## 7. Recovery

State is versioned, so recovery is possible but never routine.

```bash
# List versions of a state object
aws s3api list-object-versions \
  --bucket u25c-tfstate-808540602855 \
  --prefix shared/eks/terraform.tfstate

# Restore a specific version
aws s3api get-object \
  --bucket u25c-tfstate-808540602855 \
  --key shared/eks/terraform.tfstate \
  --version-id <VERSION_ID> restored.tfstate
```

Then `terraform state push restored.tfstate` — **only** after confirming with
the layer's owner, and only with the reason recorded in the incident issue.

Non-current versions expire after 90 days. That is the real recovery window.
