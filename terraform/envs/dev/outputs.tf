output "gke_cluster_name" {
  value = module.gke.cluster_name
}
output "artifact_registry_url" {
  value = module.artifact_registry.repository_url
}
output "cloudsql_connection_name" {
  value = module.cloudsql.instance_connection_name
}
output "workload_identity_provider" {
  value = module.iam_wif.workload_identity_provider
}
output "ci_service_account_email" {
  value = module.iam_wif.ci_service_account_email
}
