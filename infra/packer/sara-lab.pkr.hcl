# sara-lab.pkr.hcl — builds the cloud VM image (AMI) that hosts the official
# experimental runs. The image bakes in the apparatus, the validator sandbox
# image, and every binary-analysis tool, so a provisioned instance can run the
# matrix immediately. The image hash is the hardware/software baseline recorded
# in the replication snapshot (docs/REPLICATION_SNAPSHOT.md).
#
# Build:   packer init . && packer validate . && packer build sara-lab.pkr.hcl
# Provision an instance from the resulting AMI with ../terraform/.
#
# CPU baseline by design: this image runs the API backends (Anthropic / OpenAI /
# Google) on a CPU instance. Running *local* open-weight / unrestricted models in
# the cloud additionally needs a GPU instance + NVIDIA drivers + an LM Studio (or
# equivalent) server — an optional extension, intentionally out of this baseline.

packer {
  required_plugins {
    amazon = {
      version = ">= 1.3.0"
      source  = "github.com/hashicorp/amazon"
    }
  }
}

source "amazon-ebs" "lab" {
  ami_name      = "sara-lab-${var.repo_ref}-${formatdate("YYYYMMDD-hhmmss", timestamp())}"
  ami_description = "SARA experiment host (apparatus + validator sandbox + binary tools) at ${var.repo_ref}"
  instance_type = var.build_instance_type
  region        = var.region

  source_ami_filter {
    filters = {
      # Ubuntu 26.04 LTS, x86_64, HVM, EBS-backed — matched to Dockerfile.sandbox.
      name                = "ubuntu/images/hvm-ssd-gp3/ubuntu-*-26.04-amd64-server-*"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    most_recent = true
    owners      = ["099720109477"] # Canonical
  }

  ssh_username = "ubuntu"

  launch_block_device_mappings {
    device_name           = "/dev/sda1"
    volume_size           = var.root_volume_gb
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = {
    Project   = "sara"
    Component = "experiment-host"
    RepoRef   = var.repo_ref
    BuiltBy   = "packer"
  }
}

build {
  name    = "sara-lab"
  sources = ["source.amazon-ebs.lab"]

  # 1. Base OS: toolchain, Python 3.14, Docker, JDK 21.
  provisioner "shell" {
    script           = "./provision/install-base.sh"
    expect_disconnect = true # reboot is allowed if the kernel/docker setup asks for it
  }

  # 2. Binary-analysis tools + the apparatus itself (cloned, bootstrapped,
  #    sandbox image built) at the pinned ref.
  provisioner "shell" {
    script = "./provision/install-tools.sh"
    environment_vars = [
      "SARA_REPO_URL=${var.repo_url}",
      "SARA_REPO_REF=${var.repo_ref}",
    ]
  }

  # 3. The non-root `experimenter` user with docker access; record provenance.
  provisioner "shell" {
    script = "./provision/setup-experimenter.sh"
    environment_vars = [
      "SARA_REPO_REF=${var.repo_ref}",
    ]
  }

  # Emit the built AMI id + region so the build is consumable by ../terraform/.
  post-processor "manifest" {
    output     = "packer-manifest.json"
    strip_path = true
    custom_data = {
      repo_ref = var.repo_ref
      region   = var.region
    }
  }
}
