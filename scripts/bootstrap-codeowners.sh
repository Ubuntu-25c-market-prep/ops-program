#!/usr/bin/env bash
# Commit .github/CODEOWNERS to every repo via the contents API.
# Idempotent: updates in place when the file already exists.
set -euo pipefail

ORG="${ORG:-Ubuntu-25c-market-prep}"
O="@${ORG}"

codeowners_for() {
  case "$1" in
    infra-aws) cat <<EOF
# Terraform for AWS primitives. Path ownership follows the workstream that owns the resource.
/network/    ${O}/infra
/eks/        ${O}/infra
/ecr/        ${O}/infra
/iam/        ${O}/security
/bedrock/    ${O}/bedrock
# Called by every layer above, so review is centralised on @infra.
/modules/    ${O}/infra
*            ${O}/cto
EOF
    ;;
    platform-security) cat <<EOF
# Policy and Zero Trust. Security owns admission control, ZeroTrust owns mesh identity.
#
# Carved back out of gitops-flux by ADR 0011: admission control decides what may
# run, so its review population is a separate blast radius and does not sit one
# mis-scoped path entry away from six other workstreams.
/kyverno/    ${O}/security
/policy-reporter/ ${O}/security
/zerotrust/  ${O}/zerotrust
*            ${O}/cto
EOF
    ;;
    gitops-flux) cat <<EOF
# Everything Flux reconciles into the cluster.
#
# Delivery objects belong to @flux; component configuration belongs to the
# workstream that runs the component. Five workstreams share this repository
# without merge contention because none of them touch the same directories.
#
# Absorbed platform-addons and platform-observability per ADR 0010. Path
# ownership is carried over unchanged from those repositories. Security policy
# went back to platform-security per ADR 0011 and is not owned here.

# Flux delivery objects - HelmReleases, Kustomizations, sources, bootstrap.
/clusters/                     ${O}/flux

# Add-on configuration.
/addons/core/                  ${O}/infra
/addons/scaling/               ${O}/scaling
/addons/utils/                 ${O}/utils
/addons/velero/                ${O}/velero
/addons/rancher/               ${O}/rancher
/addons/istio/                 ${O}/istio

# Observability.
/observability/monitoring/     ${O}/monitoring
/observability/logging/        ${O}/logging
/observability/tracing/        ${O}/tracing
/observability/finops/         ${O}/finops

*                              ${O}/flux ${O}/cto
EOF
    ;;
    gitops-argocd) cat <<EOF
# Argo CD / Argo Workflows desired state for business apps.
*            ${O}/argocd ${O}/cto
EOF
    ;;
    apps-business) cat <<EOF
# Business application source.
*            ${O}/argocd ${O}/cto
EOF
    ;;
    ops-program) cat <<EOF
# Program tracking: epics, backlog manifest, ADRs, runbooks.
/program/    ${O}/pm
/docs/adr/   ${O}/pm ${O}/cto
*            ${O}/pm ${O}/cto
EOF
    ;;
    .github) cat <<EOF
# Org-wide templates and reusable workflows.
*            ${O}/cto
EOF
    ;;
  esac
}

for repo in infra-aws platform-security gitops-flux gitops-argocd apps-business \
            ops-program .github; do
  body="$(codeowners_for "$repo" | base64 -w0)"
  sha="$(gh api "repos/${ORG}/${repo}/contents/.github/CODEOWNERS" --jq '.sha' 2>/dev/null || true)"

  if [[ -n "$sha" ]]; then
    gh api --method PUT "repos/${ORG}/${repo}/contents/.github/CODEOWNERS" \
      -f message="chore(ops): update CODEOWNERS" -f content="$body" -f sha="$sha" \
      --silent && echo "  updated: ${repo}"
  else
    gh api --method PUT "repos/${ORG}/${repo}/contents/.github/CODEOWNERS" \
      -f message="chore(ops): add CODEOWNERS" -f content="$body" \
      --silent && echo "  created: ${repo}"
  fi
done
