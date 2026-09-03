# Runbook: put Rancher behind authentik SSO

Not an incident. This is the procedure for turning on Generic OIDC in Rancher
against authentik, and for getting back in when it goes wrong.

Serves `[rancher] Configure Rancher RBAC mapped to the workstream teams`
(`program/backlog.yaml`, workstream `rancher`, repo `gitops-flux`).

**Read this first: there is no GitOps path for this.** Rancher's auth provider
is not a Helm value. Nothing you add to `base/rancher/helmrelease.yaml` or the
`dev/25c-shared/rancher` overlay will configure it. Rancher stores the config in
a cluster-scoped `AuthConfig` object named `genericoidc`, and the only supported
ways to write it are the Rancher UI form and the Rancher API (which is what the
`rancher2_auth_config_generic_oidc` Terraform resource drives).

Applying that `AuthConfig` as a raw manifest through Flux is not documented by
SUSE and is deliberately not what this runbook does — see **Why not GitOps**
at the bottom. This is the one platform component whose identity config lives
in the cluster and not in Git, and that is a property of Rancher, not a
shortcut. The same is already true of the authentik half: the provider and
application for Argo CD were created by hand in the authentik UI, and nothing
in `gitops-flux` creates them either.

## Symptom

`https://rancher.25c-team1.art` presents a local username/password box. Everyone
who needs Rancher is sharing the generated bootstrap password, which is a single
credential in front of something that can reach every cluster Rancher manages.
Nobody's access is tied to their authentik account, so offboarding in authentik
does not remove Rancher access.

## Impact

Low while Rancher manages only itself. It stops being low the moment the home
k3s cluster is registered, because from then on the bootstrap password reaches
two clusters. Do this before that task, not after.

## Before you start

You need all four. Missing any one of them turns this into a lockout.

```bash
# 1. Rancher is up and its route works
kubectl -n cattle-system get deploy rancher
curl -s -o /dev/null -w '%{http_code}\n' https://rancher.25c-team1.art/ping

# 2. The bootstrap password (this is your escape hatch - write it down NOW)
kubectl -n cattle-system get secret bootstrap-secret \
  -o go-template='{{.data.bootstrapPassword|base64decode}}{{"\n"}}'

# 3. authentik is up and serving discovery
curl -s https://auth.25c-team1.art/-/health/ready/ -o /dev/null -w '%{http_code}\n'

# 4. Admin access to the authentik UI at https://auth.25c-team1.art
```

You also need the four authentik groups to exist already: `cto`, `pm`, `devops`,
`security`. These are the same group names Argo CD's `policy.csv` matches on
(`gitops-flux/infrastructures/base/argo-cd/helmrelease.yaml`), and they must
match exactly, including case.

### Know this before you start: the accounts have no email addresses

Stage 05 created all seventeen authentik users without an email address, while
SES was still in the sandbox, and authentik's user-settings flow does not let
people add their own. **This has already broken one integration.** Grafana
requires an email for `generic_oauth`; when userinfo carried none it fell back
to a GitHub-shaped `<api_url>/emails` endpoint that authentik does not serve,
and the 404 surfaced to the user as `Login failed - internal error` with nothing
pointing at the cause. gitops-flux#177 worked around it by mapping Grafana's
email field onto the username (`email_attribute_path: preferred_username`).

Rancher is **expected** to survive this, because it keys users on the OIDC `sub`
claim rather than on email. That is an expectation, not a verified result — it
has not been tested on this cluster. Given it already cost the platform one
confusing outage, check what the token actually carries before you conclude
Rancher is broken:

```bash
curl -s https://auth.25c-team1.art/application/o/rancher/.well-known/openid-configuration \
  | jq -r '.userinfo_endpoint'
```

If login fails with a message about a missing or invalid user rather than a
redirect or discovery error, this is the first thing to suspect, and the fix is
the same one Grafana is waiting on: set real email addresses on the authentik
users. Do not reach for a claim-mapping workaround in Rancher before checking
whether `sub` alone was enough.

## Immediate action — the authentik half

In the authentik admin interface at `https://auth.25c-team1.art`:

**Applications → Providers → Create → OAuth2/OpenID Provider**

| Field | Value |
|---|---|
| Name | `rancher` |
| Authentication flow | `default-authentication-flow` |
| Authorization flow | `default-provider-authorization-explicit-consent` |
| Client type | **Confidential** |
| Redirect URIs | `https://rancher.25c-team1.art/verify-auth` |
| Signing Key | any available certificate |
| Scopes | `openid`, `profile`, `email` (the defaults) |

Two things about that redirect URI:

- The path is `/verify-auth`. Not `/verify`, not the dashboard URL. Rancher
  publishes this exact callback and it is also, confusingly, what you type into
  Rancher's own **Rancher URL** field later.
- We run authentik **2026.8.1**, which is past 2026.5, so redirect URIs carry a
  **type** and a **purpose**. Set type `Strict` and purpose `Authorization`. On
  older authentik every URI was treated as Authorization automatically; on ours
  it is not, and a URI left on the wrong purpose produces a redirect the
  provider then refuses.

Copy the **Client ID** and **Client Secret** off this screen before leaving it.
The secret is retrievable later from the provider page, but not from anywhere
else.

Then **Applications → Applications → Create**:

| Field | Value |
|---|---|
| Name | `Rancher` |
| Slug | `rancher` |
| Provider | `rancher` |
| Launch URL | `https://rancher.25c-team1.art` |

**Set the Launch URL**, or the application has no clickable tile on the
authentik dashboard. `https://rancher.25c-team1.art/dashboard/auth/login` is the
right value and is as good as it gets — see the next section for why.

### Rancher is two clicks and cannot be made one. Stop trying.

This question will be asked. Answer it once with the evidence rather than
re-investigating, because the investigation is a dead end every time.

The tile lands the user on Rancher's login page and they must still press
**Log in with OIDC**. Grafana is one click. The difference is not configuration
on our side — it is that **Grafana has a URL that starts a login and Rancher
does not**:

| App | Launch URL | What that URL actually is |
|---|---|---|
| Grafana | `/login/generic_oauth` | **302** straight to authentik — an endpoint that *begins* the flow, `state` and PKCE minted server-side |
| Argo CD | `/auth/login` | same shape — a flow starter |
| Rancher | `/dashboard/auth/login` | **200** — a *page with a button*. Rancher offers nothing else to link to |

Rancher's login is a Vue app that assembles the OIDC request **in the browser,
after the page has loaded**. So the flow can only begin once you are already
looking at the page, and the button press *is* the beginning. There is no
earlier point to link to.

Rancher also refuses any login it did not start itself. When it starts one it
mints a one-time `state` and keeps a copy; authentik returns your half; Rancher
compares them. A cold link therefore fails, and this has been tested on this
cluster — a valid, freshly issued authentik code delivered to the callback with
no `state`:

```
https://rancher.25c-team1.art/verify-auth?code=e2995f17b3f64351b1c5aab1f03c26a6&state=
  -> 404  "The page you were looking for doesn't exist!"
```

Nothing was misconfigured. Rancher discarded a perfectly good login because it
had no matching ticket. That is the anti-forgery check doing its job, and it is
also what makes an IdP-initiated tile impossible.

Four independent confirmations, so nobody needs a fifth:

1. All 171 Rancher settings on this instance — no auto-redirect option.
   `hide-local-cluster` hides the local *cluster*, not local *login*.
2. `rancher/dashboard` login page source — reads `LOCAL`, `IS_SSO`, `IS_SLO`,
   `TIMED_OUT`, `LOGGED_OUT`, `err`; no auto-redirect, and no auto-trigger even
   when exactly one non-local provider is configured.
3. The 404 above.
4. [rancher/rancher#29376](https://github.com/rancher/rancher/issues/29376),
   "Option to disable default login and auto redirect to IdP" — opened October
   2020, still **open**. Rancher's own users have wanted this for six years.

The only mechanism that would work is a custom Rancher UI extension that presses
the button for you: JavaScript written against dashboard internals, maintained
across upgrades, to remove one click. Do not.

**The slug is load-bearing.** It is what makes the issuer URL, and a mismatch
here produces a discovery failure that reads as though authentik were down.
Confirm the issuer exists before you touch Rancher at all:

```bash
curl -s https://auth.25c-team1.art/application/o/rancher/.well-known/openid-configuration \
  | jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri}'
```

`issuer` must come back as exactly `https://auth.25c-team1.art/application/o/rancher/`
— **with the trailing slash**. That string is what you paste into Rancher. A 404
here means the slug does not match; fix it in authentik, not in Rancher.

## Immediate action — the Rancher half

Log in to `https://rancher.25c-team1.art` as the local `admin` using the
bootstrap password from step 2 above.

**☰ → Users & Authentication → Auth Provider → Generic OIDC**

| Field | Value |
|---|---|
| Client ID | from authentik |
| Client Secret | from authentik |
| Issuer | `https://auth.25c-team1.art/application/o/rancher/` |
| Rancher URL | `https://rancher.25c-team1.art/verify-auth` |
| Scopes | `openid profile email` |
| Groups Field | `groups` |
| Auth Endpoint | leave blank |
| Private Key / Certificate | **leave blank** |

On the last two:

- **Auth Endpoint** is discovered from the issuer. Fill it in only if diagnosis
  below tells you discovery is failing, in which case the value is
  `https://auth.25c-team1.art/application/o/authorize/` — note that one is
  global to authentik and has no slug in it.
- **Private Key / Certificate** is for an IdP serving a certificate the system
  trust store does not know. Ours does not qualify: the gateway serves a
  cert-manager Let's Encrypt production certificate (gitops-flux#146), which is
  why the overlay already sets `privateCA: false`. Pasting anything here gives
  Rancher a trust bundle that does not contain Let's Encrypt and breaks the
  token exchange.

`groups` needs no property mapping in authentik. Its default `profile` scope
already emits a `groups` claim, and Rancher's default `groups` field reads it.

Click **Enable**. Rancher redirects you to authentik, you log in there, and it
signs you back in as your authentik principal. **Do not close the browser until
you have confirmed you are still an administrator** — see the next section.

## Immediate action — do not skip this

Enabling through the form is what puts *your* principal into
`allowedPrincipalIds`. That is the entire reason this runbook uses the form and
not a manifest. Confirm it landed:

```bash
kubectl get authconfig genericoidc \
  -o jsonpath='{"enabled: "}{.enabled}{"\naccessMode: "}{.accessMode}{"\nallowed:\n"}{range .allowedPrincipalIds[*]}{"  "}{@}{"\n"}{end}'
```

You want `enabled: true` and at least one entry under `allowed:` that is your
own `genericoidc_user://...` principal. An empty `allowedPrincipalIds` with
`accessMode: restricted` is a locked door with nobody's key in it.

Then set the access mode. In the same Auth Provider screen, choose
**Restrict access to only Authorized Users and Groups**, and add the four
groups as authorized: `cto`, `pm`, `devops`, `security`. Left on the default
(any valid user), every account that exists in authentik — including any future
application-only account — can log in to Rancher.

Re-run the `kubectl get authconfig` command above and confirm `accessMode`
changed and the group principals are listed.

## Resolution — the group to role mapping

This is the half that makes the ticket "RBAC mapped to the workstream teams"
rather than "SSO". Mirror what Argo CD already does, so one group means one
thing across the platform:

| authentik group | Rancher global role | Access on the `local` cluster |
|---|---|---|
| `cto` | Administrator | — (global admin covers it) |
| `pm` | Administrator | — |
| `devops` | Standard User | Cluster Member |
| `security` | Standard User | Read Only |

`security` reading everything and changing nothing is the same call Argo CD's
`policy.csv` makes by giving that group no line and letting
`policy.default: role:readonly` cover it.

Global roles: **Users & Authentication → Groups**, pick the group, **Edit**,
assign the global role. The groups list is empty until at least one member of
that group has logged in once — Rancher learns groups from tokens, it does not
read your directory. If a group is missing, have someone in it log in.

Cluster access: **Cluster Management → local → Cluster & Project Members →
Add**, select **Group**, pick the group, choose the role.

Finally, once someone other than you has logged in through authentik and landed
on the right role, take the shared credential out of circulation:

```bash
# Confirm at least one non-you external user exists first
kubectl get users.management.cattle.io \
  -o custom-columns=NAME:.metadata.name,DISPLAY:.displayName,PRINCIPALS:.principalIds
```

## Diagnosis

**START HERE: can Rancher verify authentik's certificate?**

Run this before forming any theory. It is one command and it has already been
the answer once:

```bash
kubectl -n cattle-system exec deploy/rancher -- \
  curl -sS https://auth.25c-team1.art/application/o/token/
```

`curl: (60) SSL certificate problem: unable to get local issuer certificate`
means Rancher cannot complete the token exchange and **no amount of auth config
will help**. `405` is the healthy answer (the endpoint is POST-only).

This is not hypothetical — it is what was actually wrong on this cluster, and it
cost a day of looking in the wrong place. `rancher/rancher:v2.14.3` sets
`SSL_CERT_DIR=/etc/rancher/ssl` in the image; with `privateCA: false` nothing is
mounted there and the directory does not exist, so Rancher's entire outbound
trust store is empty. gitops-flux#179 pins `SSL_CERT_DIR=/etc/ssl/certs` in the
overlay's postRenderer. If that patch is ever dropped, this returns.

The tell is the shape of the failure: **the browser leg works and the login
still fails.** Users reach the authentik login screen normally, because the
browser never consults Rancher's trust store — only the server-to-server code
exchange behind it does. Anything that presents as "SSO is broken but authentik
looks fine" should come here first.

```bash
# confirm it is trust and not connectivity - this returns 200 when it is
kubectl -n cattle-system exec deploy/rancher -- curl -sSk -o /dev/null \
  -w '%{http_code}\n' https://auth.25c-team1.art/application/o/token/
```

**"Grafana and Argo CD are on the authentik dashboard and Rancher is not."**
Check whether the provider is enabled at all:

```bash
kubectl get authconfig genericoidc -o jsonpath='{.enabled}{"\n"}'
```

`false` or `NotFound` means SSO was never enabled. `true` means it is
configured, and a missing tile is an unset **Launch URL** on the authentik
application.

Be careful with this one. Because no PR to `gitops-flux` can configure Rancher's
auth, there is nothing in Git to confirm the work was done, and it is very easy
to conclude "nobody ever set this up" when in fact it was set up correctly and
is failing for the TLS reason above. Check the `AuthConfig` before believing
Git. A `genericoidc_user://` principal on any user in
`kubectl get users.management.cattle.io` proves someone has logged in
successfully at some point.

**Browser redirects to authentik, logs in, and returns to a Rancher error.**
The browser leg works and the server-to-server leg does not. Rancher itself must
reach `auth.25c-team1.art` to exchange the code for a token, and that request
leaves the pod, resolves the *public* name to the ingress load balancer, and has
to come back in through the same gateway. Test it from inside the pod:

```bash
kubectl -n cattle-system exec deploy/rancher -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
  https://auth.25c-team1.art/application/o/rancher/.well-known/openid-configuration
```

`200` means the hairpin works and the problem is elsewhere. A hang or a
connection error means it does not, and no amount of editing the auth form will
fix it — that is a networking finding for the istio workstream.

**"Client is unauthorised" or the callback is refused.** Redirect URI mismatch.
It is `https://rancher.25c-team1.art/verify-auth` in authentik, character for
character, on a URI whose purpose is `Authorization`.

**Discovery failure that looks like authentik being down.** The issuer is wrong.
Re-run the `.well-known` curl above. Missing trailing slash and a wrong slug both
land here.

**Logged in, but no groups and the wrong role.** Rancher got a token with no
`groups` claim. Check the provider's scopes include `profile` and that the
Groups Field in Rancher is `groups`. Confirm what actually arrived:

```bash
kubectl get users.management.cattle.io \
  -o custom-columns=NAME:.metadata.name,PRINCIPALS:.principalIds | grep genericoidc
```

**Rancher pod restarts or 502s during the flow.** Not an auth problem. Check the
pod landed on the platform pool — the overlay's postRenderer is what puts it
there, and a scheduling failure looks like an outage at exactly the wrong moment.

## Resolution — locked out

If nobody can log in, the provider is still disableable from the cluster. You do
not need the UI:

```bash
kubectl patch authconfig genericoidc --type merge -p '{"enabled":false}'
```

Local login returns immediately; no restart needed. Log back in as `admin` with
the bootstrap password, fix the config, enable again.

**Test this escape hatch on the day you turn SSO on, not on the day you need
it.** Disable, confirm the local login box comes back, re-enable through the
form. Ten minutes now against an outage later.

If the local `admin` has also lost its permissions — Rancher demotes the local
principal when it binds it to an external one — the recovery is to restore the
global role binding directly:

```bash
kubectl get globalrolebindings.management.cattle.io \
  -o custom-columns=NAME:.metadata.name,USER:.userName,ROLE:.globalRoleName | grep admin
```

## Prevention

- **Keep the bootstrap password.** It is the only credential that does not
  depend on authentik being up. It is generated in-cluster and never enters
  Git, which is the arrangement `base/rancher/helmrelease.yaml` documents — so
  losing it means losing the escape hatch, not looking it up somewhere.
- **authentik is now a hard dependency of Rancher.** authentik runs on the same
  two-node cluster with a single Postgres and an 8Gi volume. When that volume
  goes, Rancher access goes with it. The backup note in the authentik base
  release is not optional once this lands.
- **Record the client ID here or in the ticket, not the secret.** The secret
  stays in authentik and in Rancher's own `cattle-global-data` secret; there is
  no third copy to rotate.
- **Rotating the client secret is a two-place edit** — authentik provider, then
  the Rancher form — and there is no drift detection on either. This is a real
  exception to [`docs/secret-management.md`](../docs/secret-management.md),
  whose rotation model is "re-seal the new value, merge, Flux applies it, no
  out-of-band step". There is no `SealedSecret` here to re-seal and no pull
  request to merge, because neither copy of this credential is in Git. Rotation
  is manual, and nothing fails visibly if it never happens — so it needs a
  calendar reminder the way the GitHub PATs in that table do, not a review gate.

## Why not GitOps

Recorded here so the next person does not re-litigate it.

Rancher's `AuthConfig` *can* be applied as a manifest, and the client secret
does live in a normal Secret in `cattle-global-data` referenced as
`cattle-global-data:genericoidcconfig-clientsecret`, so a SealedSecret plus a
manifest in the rancher overlay looks tractable. It is not, for one specific
reason: `allowedPrincipalIds` has to contain a principal ID that does not exist
until a human has logged in through the provider once. Committing an
`AuthConfig` with `enabled: true`, `accessMode: restricted` and an empty or
guessed principal list locks every account out of Rancher on the next Flux
reconcile, on a cluster four workstreams are using.

The supported automated path, if this ever needs to be repeatable, is the
Rancher API — the `rancher2_auth_config_generic_oidc` Terraform resource, which
performs the same enable flow the form does and needs a Rancher API token to
run. That is a different ticket and a different repo, and it trades a manual
form for a long-lived admin token that would itself have to be stored somewhere.

## Sources

- [Configure Generic OIDC — Rancher Manager v2.14](https://documentation.suse.com/cloudnative/rancher-manager/v2.14/en/rancher-admin/users/authn-and-authz/configure-generic-oidc.html)
- [Integrate with Rancher — authentik](https://integrations.goauthentik.io/hypervisors-orchestrators/rancher/)
- [Configuring Authentication — Rancher Manager v2.14](https://documentation.suse.com/cloudnative/rancher-manager/v2.14/en/rancher-admin/users/authn-and-authz/authn-and-authz.html)
- [`rancher2_auth_config_generic_oidc`](https://registry.terraform.io/providers/rancher/rancher2/latest/docs/resources/auth_config_generic_oidc)
