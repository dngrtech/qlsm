terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.50.0" // Use a recent version
    }
  }
}

resource "google_compute_instance" "this" {
  name         = var.instance_name
  project      = var.project_id
  zone         = var.zone
  machine_type = var.machine_type
  tags         = var.tags
  labels       = var.labels

  boot_disk {
    initialize_params {
      image = var.disk_image
      size  = var.disk_size_gb
      type  = var.disk_type
    }
    auto_delete = true // Based on your gcloud command
  }

  network_interface {
    network    = var.network
    subnetwork = var.subnetwork
    access_config {
      // Ephemeral public IP assigned by default
      network_tier = var.network_tier
    }
  }

  metadata = {
    // Add the SSH key for the specified user (root in this case)
    ssh-keys = "${var.ssh_user}:${var.ssh_public_key}"
    // Block project-wide keys as per your gcloud command
    block-project-ssh-keys = true
    // Include the startup script if content is provided
    startup-script = var.startup_script_content != "" ? var.startup_script_content : null
    // Enable OS Config agent
    enable-osconfig = "TRUE"
  }

  service_account {
    email  = var.service_account_email
    scopes = var.scopes
  }

  scheduling {
    automatic_restart   = true // Corresponds to --maintenance-policy=MIGRATE
    provisioning_model  = "STANDARD" // Based on your gcloud command
    on_host_maintenance = "MIGRATE"
  }

  shielded_instance_config {
    enable_secure_boot          = false // Based on --no-shielded-secure-boot
    enable_vtpm                 = true  // Based on --shielded-vtpm
    enable_integrity_monitoring = true  // Based on --shielded-integrity-monitoring
  }

  allow_stopping_for_update = true // Recommended for managed instances

  // reservation_affinity is implicitly "any" unless specified otherwise

  lifecycle {
    // Prevent accidental replacement if only labels or metadata change
    ignore_changes = [metadata["ssh-keys"]]
  }
}
