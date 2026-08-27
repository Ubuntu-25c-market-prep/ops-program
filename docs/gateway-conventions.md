# Gateway API and VirtualService Conventions

Binding for every application team routing traffic through the mesh. Owned by `@istio`.
Deviations need an ADR.

The mesh itself — `istiod`, gateways, Kiali — is `@istio`'s to install and upgrade
(`gitops-flux`, epic `[istio] Service mesh and Kiali`). This document is the boundary: what
an app team writes to get traffic to their service, and what stays out of their hands.

---

## 1. Two APIs, one rule for choosing

Both `Gateway API` (`Gateway`, `HTTPRoute`) and Istio's classic API (`Gateway`,
`VirtualService`) work once the mesh is installed. Pick by what the route needs:

| Use | When |
|---|---|
| Gateway API (`HTTPRoute`) | Default. Portable, vendor-neutral, where the ecosystem is moving. |
| `VirtualService` | Only for Istio-specific traffic management `HTTPRoute` cannot express yet — fault injection, mirroring, and outlier-detection-driven retries. |

**Checked 2026-08-26: Gateway API's CRDs are not installed on `u25c-shared`** -
`kubectl get gateway.gateway.networking.k8s.io` returns "the server doesn't
have a resource type", not an empty list. Every route on this cluster today is
a `VirtualService`, not because it needed Istio-specific features, but because
that's what actually exists. Use `VirtualService` until `@istio` installs the
Gateway API CRDs - raise it with them if `HTTPRoute` is what you need.

Do not use both for the same route. A service's traffic policy has exactly one controlling
object, same as the single-controller-per-resource rule GitOps already runs on — two objects
routing the same host is two controllers fighting, not redundancy.

---

## 2. Ownership boundary

| Object | Namespace it lives in | Who writes it |
|---|---|---|
| `Gateway` (the listener — ports, TLS, hostnames) | `platform-istio` | `@istio` only |
| `HTTPRoute` / `VirtualService` (where traffic goes) | `app-<name>` | the owning app team |
| `AuthorizationPolicy`, `PeerAuthentication` | `app-<name>`, scoped to that namespace | the owning app team, defaults set by `@zerotrust` |

An app team requests a listener (a hostname, a port, a TLS cert) from `@istio` by opening an
issue against `gitops-flux` — they do not create `Gateway` objects themselves. They *do* own
every `HTTPRoute`/`VirtualService` that attaches to it via `parentRefs` /
`gateways:`, for their own namespace.

This mirrors the Argo/Flux boundary already in place: `gitops-argocd`'s `business`
`AppProject` restricts destinations to `app-*` namespaces specifically so a product pull
request cannot reach `platform-istio` and take down the mesh. A team's `HTTPRoute` that tries
to attach to a `Gateway` outside its own namespace is the same failure mode in miniature —
Kyverno enforces the boundary at admission, this document is what the boundary *is*.

---

## 3. Naming

| Thing | Rule | Example |
|---|---|---|
| `HTTPRoute` / `VirtualService` | `<app-name>` — matches the Deployment/Service it routes to | `storefront` |
| `Gateway` | One shared listener, not per-env (§5) — `@istio` owns the name | `ingressgateway` |
| Hostname | `<app-name>.25c-team1.art` — single label, not `<app-name>.<env>.25c-team1.art` | `storefront.25c-team1.art` |
| Helm release (if the route ships inside a chart) | Matches the namespace component convention in `CONVENTIONS.md` | — |

**Checked 2026-08-26: the hostname rule above replaces an earlier two-label form
(`<app-name>.<env>.25c-team1.art`) that was never actually usable.** The
`Gateway`'s TLS certificate SANs are `*.25c-team1.art` and the apex
`25c-team1.art` — one wildcard label. A two-label host fails the TLS
handshake before routing ever runs; it's not a style preference, the cert
can't serve it. Every real hostname on this cluster already follows the
single-label form (`rancher.25c-team1.art`, `storefront.25c-team1.art`) -
see §4 for what's actually issuing that cert today. If per-environment
hostnames are ever needed, that's a `@istio` decision requiring a wider
cert first, not something to route around per-app.

For local testing before a hostname's DNS record exists, use curl's
`--resolve` against the NLB's address rather than adding a workaround host
to the `Gateway`.

How the record itself gets created — and why a hostname in the `Gateway`'s
`hosts` is not the same thing as a hostname that resolves — is
[dns-records.md](dns-records.md).

Never route two apps through the same hostname distinguished only by path unless the app
explicitly is a path-based multi-service frontend — one hostname, one owning team, is what
keeps an incident page unambiguous about who to call.

---

## 4. TLS

Every `Gateway` listener terminates TLS. No plaintext HTTP listener ships past `dev`.

**Updated 2026-08-26: this is now live, not aspirational.** The `Gateway`'s
`credentialName` points at `wildcard-25c-team1-art-tls`, a cert-manager
`Certificate` (`platform-istio/wildcard-25c-team1-art`) issued by the
`letsencrypt-prod` `ClusterIssuer` via Route 53 DNS-01
(`gitops-flux#146`). Verified end to end, not just `Ready: True` on the
object:

```
$ curl -v --resolve rancher.25c-team1.art:443:<NLB IP> https://rancher.25c-team1.art/
*  issuer: C=US; O=Let's Encrypt; CN=YE2
*  SSL certificate verify ok.
```

No `(STAGING)` in the issuer, no manual `kubeseal` step, no browser warning.
The two things that used to sit behind this cert are gone: the self-signed
`SealedSecret` (`istio-gateway/sealed-tls-cert.yaml`) and Rancher's
`privateCA: true` + its own CA-bundle `SealedSecret`
(`rancher/tls-ca-sealedsecret.yaml`), which would have broken every Rancher
agent the moment the gateway stopped serving the cert they were pinned to -
both were removed in the same change that cut the gateway over, not as a
followup.

App teams still request a hostname from `@istio` the same way (§2); the cert
behind it is now a real, auto-renewing one. `letsencrypt-prod` has a real
rate limit (5 duplicate certificates per registered domain per week, no
appeal) - that's `@istio`'s constraint to manage when re-issuing, not
something an app team's hostname request needs to account for.

---

## 5. Environments

One cluster, environments are namespaces (ADR 0002) — `dev`, `stage`, `prod` are
`app-<name>` namespace suffixes, not separate `Gateway` objects or separate clusters.
Promotion is the pull request in `gitops-argocd` that changes which overlay's `HTTPRoute`
points at which image tag, per that repo's existing dev → stage → prod flow. It is never a
new route written by hand in a higher environment — if `dev`'s route works, `stage`'s and
`prod`'s are the same object with the overlay's values substituted in.

---

## 6. Topology and cost

Nodes span multiple AZs. Every `HTTPRoute`/`VirtualService` that fans out to more than one
backend pod should assume cross-AZ hops are possible unless topology-aware routing is
configured — that configuration is `@istio`'s (`gitops-flux`, topology-aware routing task),
not something an app team sets per-route. Mesh traffic that ignores this is quiet cost, not a
correctness bug, which is exactly why it is easy to miss in review.

---

## 7. Before you open a pull request

- Does this route attach only to a `Gateway`/hostname already granted to your namespace?
- Is there exactly one object (`HTTPRoute` *or* `VirtualService`) controlling this route —
  never both?
- Does the hostname follow §3, and does the `Gateway` listener behind it already have a
  certificate (§4)?
- Sidecar injection is opt-in per namespace (`istio.io/rev` label) — is your namespace
  actually labeled, or will your pods run outside the mesh silently?

## 8. Reviewing a route

1. **Does it stay inside the owning namespace?** A `parentRef`/`gateways:` entry naming
   anything outside `app-<name>` is an escalation, not a routing choice — see §2.
2. **Single controlling object?** Confirm no pre-existing `VirtualService` and `HTTPRoute`
   both claim the same host.
3. **TLS terminated, not passthrough**, unless the app has a documented reason to terminate
   its own TLS.
4. **What does a wrong host or path match do?** A route that silently 404s is safer under
   review than one that silently falls through to another team's service.
