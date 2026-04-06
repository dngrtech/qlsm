variable "region" {
  description = "The Vultr region ID where the instance will be created (e.g., 'ewr', 'lax')."
  type        = string
  # No default, must be provided by the user.
}

variable "plan" {
  description = "The Vultr plan ID for the instance (e.g., 'vc2-1c-1gb')."
  type        = string
  # No default, must be provided by the user.
}

variable "ssh_key_ids" {
  description = "A list of Vultr SSH Key IDs to associate with the instance."
  type        = list(string)
  # No default, must be provided by the user. Example: ["4dc4fbe7-ab76-466b-9c0e-06178cafba4c"]
}

variable "os_id" {
  description = "The Vultr OS ID to install on the instance."
  type        = number
  default     = 2139 # Default to Debian 12 Bookworm x64
}

variable "hostname" {
  description = "The hostname to assign to the server."
  type        = string
  default     = null
}

variable "label" {
  description = "A label for the server visible in the Vultr control panel."
  type        = string
  default     = null
}

variable "tags" {
  description = "A list of tags to apply to the instance."
  type        = list(string)
  default     = []
}

variable "user_data" {
  description = "User data script content (e.g., cloud-init) to run on first boot."
  type        = string
  default     = null
}

variable "enable_ipv6" {
  description = "Enable IPv6 networking for the instance."
  type        = bool
  default     = false
}
