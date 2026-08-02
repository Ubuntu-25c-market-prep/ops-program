# Runbook: cost freeze triggered

## Symptom

Terraform applies and console actions start failing in the workload account with
`AccessDenied` / `explicit deny in a service control policy`, on actions like
`ec2:RunInstances`, `eks:CreateCluster`, `elasticloadbalancing:CreateLoadBalancer`.

An email from AWS Budgets stating the action was executed usually arrives first.

## Impact

**New resource creation is blocked** in the workload account. Existing workloads
keep running and keep billing — the freeze is a brake, not a kill switch.
Autoscaling that needs to launch new nodes will fail, so this can degrade a
running service even though nothing was terminated.

## Immediate action

Confirm the freeze is what you are seeing rather than an unrelated permissions
problem:

```bash
aws organizations list-targets-for-policy --policy-id p-d5aegejc
```

Non-empty output means the freeze is attached to the listed accounts.

## Diagnosis

Find what actually spent the money before lifting anything.

```bash
# Where the spend went, this month, by service
aws ce get-cost-and-usage \
  --time-period Start=$(date -u +%Y-%m-01),End=$(date -u +%Y-%m-%d) \
  --granularity MONTHLY --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --query 'ResultsByTime[0].Groups[?Total.UnblendedCost.Amount>`5`].[Keys[0],Total.UnblendedCost.Amount]' \
  --output table

# What is actually running
aws ec2 describe-instances --filters Name=instance-state-name,Values=running \
  --query 'Reservations[].Instances[].[InstanceId,InstanceType,LaunchTime]' --output table
aws eks list-clusters
aws elbv2 describe-load-balancers --query 'LoadBalancers[].[LoadBalancerName,Type,CreatedTime]' --output table
```

The usual causes, in order of likelihood:

1. Karpenter provisioning far more capacity than expected — check for a workload
   with no resource limits, or a NodePool with no `limits` block.
2. Something created outside Terraform and never torn down.
3. Observability retention growing unbounded on EBS.
4. Cross-AZ or NAT data processing, which shows up as EC2-Other, not as an
   obvious resource.

## Resolution

**Fix the cause first.** Lifting the freeze without fixing anything means it
re-attaches at the next evaluation, and you will have lost the signal.

Once remediated, detach:

```bash
aws organizations detach-policy --policy-id p-d5aegejc --target-id 808540602855
```

Then either raise the ceiling deliberately, or confirm spend is back under it:

```bash
aws budgets describe-budget --account-id 909783398044 --budget-name u25c-org-monthly \
  --query 'Budget.[BudgetLimit.Amount,CalculatedSpend.ActualSpend.Amount]' --output text
```

Raising the ceiling is a change to `infra-aws/budgets/terraform.tfvars` through a
pull request, not a console edit. A console edit will be reverted by the next
apply, silently.

## Prevention

- Karpenter NodePools carry a `limits` block. A NodePool without one has no upper
  bound by design.
- Every workload has resource requests and limits; Kyverno enforces it.
- Raise the ceiling *before* a wave lands that will legitimately need it, not
  after the freeze fires.
- If the freeze fires on legitimate growth twice, the ceiling is wrong. Change
  the number rather than training the team to ignore the alert.
