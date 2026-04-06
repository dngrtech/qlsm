terraform {
  required_providers {
    vultr = {
      source  = "vultr/vultr"
      version = ">= 2.18.0" // Match the version constraint in the module
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = ">= 2.1"
    }
  }
  # API key is expected to be set via the VULTR_API_KEY environment variable
}

# -----------------------------------------------------------------------------
# Input Variables
# These will be passed per workspace/instance via -var flags
# -----------------------------------------------------------------------------
variable "instance_name" {
  description = "The name/label for the Vultr instance and associated resources. Used for workspace identification."
  type        = string
}

variable "vultr_region" {
  description = "The Vultr region ID where the instance will be created."
  type        = string
}

variable "vultr_plan" {
  description = "The Vultr plan ID for the instance."
  type        = string
}

variable "instance_tags" {
  description = "A list of tags to apply to the Vultr instance."
  type        = list(string)
  default     = [] # Optional, provide a default if desired
}

# -----------------------------------------------------------------------------
# SSH Key Management
# -----------------------------------------------------------------------------
# Generate an SSH key pair for this instance/workspace
resource "tls_private_key" "instance_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# Upload the public key to Vultr
resource "vultr_ssh_key" "instance_ssh_key" {
  name    = "${var.instance_name}-key" # Name the key in Vultr using the input variable
  ssh_key = tls_private_key.instance_key.public_key_openssh
}

# Save the private key locally for Ansible use
resource "local_file" "private_key_pem" {
  content  = tls_private_key.instance_key.private_key_pem
  filename = "../ssh-keys/${var.instance_name}_id_rsa" # Save in project_root/ssh-keys/ using the input variable
  file_permission = "0600" # Set secure permissions

  # Ensure the ssh-keys directory exists (relative path from this main.tf)
  provisioner "local-exec" {
    command = "mkdir -p ../ssh-keys"
  }
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------
# Look up the OS ID for Debian 12 x64 dynamically
data "vultr_os" "debian12" {
  filter {
    name   = "name"
    values = ["Debian 12 x64 (bookworm)"] # Exact name from Vultr API
  }
  filter {
    name   = "family"
    values = ["debian"]
  }
  filter {
    name   = "arch"
    values = ["x64"]
  }
}

# -----------------------------------------------------------------------------
# Resources
# -----------------------------------------------------------------------------
# Define the instance using the module
module "vultr_host_instance" {
  source = "../modules/vultr_instance" # Relative path to the module directory

  # --- Required Variables ---
  region      = var.vultr_region
  plan        = var.vultr_plan
  os_id       = data.vultr_os.debian12.id # Use the dynamically found OS ID
  ssh_key_ids = [vultr_ssh_key.instance_ssh_key.id] # Use the dynamically created SSH key ID

  # --- Optional Variables ---
  label     = var.instance_name
  hostname  = var.instance_name
  tags      = var.instance_tags
  # Read startup script content relative to the project root
  user_data = file("${path.root}/../startup_scripts/ansible_client_setup.sh") # Hardcoded path
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

# Output the server's main IP address
output "main_ip" {
  description = "Public IPv4 address of the instance."
  value       = module.vultr_host_instance.main_ip
}

# Output the server's ID
output "instance_id" {
  description = "ID of the instance."
  value       = module.vultr_host_instance.instance_id
}

# Output the default password (use SSH key for access)
output "default_password" {
  description = "Default root password for the instance (use SSH key for access)."
  value       = module.vultr_host_instance.default_password
  sensitive   = true
}

# Output the path to the generated private key
output "private_key_path" {
  description = "Absolute path to the generated private SSH key file."
  value       = abspath(local_file.private_key_pem.filename)
}


# -----------------------------------------------------------------------------
# Ansible Inventory File Generation (Per Instance/Workspace)
# -----------------------------------------------------------------------------
resource "local_file" "ansible_inventory_snippet" {
  # Path to the generated inventory file, using an absolute path relative to the project root
  # Creates a unique file per instance name
  filename = abspath("${path.root}/../../ansible/inventory/${var.instance_name}_vultr_host.yml")

  # Ensure the target directory exists before writing the file
  # Path relative to this main.tf file
  provisioner "local-exec" {
    command = "mkdir -p ../ansible/inventory"
  }

  # Render the template file
  # Template path is relative to this main.tf file
  content = templatefile("${path.module}/../templates/vultr_hosts.yml.tftpl", {
    instance_name    = var.instance_name
    instance_ip      = module.vultr_host_instance.main_ip
    # Use abspath() for the key path to ensure correctness
    private_key_path = abspath(local_file.private_key_pem.filename)
  })
}
