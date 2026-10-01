variable "aiven_api_token" {
  description = "Token de API gerado no console Aiven (My profile → Tokens)"
  type        = string
  sensitive   = true
}

variable "aiven_project_name" {
  description = "Nome do projeto Aiven onde o serviço será criado"
  type        = string
}

variable "cloud_region" {
  description = "Região de nuvem para o serviço (padrão: Google São Paulo)"
  type        = string
  default     = "google-southamerica-east1"
}

variable "service_name" {
  description = "Nome do serviço PostgreSQL na Aiven"
  type        = string
  default     = "microcredito-pg"
}
