# Secret Management

Where secret material lives, who can read it, and how it rotates.

> **The one-sentence version:** prefer no secret at all — IRSA over credentials —
> and where a secret is unavoidable, encrypt it into Git with sealed-secrets and
> keep the one key that decrypts everything in AWS Secrets Manager.

---

## 1. The hierarchy

Reach for the first option that works. Every step down adds something that can be
lost, leaked, or forgotten.

| Preference | Mechanism | Use for |
|---|---|---|
| **1. No secret** | IRSA — an IAM role assumed via the cluster's OIDC provider | Anything a workload needs from AWS |
| **2. Encrypted in Git** | `SealedSecret`, decryptable only by the in-cluster controller | Kubernetes `Secret`s: passwords, tokens, TLS keys |
| **3. Held by AWS** | Secrets Manager | Material that must survive the cluster, or that AWS itself consumes |
| **4. Not committed** | `.tfvars`, `.env`, gitignored | Terraform inputs carrying account ids |

**IRSA is not a convenience, it is the default.** A static AWS credential in a
cluster is a credential that must be stored, rotated, audited and revoked. A role
assumed through the OIDC provider has none of those problems: the token is minted
per pod, expires in an hour, and is scoped by a trust condition to one
`namespace:serviceaccount`. cert-manager, Karpenter, external-dns and Velero all
take this path. If a component supports IRSA and someone proposes an access key,
that needs an ADR, not a pull request.

---

## 2. Sealed secrets

`gitops-flux` is public. A Kubernetes `Secret` is base64, which is encoding, not
encryption — committing one publishes it. sealed-secrets solves this by
encrypting with a public key anyone may hold, where only the in-cluster
controller holds the private half.

### Sealing scope

`kubeseal` binds the ciphertext to a name and namespace by default. Do not widen
this without a reason recorded in the pull request.

| Scope | Behaviour | When |
|---|---|---|
| `strict` *(default)* | Decrypts only as this name, in this namespace | Always, unless proven otherwise |
| `namespace-wide` | Any name, one namespace | A generated name |
| `cluster-wide` | Any name, any namespace | Effectively never — a leaked file is reusable anywhere |

### Naming

The `SealedSecret` takes the name of the `Secret` it produces. No `-sealed`
suffix: the file already says `kind: SealedSecret`, and the suffix would leak
into the `Secret` name and every reference to it.

---

## 3. The controller key

The controller generates an RSA keypair on first start and stores it as a
`Secret` in its own namespace, labelled
`sealedsecrets.bitnami.com/sealed-secrets-key`.

**This key is the single highest-consequence object on the platform.** It is the
only thing that can decrypt every `SealedSecret` in Git. If the namespace is
deleted, the cluster is rebuilt, or EKS is replaced without it, every sealed
secret in every repository becomes permanently undecryptable. There is no
recovery path and no warning — the ciphertext stays in Git looking perfectly
healthy.

### Renewal, and why "the key" is really "the keys"

The controller mints a **new** keypair every 30 days. It does not discard the old
ones: new secrets are sealed with the newest key, and existing `SealedSecret`s
still decrypt because every prior key is retained.

Two consequences that catch people out:

- A backup must capture **every** key carrying the label, not just the one
  marked `active`. Backing up the active key alone leaves older `SealedSecret`s
  undecryptable.
- A backup goes stale within 30 days. Re-run it after each renewal.

Renewal is not rotation of the secrets themselves. Re-encrypting existing
`SealedSecret`s to the newest key is a separate, deliberate act
(`kubeseal --re-encrypt`), and is not required for correctness.

---

## 4. Backup

**Destination: AWS Secrets Manager**, in the workload account, encrypted with the
platform KMS key.

Chosen over the alternatives because access is IAM-controlled and auditable
through CloudTrail, it is encrypted at rest without us managing that, restore is
a single command, and it costs roughly $0.40/month. An S3 object would work but
puts versioning and access policy back on us. An external vault survives total
loss of the AWS account, which is a real advantage — revisit it if the programme
ever holds anything that would end the business.

| Property | Value |
|---|---|
| Secret name | `u25c/shared/sealed-secrets/controller-keys` |
| Contents | All `Secret`s labelled `sealedsecrets.bitnami.com/sealed-secrets-key`, as YAML |
| Encryption | Platform KMS key |
| Read access | `@utils` and `@cto` only |
| Refresh | Monthly, and after any controller key renewal |

The procedure itself — the exact commands to back up and to restore — is
`ops-program#19`, in `runbooks/`. A convention that says "back it up" without a
tested restore is not a backup.

**The restore path must be tested at least once.** An untested backup is a
hypothesis.

---

## 5. Rotation

| Material | Rotates | Trigger |
|---|---|---|
| sealed-secrets controller keys | Every 30 days | Automatic; back up afterwards |
| Application secrets in `SealedSecret`s | Per the issuing system's policy | Re-seal and merge |
| IRSA role sessions | Hourly | Automatic; nothing to do |
| Personal AWS access | Per Identity Center session policy | Automatic |
| GitHub PATs used against org repos | 90 days maximum | Calendar reminder |

Rotating a sealed secret is an ordinary pull request: re-seal the new value, merge,
Flux applies it. No out-of-band step, which is the point of the whole arrangement.

---

## 6. Never commit

Enforced by `.gitignore` and the security workflow, but **you are the control** —
both repositories are public and a force-push does not un-publish anything.

- Kubernetes `Secret` manifests with real `data:` — seal them
- `*.tfvars`, `*.tfvars.json`, `.env`
- Terraform state, `kubeconfig`, `*.pem`, `*.key`
- Bare AWS account ids and role ARNs. For IRSA annotations the established
  workaround is an out-of-band `ConfigMap` in `flux-system`, consumed with
  `valuesFrom` — see `base/karpenter/helmrelease.yaml`.

Terraform backend blocks are the one exception: they cannot take variables, so
the state bucket and KMS ARN are committed. That is a known trade-off, not a
licence to commit account ids elsewhere.

---

## 7. If a secret is committed

Assume it is compromised the moment it is pushed. Public repositories are
scraped continuously.

1. **Rotate the credential first.** Do not start with git history — while you
   rewrite it, the live credential is still valid.
2. Revoke the old value at its source.
3. Remove it from history, force-push, and tell everyone with a clone to re-clone.
4. Open an incident note in `runbooks/` if it was live in production.

Rotate first, clean second. Reversing the order is the common mistake.
