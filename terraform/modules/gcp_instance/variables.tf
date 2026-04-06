variable "instance_name" {
  description = "Name of the compute instance"
  type        = string
}

variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "zone" {
  description = "The GCP zone for the instance"
  type        = string
  default     = "us-west1-a" // Default zone, can be overridden
}

variable "machine_type" {
  description = "The machine type for the instance"
  type        = string
  default     = "custom-1-2048" // Based on your gcloud command
}

variable "disk_image" {
  description = "The source image for the boot disk"
  type        = string
  default     = "ubuntu-os-cloud/ubuntu-2204-jammy-v20250312" // Based on your gcloud command
}

variable "disk_size_gb" {
  description = "The size of the boot disk in GB"
  type        = number
  default     = 10 // As requested
}

variable "disk_type" {
  description = "The type of the boot disk"
  type        = string
  default     = "pd-standard" // Based on your gcloud command
}

variable "network" {
  description = "The network name"
  type        = string
  default     = "default"
}

variable "subnetwork" {
  description = "The subnetwork name"
  type        = string
  default     = "default" // Assumes default subnet in the specified network/region
}

variable "network_tier" {
  description = "The network tier (e.g., PREMIUM, STANDARD)"
  type        = string
  default     = "PREMIUM"
}

variable "service_account_email" {
  description = "The service account email for the instance"
  type        = string
  // Example: "876667503390-compute@developer.gserviceaccount.com"
  // Make this required or provide a default if applicable
}

variable "scopes" {
  description = "List of API scopes granted to the service account"
  type        = list(string)
  default = [
    "https://www.googleapis.com/auth/devstorage.read_only",
    "https://www.googleapis.com/auth/logging.write",
    "https://www.googleapis.com/auth/monitoring.write",
    "https://www.googleapis.com/auth/service.management.readonly",
    "https://www.googleapis.com/auth/servicecontrol",
    "https://www.googleapis.com/auth/trace.append",
  ]
}

variable "ssh_user" {
  description = "The username for the SSH key"
  type        = string
  default     = "root" // The startup script copies from root, so we add the key for root
}

variable "ssh_public_key" {
  description = "The public SSH key content"
  type        = string
  sensitive   = true // Mark as sensitive
}

variable "startup_script_content" {
  description = "The content of the startup script to run on boot"
  type        = string
  default     = ""
}

variable "tags" {
  description = "A list of network tags to apply to the instance"
  type        = list(string)
  default     = []
}

variable "labels" {
  description = "A map of labels to apply to the instance"
  type        = map(string)
  default = {
    // Based on your gcloud command
    "goog-ops-agent-policy" = "v2-x86-template-1-4-0"
    "goog-ec-src"           = "vm_add-tf" // Changed from gcloud to tf
  }
}
