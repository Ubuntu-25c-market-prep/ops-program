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
| `Gateway` | `<env>-ingress` or `<env>-egress` | `dev-ingress` |
| Hostname | `<app-name>.<env>.25c-team1.art` | `storefront.dev.25c-team1.art` |
| Helm release (if the route ships inside a chart) | Matches the namespace component convention in `CONVENTIONS.md` | — |

Never route two apps through the same hostname distinguished only by path unless the app
explicitly is a path-based multi-service frontend — one hostname, one owning team, is what
keeps an incident page unambiguous about who to call.

---

## 4. TLS

Every `Gateway` listener terminates TLS. No plaintext HTTP listener ships past `dev`.

Certificates come from cert-manager, issuer `platform-issuer` (Route 53 DNS-01, wildcard per
environment). App teams do not create `Certificate` objects directly — request the hostname
via the same issue against `gitops-flux` used for the `Gateway` listener, and `@istio`
provisions both together. A `Gateway` listener and its certificate are provisioned as one
unit; requesting them separately is how a listener ends up live with no cert behind it.

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
