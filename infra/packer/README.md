# packer/

Builds the cloud VM image (AMI) used by `../terraform/` to provision the experiment VM. Placeholder until Phase 7.

## Planned image contents

- Ubuntu 26.04 LTS as the base.
- Python 3.14 from the default Ubuntu 26.04 repositories.
- Docker 24+.
- The `sara-sandbox:latest` validator image, pulled and pinned by digest.
- Ghidra 11+, radare2, ROPgadget, Ropper, pwntools, GDB, gdbserver.
- A non-root `experimenter` user with docker group membership and rootless Docker pre-configured.
- This repository cloned at `/home/experimenter/sara` at the commit recorded in `/etc/sara-version`.

## Planned Packer template skeleton

```hcl
# packer/sara-lab.pkr.hcl  (Phase 7 deliverable)
#
# packer {
#   required_plugins {
#     amazon = {
#       version = ">= 1.3"
#       source  = "github.com/hashicorp/amazon"
#     }
#   }
# }
#
# source "amazon-ebs" "lab" {
#   ami_name      = "sara-lab-{{timestamp}}"
#   instance_type = "c7i.xlarge"
#   region        = "us-east-1"
#   source_ami_filter {
#     filters = {
#       # Ubuntu 26.04 LTS, x86_64, HVM, EBS-backed.
#       name                = "ubuntu/images/hvm-ssd-gp3/ubuntu-*-26.04-amd64-server-*"
#       root-device-type    = "ebs"
#       virtualization-type = "hvm"
#     }
#     most_recent = true
#     owners      = ["099720109477"]  # Canonical
#   }
#   ssh_username = "ubuntu"
# }
#
# build {
#   sources = ["source.amazon-ebs.lab"]
#   provisioner "shell" { script = "./provision/install-base.sh" }
#   provisioner "shell" { script = "./provision/install-tools.sh" }
#   provisioner "shell" { script = "./provision/setup-experimenter.sh" }
# }
```
