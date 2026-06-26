output "instance_id" {
  value       = aws_instance.sara.id
  description = "EC2 instance id of the experiment host."
}

output "public_ip" {
  value       = aws_instance.sara.public_ip
  description = "Public IP of the experiment host."
}

output "public_dns" {
  value       = aws_instance.sara.public_dns
  description = "Public DNS name of the experiment host."
}

output "ami_id" {
  value       = local.ami_id
  description = "AMI the instance was launched from (its hash is the baked-in apparatus/version baseline)."
}

output "ssh_command" {
  value       = "ssh ubuntu@${aws_instance.sara.public_ip}   # then: sudo -iu experimenter; cd sara"
  description = "Convenience SSH command. Log in as ubuntu, switch to the experimenter user."
}
