# Runbook: sealed-secrets controller key — back up and restore

**Doing a routine backup, not handling an incident?** Skip to
[Prevention](#prevention--the-backup-procedure). That is the backup procedure.

Convention and rationale live in
[docs/secret-management.md](../docs/secret-management.md) §2–§5. This file is the
procedure that document points at.

## Symptom

One of:

- `SealedSecret` objects stop producing `Secret`s. `kubectl describe sealedsecret
  <name>` reports `no key could decrypt secret` and the target `Secret` is never
  created or refreshed.
- The `sealed-secrets` controller starts with a fresh, empty key set — visible as
  a newly generated key Secret with today's timestamp and none of the older ones.
- The cluster, or the `sealed-secrets` namespace, was rebuilt.

## Impact

**Every `SealedSecret` in `gitops-flux` becomes undecryptable ciphertext.**

The private half of the keypair exists in exactly one place — a `Secret` in the
`sealed-secrets` namespace, in etcd. It is not in Git, and it cannot be: the
repository is public, which is the entire reason sealed-secrets is in use.

`Secret`s the controller already wrote keep working, because they are ordinary
`Secret`s in etcd. So an outage does **not** announce itself. It surfaces the
next time something needs re-creating — a namespace rebuild, a restore, a new
cluster — and by then the cause is weeks old.

Committed ciphertext cannot be recovered by any other means. Without a backup,
recovery means re-sealing every secret from its original plaintext, which the
platform may no longer have.

## Immediate action

**Do not delete or restart the controller, and do not let Flux reinstall it.**
If any key material is still present it is the only copy, and a restart can
generate a new active key that masks what is left.

Freeze reconciliation of the release while you work:

```bash
flux suspend helmrelease sealed-secrets -n flux-system
```

Then check whether anything survives — this is also the first diagnostic step
below. If keys are present, **go straight to
[Prevention](#prevention--the-backup-procedure) and back them up before doing
anything else.** Diagnose afterwards.

## Diagnosis

**1. Is any key material present?**

```bash
kubectl -n sealed-secrets get secret \
  -l sealedsecrets.bitnami.com/sealed-secrets-key \
  -o custom-columns='NAME:.metadata.name,LABEL:.metadata.labels.sealedsecrets\.bitnami\.com/sealed-secrets-key,AGE:.metadata.creationTimestamp'
```

Expect one row per key. There is normally **more than one**: the controller
renews on a schedule and retains the old keys so previously sealed data still
decrypts. The newest carries the label value `active`; the rest are retained for
decryption only.

- **Rows returned, one of them `active`** — the controller has its keys. Your
  problem is something else: check the controller is running and that the
  `SealedSecret`'s name and namespace match what it was sealed for (`strict`
  scope is the default; see §2 of the convention).
- **Rows returned, none `active`** — the controller has not adopted a key.
  Restarting it (Resolution step 4) is usually enough.
- **No rows** — the key material is gone. Restore.

**2. Does a backup exist, and is it current?**

```bash
aws secretsmanager describe-secret \
  --secret-id u25c/shared/sealed-secrets/controller-keys \
  --query '{Created:CreatedDate,LastChanged:LastChangedDate,Versions:length(VersionIdsToStages)}'
```

`LastChangedDate` absent means the container exists but **was never filled** —
Terraform creates it empty on purpose, because the key must never enter a state
file. An empty container is not a backup.

**3. Which controller are you actually talking to?**

The deployment name is **not** `sealed-secrets`. `base/sealed-secrets/helmrelease.yaml`
sets no `releaseName`, so Flux composes the release as
`<targetNamespace>-<name>` — `sealed-secrets-sealed-secrets`. Derive it rather
than assuming:

```bash
kubectl -n sealed-secrets get deploy
```

This also breaks `kubeseal`, whose default `--controller-name` is
`sealed-secrets-controller`. Pass the real name explicitly:

```bash
kubeseal --controller-namespace sealed-secrets \
         --controller-name <name from above> \
         --fetch-cert
```

## Resolution — restore from the Secrets Manager backup

> **This is the one sanctioned exception to "everything through Git."** The
> private key cannot be committed to a public repository, so it is applied
> directly. Nothing else in this platform is restored this way.

**1. Confirm you are on the right cluster.** Restoring keys onto the wrong one
silently cross-wires two clusters' secrets.

```bash
kubectl config current-context
```

**2. Pull the backup to a file in a directory only you can read.**

```bash
umask 077
mkdir -p ~/.ss-restore && cd ~/.ss-restore

aws secretsmanager get-secret-value \
  --secret-id u25c/shared/sealed-secrets/controller-keys \
  --query SecretString --output text > keys.yaml
```

Sanity-check before applying — you should see one or more `kind: Secret` with
`type: kubernetes.io/tls`:

```bash
grep -cE '^\s*kind: Secret' keys.yaml
```

**3. Apply the keys.**

```bash
kubectl apply -f keys.yaml
```

If this fails with `metadata.resourceVersion: Invalid value`, the backup was
taken without stripping cluster-assigned fields. Strip them and retry — see the
note in the backup procedure, and fix the backup afterwards so the next person
does not hit this:

```bash
kubectl apply -f <(yq 'del(.items[].metadata.resourceVersion,
                          .items[].metadata.uid,
                          .items[].metadata.creationTimestamp,
                          .items[].metadata.managedFields)' keys.yaml)
```

**4. Restart the controller.** Keys are read at startup; applying them to a
running controller changes nothing.

```bash
kubectl -n sealed-secrets rollout restart deploy/<controller deployment name>
kubectl -n sealed-secrets rollout status deploy/<controller deployment name>
```

**5. Resume Flux and prove decryption works.**

```bash
flux resume helmrelease sealed-secrets -n flux-system
```

Pick a `SealedSecret` that already exists in Git, delete the `Secret` it
produces, and confirm the controller re-creates it:

```bash
kubectl -n <ns> delete secret <name>
kubectl -n <ns> get secret <name> -w
```

It reappearing is the proof. The controller logs say so too:

```bash
kubectl -n sealed-secrets logs deploy/<controller deployment name> | grep -i unseal
```

**6. Destroy the local copy.**

```bash
cd ~ && rm -rf ~/.ss-restore
```

## Prevention — the backup procedure

Run this **after any controller key renewal**, and on the schedule in
[§4](../docs/secret-management.md) of the convention. Read access to the
Secrets Manager entry is `@utils` and `@cto` only.

**0. Know how often you owe this.** The chart's default key renewal period is 30
days, and `base/sealed-secrets/helmrelease.yaml` does not override it — so today
a new key appears monthly and this procedure is a monthly obligation. §5 of the
convention states that as the policy. If `keyrenewperiod: "0"` is ever pinned,
renewal stops, this becomes a one-time task, and §5 must change in the same PR.
That decision is open; until it is made, assume monthly.

**1. Export every key, not just the active one.** Old keys are what decrypt
previously sealed data. Backing up only the active key silently loses
everything sealed before the last renewal.

```bash
umask 077
mkdir -p ~/.ss-backup && cd ~/.ss-backup

kubectl -n sealed-secrets get secret \
  -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml \
  | yq 'del(.items[].metadata.resourceVersion,
            .items[].metadata.uid,
            .items[].metadata.creationTimestamp,
            .items[].metadata.managedFields,
            .metadata)' > keys.yaml
```

Stripping those fields is not cosmetic: `kubectl apply` rejects a manifest
carrying another cluster's `resourceVersion`, which turns a restore into a
debugging session at the worst possible moment.

**2. Check what you captured.**

```bash
grep -cE '^\s*kind: Secret' keys.yaml     # must match the row count from Diagnosis step 1
grep -c 'tls.key' keys.yaml               # must equal the above - a key without its private half is useless
wc -c keys.yaml                           # must stay under 65536
```

Secrets Manager caps `SecretString` at 64 KiB. Each retained key is roughly
3–4 KB, so this is comfortable now and will not be forever — if it approaches
the cap, prune genuinely dead keys rather than truncating the backup.

**3. Write it to Secrets Manager.**

```bash
aws secretsmanager put-secret-value \
  --secret-id u25c/shared/sealed-secrets/controller-keys \
  --secret-string file://keys.yaml
```

The container is created by `infra-aws/sealed-secrets` and encrypted with
`alias/u25c-shared-platform`. Terraform deliberately never holds the key
material, so this step is manual by design and cannot be automated into the
apply.

**4. Verify the write round-trips.**

```bash
aws secretsmanager get-secret-value \
  --secret-id u25c/shared/sealed-secrets/controller-keys \
  --query SecretString --output text | grep -cE '^\s*kind: Secret'
```

Must match step 2.

**5. Destroy the local copy.**

```bash
cd ~ && rm -rf ~/.ss-backup
```

**6. Test the restore. At least once, and this is not optional.**

§4 of the convention states it plainly: *an untested backup is a hypothesis.*
Restore into something disposable and confirm a `SealedSecret` decrypts there —
a scratch cluster is the honest test, a scratch namespace on this cluster is the
cheap one. Whichever is used, record which it was on the issue, because the two
prove different things: a namespace proves the key material is intact, a
separate cluster proves the whole procedure works when the cluster is gone.

Do not run the test against `sealed-secrets` on this cluster. Applying keys to
the live controller is a restore, not a test of one.
