terraform {
  required_providers {
    vultr = {
      source  = "vultr/vultr"
      version = ">= 2.18.0" // Use a recent version of the Vultr provider
    }
  }
}

resource "vultr_instance" "this" {
  region        = var.region
  plan          = var.plan
  os_id         = var.os_id
  ssh_key_ids   = var.ssh_key_ids
  hostname      = var.hostname
  label         = var.label
  tags          = var.tags
  user_data     = var.user_data
  enable_ipv6   = var.enable_ipv6

  # Optional arguments not included as variables (can be added later if needed):
  # firewall_group_id = ...
  # vpc_ids = ...
  # backups = ...
  # ddos_protection = ...
  # reserved_ip_id = ...
  # activation_email = false # Default is usually fine

  lifecycle {
    # Prevent accidental replacement if only certain attributes change
    ignore_changes = [
      tags, // Often changed outside Terraform
    ]
  }
}
