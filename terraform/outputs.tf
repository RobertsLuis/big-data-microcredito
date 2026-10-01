output "service_uri" {
  description = "URI de conexão completa do PostgreSQL (usar como DATABASE_URL no .env)"
  value       = aiven_pg.microcredito_db.service_uri
  sensitive   = true
}

output "host" {
  description = "Host do banco de dados"
  value       = aiven_pg.microcredito_db.service_host
}

output "port" {
  description = "Porta do banco de dados"
  value       = aiven_pg.microcredito_db.service_port
}

output "database_name" {
  description = "Nome do banco padrão"
  value       = "defaultdb"
}
