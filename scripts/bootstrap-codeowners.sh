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
*            ${O}/cto
EOF
    ;;
    infra-modules) cat <<EOF
# Reusable, tag-versioned Terraform modules. Consumed by every workstream, so review is centralised.
*            ${O}/infra ${O}/cto
EOF
    ;;
    platform-addons) cat <<EOF
# Cluster add-ons. One directory per workstream so six teams can work without merge contention.
/core/       ${O}/infra
/scaling/    ${O}/scaling
/utils/      ${O}/utils
/velero/     ${O}/velero
/rancher/    ${O}/rancher
/istio/      ${O}/istio
*            ${O}/cto
EOF
    ;;
    platform-observability) cat <<EOF
# Observability stack. One directory per workstream.
/monitoring/ ${O}/monitoring
/logging/    ${O}/logging
/tracing/    ${O}/tracing
/finops/     ${O}/finops
*            ${O}/cto
EOF
    ;;
    platform-security) cat <<EOF
# Policy and Zero Trust. Security owns admission control, ZeroTrust owns mesh identity.
/kyverno/    ${O}/security
/policy-reporter/ ${O}/security
/zerotrust/  ${O}/zerotrust
*            ${O}/cto
EOF
    ;;
    gitops-flux) cat <<EOF
# Flux desired state for platform apps.
*            ${O}/flux ${O}/cto
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
/adr/        ${O}/pm ${O}/cto
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

for repo in infra-aws infra-modules platform-addons platform-observability \
            platform-security gitops-flux gitops-argocd apps-business \
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
