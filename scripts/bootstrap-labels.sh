#!/usr/bin/env bash
# Apply the org-wide label taxonomy to every repo.
# Idempotent: creates missing labels, updates colour/description on existing ones.
set -euo pipefail

ORG="${ORG:-Ubuntu-25c-market-prep}"

# Seven repositories: six from ADR 0010 plus platform-security, carved back out
# by ADR 0011. Archived repositories must not be listed - the label API rejects
# writes to a read-only repo and the run fails. platform-addons,
# platform-observability and infra-modules are archived; keep them out.
REPOS=(
  infra-aws
  platform-security
  gitops-flux gitops-argocd apps-business
  ops-program .github
)

# name|colour|description
LABELS=(
  "ws:infra|0e8a16|Networking, EKS, ECR"
  "ws:security|0e8a16|IAM, permissions, Kyverno, Policy Reporter"
  "ws:scaling|0e8a16|Karpenter, KEDA, HPA"
  "ws:argocd|0e8a16|Argo CD / Argo Workflows, business app GitOps"
  "ws:flux|0e8a16|Flux CD, platform app GitOps"
  "ws:monitoring|0e8a16|Prometheus / Grafana"
  "ws:logging|0e8a16|EFK logging pipeline"
  "ws:tracing|0e8a16|OpenTelemetry, Jaeger, Kiali"
  "ws:utils|0e8a16|cert-manager, external-dns, sealed-secrets"
  "ws:velero|0e8a16|Backup and restore"
  "ws:rancher|0e8a16|Multi-cluster management"
  "ws:finops|0e8a16|Kubecost cost visibility"
  "ws:istio|0e8a16|Service mesh"
  "ws:zerotrust|0e8a16|Zero Trust solution"
  "ws:bedrock|0e8a16|AWS Bedrock integration"

  "type:epic|3e4b9e|Workstream-level epic, owns sub-issues"
  "type:story|1d76db|User-facing deliverable"
  "type:task|c5def5|Unit of implementation work"
  "type:bug|d73a4a|Defect"
  "type:spike|fbca04|Timeboxed investigation"
  "type:toil|5319e7|Manual repeat work to automate away"
  "type:docs|0075ca|Documentation, ADR, runbook"

  "pri:P1|b60205|Blocks the wave"
  "pri:P2|d93f0b|Needed this wave"
  "pri:P3|fef2c0|Opportunistic"

  "size:S|bfd4f2|Under a day"
  "size:M|bfd4f2|A few days"
  "size:L|bfd4f2|About a sprint"
  "size:XL|bfd4f2|Split this"

  "env:dev|c2e0c6|Development"
  "env:stage|fef2c0|Staging"
  "env:prod|f9d0c4|Production"

  "blocked|b60205|Waiting on a dependency"
  "needs-review|fbca04|Awaiting review"
  "good-first-task|7057ff|Good entry point for onboarding"
)

for repo in "${REPOS[@]}"; do
  echo "==> ${ORG}/${repo}"
  for spec in "${LABELS[@]}"; do
    IFS='|' read -r name colour desc <<<"$spec"
    gh label create "$name" \
      --repo "${ORG}/${repo}" \
      --color "$colour" \
      --description "$desc" \
      --force >/dev/null 2>&1 \
      && printf '    %s\n' "$name" \
      || printf '    FAILED %s\n' "$name"
  done
done

echo "Done. ${#LABELS[@]} labels across ${#REPOS[@]} repos."
