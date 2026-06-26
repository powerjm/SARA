# Provisions the SARA experiment VM in AWS from the AMI that ../packer/ builds.
# A single instance is enough: the apparatus runs the matrix locally on the box;
# nothing inbound is served. The hardware baseline (instance type) is a declared
# dependent variable of the experiment — keep it fixed across a run for record.
#
#   terraform init
#   terraform validate
#   terraform plan  -var-file=lab.tfvars
#   terraform apply -var-file=lab.tfvars
#   terraform output ssh_command          # connect and run the matrix
#   terraform destroy -var-file=lab.tfvars # when done

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# --- AMI: explicit id, or the most recent self-built sara-lab image --------- #
data "aws_ami" "sara_lab" {
  count       = var.ami_id == "" ? 1 : 0
  most_recent = true
  owners      = ["self"]
  filter {
    name   = "name"
    values = ["sara-lab-*"]
  }
}

locals {
  ami_id = var.ami_id != "" ? var.ami_id : data.aws_ami.sara_lab[0].id
}

# --- Networking: default VPC + one of its subnets (single lab instance) ------ #
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "sara" {
  name_prefix = "sara-experiment-"
  description = "SARA experiment host: SSH in from the researcher; all egress (LLM APIs, apt, pip)."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH from the researcher"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.researcher_cidr]
  }

  egress {
    description = "All outbound (backend APIs, package mirrors)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "sara-experiment" })
}

resource "aws_instance" "sara" {
  ami                         = local.ami_id
  instance_type               = var.instance_type
  key_name                    = var.key_name
  subnet_id                   = element(data.aws_subnets.default.ids, 0)
  vpc_security_group_ids      = [aws_security_group.sara.id]
  associate_public_ip_address = true

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
    encrypted   = true
  }

  tags = merge(var.tags, {
    Name           = "sara-experiment"
    RunEnvironment = "cloud"
  })
}
