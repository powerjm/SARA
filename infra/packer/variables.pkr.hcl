# Build-time variables for sara-lab.pkr.hcl.
#
# Override on the CLI (`packer build -var region=us-west-2 ...`) or in a
# *.pkrvars.hcl file. Defaults target a small CPU build instance in us-east-1.

variable "region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region to build the AMI in."
}

variable "build_instance_type" {
  type        = string
  default     = "c7i.xlarge"
  description = "Instance type used to *build* the image (CPU is sufficient; the apparatus is API-backend driven)."
}

variable "root_volume_gb" {
  type        = number
  default     = 30
  description = "Root EBS volume size for the image (REPRODUCTION.md budgets ~20 GB)."
}

variable "repo_url" {
  type        = string
  default     = "https://github.com/jeffpowers/sara.git"
  description = "Git URL of the apparatus to bake into the image. Override for a fork or a local mirror."
}

variable "repo_ref" {
  type        = string
  default     = "main"
  description = "Git ref (tag/branch/commit) to clone. Use the run-for-record tag so the image's /etc/sara-version matches the thesis citation."
}
