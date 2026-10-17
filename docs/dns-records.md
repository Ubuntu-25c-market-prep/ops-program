# DNS Records

**Owner:** `@utils` · **Consumers:** every workstream that needs a hostname
**Zone:** `25c-team1.art` (public, `Z033052035FXAKF23D1RR`)
**Controller:** external-dns, `gitops-flux/infrastructures/base/external-dns`

Hostname *naming* is [gateway-conventions.md §3](gateway-conventions.md). The
certificate behind it is [§4](gateway-conventions.md) of the same file. This page
is about how the DNS record itself comes to exist, and the three ways to break
the zone.

## How a record is actually created

Not per-app, and not by adding a manifest. Every platform hostname today comes
from **one annotation on one Service** — the Istio ingress gateway's — as a
comma-separated list:

```yaml
# gitops-flux/infrastructures/dev/25c-shared/istio-gateway/patch.yaml
        external-dns.alpha.kubernetes.io/hostname: rancher.25c-team1.art,storefront.25c-team1.art,grafana.25c-team1.art
```

external-dns watches `service` and `ingress` sources. The gateway is a
`type: LoadBalancer` Service, so each name in that list becomes a CNAME to the
NLB's hostname.

**Consequences worth knowing before you need a hostname:**

- Adding one is an edit to a file `@istio` owns, not a change in your own
  component's directory. Route it through them (`gateway-conventions.md` §2).
- It is one line. Appending carelessly — dropping a comma, or replacing rather
  than appending — removes every other hostname on the platform at once. `sync`
  policy means removal from the annotation deletes the record.
- The `Gateway`'s `hosts` list and this annotation are separate things. A name
  in one and not the other either resolves to a gateway that will not serve it,
  or is served by a gateway nothing resolves to.

## What external-dns will and will not touch

Configuration that matters, all in
`base/external-dns/helmrelease.yaml` and the dev overlay's `patch.yaml`:

| Setting | Value | Why it matters here |
|---|---|---|
| `policy` | `sync` | Deleting a hostname deletes its record. Not `upsert-only`. |
| `registry` | `txt` | Ownership is recorded in a companion TXT record |
| `txtPrefix` | `edns-` | Registry records are `edns-<name>`, not `<name>` |
| `txtOwnerId` | `u25c-shared` | This cluster's identity in those TXT records |
| `domainFilters` | `25c-team1.art` | Client-side; the IAM policy is the real boundary |
| `managedRecordTypes` | `A`, `AAAA`, `CNAME` | TXT is written by the registry regardless |

**external-dns only ever modifies or deletes records its own TXT registry
claims.** That is what lets it share the zone safely with cert-manager's
`_acme-challenge.*` records and with anything created by hand — it does not own
them, so `policy: sync` will not remove them.

The corollary is the part people get wrong: a record created by hand is *not*
protected, it is *invisible*. external-dns will happily try to create the same
name later, and Route 53 will reject a CNAME sitting alongside an existing
record type. The symptom is a hostname that silently never appears.

**Do not hand-create records in this zone.** If something needs a name that is
not a gateway hostname, raise it with `@utils` rather than clicking it into the
console.

## Three things that break the zone irreversibly

**1. Changing `txtPrefix`.** The prefix is how external-dns finds its own
registry entries. Change it and every existing registry record is orphaned: the
controller no longer recognises records it created, stops managing them, and
creates duplicates alongside. There is no migration path that does not involve
editing the zone by hand. **Never change it after records exist.**

**2. Reusing `txtOwnerId` on another cluster.** It identifies *one* external-dns
instance. Two instances sharing a zone and an owner id will each believe they
own the other's records and fight over them — one deleting what the other just
created, indefinitely. This is why `txtOwnerId` lives in the overlay and not in
`base/`: a second cluster syncing the library must be forced to choose its own.
It is also why external-dns not failing without one is dangerous — it falls back
to the owner id `default`, which is worse than an error.

**3. Running a second replica.** The chart hardcodes `replicas: 1` and exposes
no value for it. There is no leader election here, so two writers would race
each other over the same records and the same registry entries. Scaling this
controller is not a values change.

## Verifying

Records the controller believes it owns:

```bash
kubectl -n external-dns logs deploy/external-dns | grep -iE "CREATE|UPDATE|DELETE"
```

What Route 53 actually holds, including the registry entries:

```bash
aws route53 list-resource-record-sets --hosted-zone-id Z033052035FXAKF23D1RR \
  --query "ResourceRecordSets[].{Name:Name,Type:Type}" --output table
```

Every managed hostname should have a matching `edns-<name>` TXT beside it. A
hostname with no `edns-` companion is one external-dns does not own — either
hand-created, or created by an instance using a different `txtOwnerId`.

End to end, from outside the cluster:

```bash
dig +short rancher.25c-team1.art
dig +short TXT edns-rancher.25c-team1.art
```

## Related

- [gateway-conventions.md](gateway-conventions.md) §3 hostname naming, §4 TLS
- [secret-management.md](secret-management.md) — the IRSA role external-dns uses
  is documented alongside cert-manager's
- `gitops-flux/infrastructures/base/external-dns/helmrelease.yaml` — every value
  above, with the reasoning inline
