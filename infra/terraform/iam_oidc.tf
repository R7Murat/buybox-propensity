# infra/terraform/iam_oidc.tf
# GitHub Actions OIDC provider + IAM role for keyless CI/CD.
# No static AWS keys are stored in GitHub — the workflow assumes this role
# via short-lived OIDC tokens scoped to this specific repository.

# ─────────────────────────────────────────────
# GitHub Actions OIDC identity provider
# ─────────────────────────────────────────────
data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]
}

# ─────────────────────────────────────────────
# IAM role assumed by GitHub Actions
# ─────────────────────────────────────────────
resource "aws_iam_role" "github_actions" {
  name = "${var.project_name}-github-actions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          # Scoped to this repo, any branch/tag — tighten to ref:refs/heads/main if desired
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:*"
        }
      }
    }]
  })
}

# ─── Permissions: ECR push + EKS deploy ───
resource "aws_iam_role_policy" "github_actions_ecr" {
  name = "ecr-push"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
        ]
        Resource = aws_ecr_repository.api.arn
      },
    ]
  })
}

resource "aws_iam_role_policy" "github_actions_eks" {
  name = "eks-deploy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "eks:DescribeCluster",
        "eks:ListClusters",
      ]
      Resource = aws_eks_cluster.main.arn
    }]
  })
}

# ─────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────
output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions to assume via OIDC."
  value       = aws_iam_role.github_actions.arn
}
