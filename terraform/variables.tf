variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix used for naming/tagging every resource this creates."
  type        = string
  default     = "sentinel"
}

variable "instance_type" {
  description = "EC2 instance size. t3.large (8GB RAM) is the safe default - the backend loads an embedding model (sentence-transformers/torch) that's memory-hungry; t3.medium (4GB) can work for light/demo use but is tighter."
  type        = string
  default     = "t3.large"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size in GB. LanceDB data grows with test history - 50GB is a reasonable starting point, resize later if needed."
  type        = number
  default     = 50
}

variable "ssh_public_key_path" {
  description = "Path to your local SSH public key (the .pub file, not the private key). Used to create the AWS key pair so you can SSH into the instance."
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "allowed_ssh_cidr" {
  description = <<-EOT
    CIDR block allowed to SSH into the instance (port 22).
    Defaults to 0.0.0.0/0 (anywhere) purely so `terraform apply` works out of
    the box - you should restrict this to your own IP (e.g. "203.0.113.4/32")
    before/soon after first apply. Ports 80/443 stay open to everyone on
    purpose (that's the public-facing dashboard); only SSH access needs
    locking down.
  EOT
  type        = string
  default     = "0.0.0.0/0"
}

variable "domain_name" {
  description = "Optional domain name (e.g. sentinel.yourcompany.com) pointed at this instance's Elastic IP. Leave empty to access Sentinel by IP only (HTTP, no TLS) - see the deployment doc for adding a domain + HTTPS after the fact."
  type        = string
  default     = ""
}
