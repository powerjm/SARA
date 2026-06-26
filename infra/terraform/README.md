# terraform/

Provisions the experiment VM in AWS from the AMI that `../packer/` builds.

## Files

- `main.tf` — provider, AMI lookup (explicit `ami_id` or newest self-built
  `sara-lab-*`), a security group (SSH from your `/32`, all egress), and the EC2
  instance in the default VPC.
- `variables.tf` — `region`, `ami_id`, `instance_type` (hardware baseline),
  `key_name`, `researcher_cidr`, `root_volume_gb`, `tags`.
- `outputs.tf` — instance id, public IP/DNS, the launched AMI id, and an
  `ssh_command` convenience output.
- `lab.tfvars.example` — copy to `lab.tfvars` (gitignored) and fill in.

## Usage

```bash
cp lab.tfvars.example lab.tfvars   # set key_name + researcher_cidr (your /32)
terraform init
terraform validate
terraform plan  -var-file=lab.tfvars
terraform apply -var-file=lab.tfvars
terraform output ssh_command
# ... run the matrix (docs/REPRODUCTION.md) ...
terraform destroy -var-file=lab.tfvars
```

`lab.tfvars` and `*.tfstate*` are gitignored (researcher IP, account identifiers,
state). `researcher_cidr` rejects `0.0.0.0/0` — set it to your own address.

## Why a VM rather than a long-lived container

The hardware baseline is itself a dependent variable. CPU model, available RAM,
kernel scheduling — all affect timing measurements for local backends. A VM gives
a stable, declared baseline that is identical across backends. The chosen
`instance_type` should stay fixed across a run for record.

## Assumptions / notes

- Uses the account's **default VPC** and one of its subnets (a single lab
  instance; no bespoke networking). Adapt `main.tf` if you run without a default
  VPC.
- **Untested from this checkout** (no cloud account wired up here). Run
  `terraform validate` and `terraform plan` with credentials before `apply`.
