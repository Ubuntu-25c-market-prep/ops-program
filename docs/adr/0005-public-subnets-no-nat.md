# 0005. Public subnets only, no NAT gateway, IPv4

**Status:** Accepted
**Date:** 2026-08-01
**Deciders:** @cto, @infra, @security

## Context

The reference VPC design puts worker nodes in private subnets reaching the
internet through NAT gateways. For this platform that costs:

| Item | Monthly |
|---|---|
| 3 × NAT gateway (one per AZ) | $99 |
| NAT data processing (~700 GB) | $30 |
| 5 × interface endpoint × 3 AZ, whose main justification was avoiding NAT data charges | $110 |
| | **~$239** |

That is roughly 12% of the platform bill, spent entirely on network plumbing for
a programme whose cluster serves no external customers.

## Decision

One VPC, **public subnets only**, IPv4. Worker nodes carry public IPs and reach
the internet directly through the internet gateway. No NAT gateways. No paid
interface endpoints.

Free **gateway** endpoints for S3 and DynamoDB stay — they cost nothing and keep
ECR layer pulls off the public path.

## Alternatives considered

**Private subnets with NAT** — the default for good reason: nodes are
unreachable from the internet regardless of security group mistakes. Rejected on
cost for a programme with no external traffic and a $200/month ceiling.

**Single NAT gateway shared across AZs** — $33/month instead of $99, keeps nodes
private. Rejected because it reintroduces a single point of failure and still
carries data processing charges, for a third of the saving.

**IPv6 with an egress-only internet gateway** — this is the technically superior
answer: egress-only IGW is **free**, so you get NAT-free egress *and* nodes that
cannot be reached inbound. Rejected for now because EKS IPv6 mode is all-or-
nothing per cluster, several add-ons and workloads in the stack assume IPv4, and
debugging dual-stack issues would cost the team more time than the $239 is worth.
**This is the decision most likely to be revisited.**

## Consequences

Nodes have public IP addresses. The security group is now the only thing between
the internet and the kubelet. The following stop being good practice and become
**required**, enforced rather than documented:

| Control | Owner | Why it is now load-bearing |
|---|---|---|
| Node SG denies all inbound from `0.0.0.0/0`; ingress only from the load balancer SG and the cluster SG | `@infra` | The single barrier. A permissive rule here is an internet-exposed kubelet. |
| **IMDSv2 required, hop limit 1** | `@infra` | An SSRF in any pod becomes credential theft against a publicly addressable node. Non-negotiable. |
| EKS API endpoint public access restricted to known CIDRs | `@infra` | Otherwise the control plane is open alongside the nodes. |
| No SSH, no key pairs — SSM Session Manager only | `@infra` | Port 22 on a public host is a login attempt generator. |
| GuardDuty enabled | `@security` | Was optional; with public nodes it is how you learn about the thing you missed. |
| Kyverno denies `hostNetwork` and privileged pods | `@security` | A hostNetwork pod on a public node binds to the public interface. |
| Default-deny NetworkPolicy | `@zerotrust` | Limits lateral movement once something does get in. |

Other consequences:

- Saves roughly **$239/month**, taking the platform estimate to about
  **$1,985/month**.
- No NAT means no NAT data processing charges and no NAT as a bandwidth
  bottleneck.
- **Not CIS EKS Benchmark compliant.** The benchmark requires worker nodes in
  private subnets. If this platform ever needs to pass an audit, this ADR is the
  first finding, and reversing it means rebuilding the VPC.
- Cross-AZ traffic charges are unaffected — they are a separate line and Istio
  topology-aware routing still matters.
- Pods receive private VPC addresses and egress via the node's public IP. Only
  node ENIs are publicly addressable.

## Reversal cost

High. Moving to private subnets means new subnets, new route tables, new NAT
gateways, and recycling every node. Plan a maintenance window, not a pull
request.
