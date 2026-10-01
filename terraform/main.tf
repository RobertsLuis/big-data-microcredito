terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aiven = {
      source  = "aiven/aiven"
      version = "~> 4.0"
    }
  }
}

provider "aiven" {
  api_token = var.aiven_api_token
}

# PostgreSQL Aiven - plano Free Tier (1 GB)
resource "aiven_pg" "microcredito_db" {
  project      = var.aiven_project_name
  cloud_name   = var.cloud_region
  plan         = "hobbyist"
  service_name = var.service_name

  pg_user_config {
    pg_version = "16"

    # Permite acesso externo para carga via ETL local
    ip_filter_object {
      network = "0.0.0.0/0"
    }
  }
}
