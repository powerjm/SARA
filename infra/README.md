# infra/

Infrastructure-as-code for the cloud VM image that hosts the official experimental runs. Local development happens on the workstation; the *record* runs (the ones whose `RunRecord`s go into the thesis) all happen on the cloud VM so every backend gets the same hardware baseline.

## Layout

```
infra/
  README.md              <- this file
  packer/                <- VM image build (Packer)
    README.md
  terraform/             <- VM provisioning + networking (Terraform)
    README.md
    main.tf.placeholder
    variables.tf.placeholder
    outputs.tf.placeholder
```

> Files end with `.placeholder` until the design lands. This avoids `terraform init` accidentally picking up empty files and creating empty state.

## Build sequence (Phase 7)

```bash
# 1. Build the AMI/disk image with the apparatus + sandbox already baked in.
cd infra/packer
packer init .
packer build sara-lab.pkr.hcl

# 2. Provision a VM from the image.
cd ../terraform
terraform init
terraform apply

# 3. SSH into the VM, clone this repo at the pinned commit, and run experiments.
```

## What the official VM provides

- Ubuntu 26.04 LTS (matched to `Dockerfile.sandbox`).
- Python 3.14 from the default Ubuntu 26.04 repositories.
- Docker 24+, configured for rootless operation.
- The validator sandbox image pre-pulled with its digest pinned in `/etc/environment`.
- All optional binary-analysis tools (Ghidra, radare2, ROPgadget, Ropper, pwntools, GDB) pre-installed.
- A non-root researcher user `experimenter` with `docker` group membership.

The image baseline is treated as a dependent variable of the experiment: its hash is recorded in every `RunRecord.notes` field that runs from it.
