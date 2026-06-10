# infra/terraform/main.tf
# Terraform settings, AWS provider, remote state, and shared locals.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Remote state in S3 with native S3 state locking (no DynamoDB; Terraform >= 1.10).
  # The bucket name is intentionally NOT committed (it embeds the account id).
  # Provide it at init time:
  #   terraform init -backend-config="bucket=<your-state-bucket>"
  backend "s3" {
    key          = "buybox-propensity/terraform.tfstate"
    region       = "ca-central-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.additional_tags,
  )
}
