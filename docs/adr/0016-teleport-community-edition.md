# 0016. Run Teleport Community Edition, and buy the missing SSO with MFA

**Status:** Proposed
**Date:** 2026-09-27
**Deciders:** @zerotrust, @security, @cto

## Context

Teleport is the access plane for `dev-eks-us-east-1`. The EKS API endpoint is
private (`endpointPublicAccess: false`), so every route to the cluster goes
through either the bastion tunnel or Teleport, and Teleport additionally
fronts internal web UIs that have no ingress of their own.

Teleport ships in two editions. **Community Edition** is AGPL v3 and free, and
is licensed for organisations **under 100 employees and under $10M annual
revenue** — confirmed applicable to this organisation. **Enterprise** is
commercial and is the only edition that carries SAML/OIDC connectors to an
external identity provider, along with Access Requests, Device Trust and
moderated sessions.

Two facts decide this:

1. **There is no identity provider to connect to.** authentik ran on
   `25c-shared`, which was torn down in September. There is no `authentik`
   namespace on this cluster, no `auth.25c-team1.art` record in Route 53, and
   its SealedSecrets are encrypted to the dead cluster's controller key. The
   single feature Enterprise would be bought for has nothing to point at.

2. **Application Access is a Community feature, and is already load-bearing.**
   The agent has run `roles: app` for eight days, proxying Kiali, Prometheus
   and OpenCost — three UIs with no ingress. This is not a feature under
   consideration; it is the existing front door.

## Decision

Run **Teleport Community Edition** (`enterprise: false`, the
`teleport-distroless` image, no licence secret), and accept that there are no
SSO connectors.

Compensate with **local Teleport users and a mandatory second factor**
(`authentication.type: local`, `second_factors` enforced). MFA is the control
that substitutes for a central identity provider, not an afterthought.

Use **Teleport Application Access as the standard front door for internal web
UIs**. A UI with no public ingress is registered as an entry in the agent's
`app_service.apps` list and reached at `<app>.teleport.25c-team1.art`, covered
by the existing wildcard record. This applies to Grafana and Alertmanager as it
already does to Prometheus.

## Alternatives considered

**Teleport Enterprise.** Rejected on cost, and honestly so — but the cost is
not the whole reason. The only capability we would be buying today is SSO
connectors, and there is no IdP for them to federate with. Buying Enterprise
now would mean paying for a connector to nothing.

**authentik as an OIDC provider, with a public ingress per UI.** Rejected on
three independent grounds. It needs `auth.25c-team1.art` to resolve, and
external-dns has been dead since 19 September, so no new hostname can be
created at all — an OIDC flow redirects the user's *browser* to the issuer, so
this is fatal, not inconvenient. It costs roughly 1280Mi of memory requests and
an 8Gi volume across three pods, on a cluster already at 76% memory requests
where Kibana is OOM-looping. And its SealedSecrets would have to be regenerated
and resealed for this cluster. It also would not remove Teleport, which remains
the access plane regardless — it would add a second system, not replace one.

**A public ingress per UI, each using the application's own login.** Rejected
on merit. It puts every internal console on the internet and multiplies the
number of authentication surfaces to secure, audit and offboard from. Teleport
already gives one audited door with MFA in front of it.

## Consequences

**What this makes easy.** Putting an internal UI behind authenticated access is
a three-line change to one list, with no ingress, no certificate, no DNS record
and no memory cost. Notably it is the **only** authentication path currently
open: every alternative depends on creating a DNS record, and external-dns
cannot create one. Access is audited centrally, and revoking a person removes
their access to every proxied UI at once.

**What this makes hard, and what we are accepting.**

- **User lifecycle is manual.** With no IdP there is no automatic
  deprovisioning. Offboarding is a deliberate Teleport operation, and nothing
  will remind anyone to perform it. This is the cost that will hurt.
- **Teleport becomes a single point of access.** If the proxy is down, every
  UI behind it is unreachable. Already true of three; this widens the blast
  radius rather than creating it.
- **AGPL v3 is a real licence, not "free to do anything".** Internal platform
  use is squarely fine. Distributing Teleport, or offering it as a service to
  third parties, carries source-availability obligations. Anyone considering
  either must read the licence first.
- **Eligibility is a moving target.** "Under 100 employees and under $10M
  annual revenue" is a threshold this organisation can cross without anyone
  noticing, and nothing in the system checks it. **Re-read this ADR if the
  organisation grows**; do not silently outgrow it.
- **Adopting an IdP later reopens this decision.** At that point the choice is
  to buy Enterprise for connectors, or to place the IdP in front of Teleport
  and keep Community. This ADR does not decide that, and should be superseded
  rather than amended when it is faced.

**What it does not decide.** Whether Grafana consumes Teleport's forwarded JWT
(`auth.jwt` against the cluster's JWKS) or simply sits behind the proxy with
its own local admin is an implementation choice for the monitoring workstream,
not an edition decision.
