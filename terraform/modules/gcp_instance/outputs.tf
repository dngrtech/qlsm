output "instance_id" {
  description = "The ID of the instance"
  value       = google_compute_instance.this.id
}

output "instance_name" {
  description = "The name of the instance"
  value       = google_compute_instance.this.name
}

output "instance_public_ip" {
  description = "The public IP address of the instance"
  value       = google_compute_instance.this.network_interface[0].access_config[0].nat_ip
}

output "instance_private_ip" {
  description = "The private IP address of the instance"
  value       = google_compute_instance.this.network_interface[0].network_ip
}
