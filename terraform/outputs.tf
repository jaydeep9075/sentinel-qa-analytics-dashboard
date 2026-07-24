output "instance_public_ip" {
  description = "Stable public IP (Elastic IP) of the Sentinel host. Use this to SSH in, run deploy.sh, and browse the dashboard."
  value       = aws_eip.sentinel.public_ip
}

output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.sentinel.id
}

output "ssh_command" {
  description = "Ready-to-run SSH command."
  value       = "ssh ubuntu@${aws_eip.sentinel.public_ip}"
}

output "dashboard_url" {
  description = "URL to open once deploy.sh has finished (HTTP only until a domain + TLS cert are configured - see the deployment doc)."
  value       = "http://${aws_eip.sentinel.public_ip}"
}
