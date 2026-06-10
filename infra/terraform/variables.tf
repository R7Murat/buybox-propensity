# infra/terraform/variables.tf
# Input variables for the Buy Box Propensity MLOps infrastructure.
# Values without a default are required and come from terraform.tfvars
# (gitignored). See terraform.tfvars.example in the repo root.

variable "project_name" {
  description = "Project name; prefix for resource names and tags."
  type        = string
  default     = "buybox-propensity"
}

variable "environment" {
  description = "Environment label used in tags. This is an ephemeral demo."
  type        = string
  default     = "demo"
}

variable "aws_region" {
  description = "AWS region for all resources. Data is Canadian -> ca-central-1 by default."
  type        = string
  default     = "ca-central-1"
}

# ---------- ECR ----------
variable "ecr_repo_name" {
  description = "ECR repository name that holds the serving image."
  type        = string
  default     = "buybox-propensity-api"
}

# ---------- EKS ----------
variable "eks_cluster_name" {
  description = "EKS cluster name."
  type        = string
  default     = "buybox-propensity-eks"
}

variable "eks_version" {
  description = "Kubernetes version for the EKS control plane. Provisional; pinned against currently-supported EKS versions when eks.tf is written."
  type        = string
  default     = "1.31"
}

variable "node_instance_type" {
  description = "EC2 instance type for the managed node group (cost-aware demo)."
  type        = string
  default     = "t3.medium"
}

variable "node_min_size" {
  description = "Minimum nodes in the managed node group."
  type        = number
  default     = 1
}

variable "node_desired_size" {
  description = "Desired nodes at creation."
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum nodes; headroom for HPA-driven scale-out during the demo."
  type        = number
  default     = 3
}

variable "enable_nat_gateway" {
  description = "false (default, cost-aware): nodes in public subnets, egress via Internet Gateway, no NAT cost. true: private nodes + NAT Gateway (more production-like, higher cost)."
  type        = bool
  default     = false
}

variable "allowed_api_cidr" {
  description = "CIDR allowed to reach the EKS public API endpoint. Use your machine's public IP /32 (curl https://checkip.amazonaws.com). '0.0.0.0/0' is possible for a quick demo but not recommended."
  type        = string

  validation {
    condition     = can(cidrhost(var.allowed_api_cidr, 0))
    error_message = "allowed_api_cidr must be a valid CIDR block, e.g. 203.0.113.5/32."
  }
}

# ---------- CI/CD (OIDC) ----------
variable "github_repo" {
  description = "GitHub repo in 'owner/repo' form; binds the GitHub Actions OIDC trust (sub claim)."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repo))
    error_message = "github_repo must be in 'owner/repo' form, e.g. R7Murat/buybox-propensity."
  }
}

# ---------- Cost guardrails ----------
variable "budget_limit_usd" {
  description = "Monthly AWS Budgets limit (USD). Alert only, not a hard stop; small footprint + destroy is the real control."
  type        = number
  default     = 10
}

variable "budget_alert_email" {
  description = "Email that receives the AWS Budgets alert notifications."
  type        = string

  validation {
    condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.budget_alert_email))
    error_message = "budget_alert_email must be a valid email address."
  }
}

# ---------- Tagging ----------
variable "additional_tags" {
  description = "Optional extra tags merged into the common tag set (built in main.tf)."
  type        = map(string)
  default     = {}
}
