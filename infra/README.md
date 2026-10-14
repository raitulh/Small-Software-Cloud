# Infrastructure folder

Infrastructure-as-code for production is intentionally not prefilled with provider-specific resources before the deployment model, region, network topology, secrets store, database service and isolation runtime are chosen.

Before adding Terraform/Pulumi resources, document:

- The control-plane network vs build/runtime network boundaries.
- Private database/cache/registry endpoints and inbound/outbound rules.
- Secret/KMS integration and rotation plan.
- Workload isolation choice and runtime version.
- State storage and locking for IaC.
- Environments, approvals, drift detection, backup and restore procedures.
- Estimated baseline/peak monthly costs and capacity limits.

Do not add a public Docker socket or public database/cache port as an infrastructure shortcut.
