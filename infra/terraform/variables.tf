variable "region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region (must match where ../packer/ built the AMI)."
}

variable "ami_id" {
  type        = string
  default     = ""
  description = "AMI to launch. Leave empty to auto-select the most recent self-built sara-lab-* image."
}

variable "instance_type" {
  type        = string
  default     = "c7i.xlarge"
  description = <<-EOT
    Instance type — the experiment's hardware baseline; keep fixed across a run
    for record. Default c7i.xlarge runs the API backends (Anthropic/OpenAI/Google)
    on CPU. Running *local* open-weight/unrestricted models in the cloud needs a
    GPU type (e.g. g5.xlarge / g6.xlarge) AND an image with NVIDIA drivers + an
    LM Studio/llama.cpp server — not in the baseline packer image.
  EOT
}

variable "key_name" {
  type        = string
  description = "Name of an existing EC2 key pair for SSH access (required)."
}

variable "researcher_cidr" {
  type        = string
  description = "CIDR allowed to SSH in, e.g. \"203.0.113.4/32\". Do not use 0.0.0.0/0."

  validation {
    condition     = var.researcher_cidr != "0.0.0.0/0"
    error_message = "Refusing 0.0.0.0/0 for SSH; set researcher_cidr to your own /32."
  }
}

variable "root_volume_gb" {
  type        = number
  default     = 30
  description = "Root EBS volume size in GB (REPRODUCTION.md budgets ~20 GB)."
}

variable "tags" {
  type        = map(string)
  default     = { Project = "sara", Component = "experiment-host" }
  description = "Tags applied to created resources."
}
