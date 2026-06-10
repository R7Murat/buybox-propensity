# infra/terraform/ecr.tf
# Amazon ECR repository for the Buy Box Propensity serving image.

resource "aws_ecr_repository" "api" {
  name                 = var.ecr_repo_name
  image_tag_mutability = "IMMUTABLE"   # each CI build → unique tag; no silent overwrites
  force_delete         = true          # demo teardown: allow destroy even if images exist

  image_scanning_configuration {
    scan_on_push = true                # free Clair scan on every push — vulnerability signal
  }
}

# Lifecycle policy: keep only the 5 most recent tagged images.
# Prevents unbounded storage cost during iterative CI builds.
resource "aws_ecr_lifecycle_policy" "api_cleanup" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the 5 most recent images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# --- Outputs consumed by CI/CD and other modules ---
output "ecr_repository_url" {
  description = "Full ECR repository URL (used in docker push and k8s deployment)."
  value       = aws_ecr_repository.api.repository_url
}

output "ecr_repository_arn" {
  description = "ECR repository ARN (used in IAM policies)."
  value       = aws_ecr_repository.api.arn
}
