terraform {
  required_version = ">= 1.6"
  required_providers { neon = { source = "kislerdm/neon", version = "~> 0.6" } }
}
variable "enable_neon_project" { type = bool, default = false } # safety: nothing is created unless explicitly enabled
variable "neon_api_key"        { type = string, sensitive = true, default = "" }
variable "project_name"        { type = string, default = "dandanai-ai" }
variable "region_id"           { type = string, default = "aws-ap-southeast-1" }
provider "neon" { api_key = var.neon_api_key }
module "neon" {
  count        = var.enable_neon_project ? 1 : 0
  source       = "./modules/neon"
  project_name = var.project_name
  region_id    = var.region_id
}
# modules/backend_service and modules/frontend_service are intentionally empty placeholders:
# add your container platform (Cloud Run / ECS / Fly / Render) here after choosing a host and approving cost.
