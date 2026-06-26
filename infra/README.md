# infra/

Infrastructure-as-code for the cloud VM image that hosts the official
experimental runs. Local development happens on the workstation; the cloud option
gives every backend the same recorded hardware baseline (the *record* runs can
come from either environment as long as the one used is captured in the
replication snapshot).

## Layout

```
infra/
  README.md              <- this file
  packer/                <- VM image build (Packer)
    sara-lab.pkr.hcl     <- the image template
    variables.pkr.hcl    <- build-time variables
    provision/           <- install-base / install-tools / setup-experimenter
  terraform/             <- VM provisioning + networking (Terraform)
    main.tf variables.tf outputs.tf
    lab.tfvars.example   <- copy to lab.tfvars (gitignored) and fill in
```

These are real, reviewable IaC (AWS). They have **not** been `packer build` /
`terraform apply`-tested from this checkout (no cloud account is wired up here);
run `packer validate .` and `terraform validate` on a host with the tools and
credentials before a real build. Everything is parameterised — no account IDs,
IPs, or keys are committed.

## Build + provision sequence

```bash
# 1. Build the AMI with the apparatus + sandbox image + binary tools baked in.
cd infra/packer
packer init .
packer validate .
packer build -var repo_ref=<run-for-record-tag> sara-lab.pkr.hcl
#   -> writes packer-manifest.json with the new AMI id; the AMI's hash is the
#      apparatus/version baseline recorded in the replication snapshot.

# 2. Provision an instance from that AMI.
cd ../terraform
cp lab.tfvars.example lab.tfvars   # fill in key_name + researcher_cidr (your /32)
terraform init
terraform validate
terraform apply -var-file=lab.tfvars
terraform output ssh_command

# 3. SSH in, switch to the experimenter user, run the matrix (see docs/REPRODUCTION.md).
```

## CPU baseline, GPU optional

The baseline image and the default `instance_type` (`c7i.xlarge`) run the **API
backends** (Anthropic / OpenAI / Google) on CPU — sufficient for the full
cross-backend matrix without local models. Running *local* open-weight /
unrestricted models in the cloud additionally needs a **GPU** instance, NVIDIA
drivers, and an LM Studio / llama.cpp server; that is an explicit extension, not
part of the baseline (intentionally — the hardware baseline stays simple and the
GPU path is only needed for the local-model category).

## What the official VM provides

- Ubuntu 26.04 LTS (matched to `Dockerfile.sandbox`).
- Python 3.14, Docker, JDK 21.
- The `sara-sandbox:latest` validator image, pre-built; its id pinned in
  `/etc/sara-version` and `VALIDATOR_IMAGE` set in `/etc/environment`.
- The binary-analysis tools (radare2, ROPgadget, Ropper, GDB; Ghidra when
  `GHIDRA_URL` is supplied at build time).
- The apparatus cloned at the build `repo_ref` under `/opt/sara` (symlinked to
  `~experimenter/sara`), bootstrapped, with `make test` run during the build.
- A non-root `experimenter` user in the `docker` group.

The image hash is treated as a dependent variable of the experiment: its
provenance (`/etc/sara-version`) is captured by the replication snapshot's
environment summary.
