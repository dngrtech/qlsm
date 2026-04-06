output "instance_id" {
  description = "The ID of the Vultr instance."
  value       = vultr_instance.this.id
}

output "main_ip" {
  description = "The main public IPv4 address of the instance."
  value       = vultr_instance.this.main_ip
}

output "internal_ip" {
  description = "The internal (private) IPv4 address of the instance, if applicable."
  value       = vultr_instance.this.internal_ip
}

output "v6_main_ip" {
  description = "The main public IPv6 address of the instance, if IPv6 is enabled."
  value       = vultr_instance.this.v6_main_ip
}

output "hostname" {
  description = "The hostname assigned to the instance."
  value       = vultr_instance.this.hostname
}

output "label" {
  description = "The label assigned to the instance."
  value       = vultr_instance.this.label
}

output "region" {
  description = "The region where the instance was created."
  value       = vultr_instance.this.region
}

output "os" {
  description = "The operating system installed on the instance."
  value       = vultr_instance.this.os
}

output "plan" {
  description = "The plan ID the instance is subscribed to."
  value       = vultr_instance.this.plan
}

output "default_password" {
  description = "The default root password assigned by Vultr (use SSH keys for access)."
  value       = vultr_instance.this.default_password
  sensitive   = true # Mark password as sensitive
}
