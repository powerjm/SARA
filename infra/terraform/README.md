# terraform/

Provisions the experiment VM in AWS from the AMI that `../packer/` builds.

Placeholder files end with `.placeholder` to keep `terraform init` from picking them up before they are filled in. Rename each to drop the suffix when the cloud account is wired up.

## Usage (once filled in)

```bash
terraform init
terraform plan -var-file=lab.tfvars
terraform apply -var-file=lab.tfvars
```

`lab.tfvars` is gitignored (contains the researcher IP and account-specific identifiers). Use `lab.tfvars.example` as a starter.

## Why a VM rather than a long-lived container

The hardware baseline is itself a dependent variable. CPU model, available RAM, kernel scheduling — all of these affect timing measurements for local backends. A VM gives a stable, declared baseline that's identical across backends.
