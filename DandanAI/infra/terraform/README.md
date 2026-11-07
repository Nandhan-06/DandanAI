# Terraform (prepared, NOT applied)
Modules are skeletons for a future deployment. Nothing here is applied automatically and no paid resource is created
unless you run `terraform apply` yourself after reviewing the plan. `terraform validate` has NOT been run in the build environment.
Neon is provisioned through the Neon console or the `kislerdm/neon` provider (see `neon/`); the database is never replaced by a cloud-native one.
