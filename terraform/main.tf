# Uses the account's default VPC/subnet on purpose - this is meant to be a
# single self-contained VM (matching Sentinel's "deploy like a simple VM"
# story), not a custom network topology. If your account's default VPC was
# deleted, create one (`aws ec2 create-default-vpc`) or swap this for a
# specific aws_vpc/aws_subnet data source.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Latest Ubuntu 22.04 LTS - deliberately not 24.04: Sentinel's backend pins
# torch==2.1.0, which is safest against the Python 3.11 that Ubuntu 22.04's
# deadsnakes-installed interpreter gives us (see user_data.sh), avoiding any
# risk of missing prebuilt wheels for a newer Python.
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_key_pair" "sentinel" {
  key_name   = "${var.project_name}-key"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

resource "aws_security_group" "sentinel" {
  name        = "${var.project_name}-sg"
  description = "Sentinel host: SSH (restricted) + HTTP/HTTPS (public dashboard)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  ingress {
    description = "HTTP (nginx - redirects to HTTPS once a domain+cert are configured)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS (nginx)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Deliberately NOT opening 8000 (backend) or 3000 (frontend) to the
  # internet - nginx is the only public entry point, matching
  # LIVE_EXECUTION_VM_DEPLOYMENT.md. Both are bound to 127.0.0.1 by the
  # systemd units user_data.sh installs.

  egress {
    description = "All outbound (package installs, LLM API calls, etc.)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg"
  }
}

resource "aws_instance" "sentinel" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.sentinel.key_name
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.sentinel.id]

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_size_gb
  }

  # Static bootstrap script - no Terraform variable interpolation inside it
  # on purpose (mixing HCL ${} interpolation with bash's own ${} syntax is a
  # common source of broken cloud-init scripts). It only installs base
  # packages and systemd/nginx *templates*; deploy.sh (plain bash, run
  # locally after `terraform apply`) pushes the actual application code and
  # fills in anything environment-specific.
  user_data                   = file("${path.module}/user_data.sh")
  user_data_replace_on_change = false

  tags = {
    Name = "${var.project_name}-host"
  }
}

resource "aws_eip" "sentinel" {
  instance = aws_instance.sentinel.id
  domain   = "vpc"

  tags = {
    Name = "${var.project_name}-ip"
  }
}
