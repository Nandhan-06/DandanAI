variable "project_name" { type = string }
variable "region_id"    { type = string }
resource "neon_project" "this" { name = var.project_name, region_id = var.region_id }
output "connection_uri_note" { value = "Copy pooled and direct URIs from the Neon console into .env" }
