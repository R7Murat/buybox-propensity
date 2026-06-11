# infra/terraform/eks.tf
# VPC + EKS cluster + managed node group.
# Design: public subnets only (no NAT), IGW egress, cost-aware ephemeral demo.
# Production note: private subnets + NAT/VPC endpoints would be standard.

# ─────────────────────────────────────────────
# Data: available AZs in the target region
# ─────────────────────────────────────────────
data "aws_availability_zones" "available" {
  state = "available"
}

# ─────────────────────────────────────────────
# VPC
# ─────────────────────────────────────────────
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.project_name}-vpc" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.project_name}-igw" }
}

# Two public subnets across two AZs (EKS control plane requires >= 2 AZs).
resource "aws_subnet" "public" {
  count = 2

  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index) # 10.0.0.0/24, 10.0.1.0/24
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true # nodes get public IPs → egress via IGW, no NAT cost

  tags = {
    Name                                          = "${var.project_name}-public-${count.index}"
    "kubernetes.io/role/elb"                       = "1"
    "kubernetes.io/cluster/${var.eks_cluster_name}" = "shared"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.project_name}-public-rt" }
}

resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ─────────────────────────────────────────────
# IAM: EKS cluster role
# ─────────────────────────────────────────────
resource "aws_iam_role" "eks_cluster" {
  name = "${var.project_name}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# ─────────────────────────────────────────────
# EKS cluster
# ─────────────────────────────────────────────
resource "aws_eks_cluster" "main" {
  name     = var.eks_cluster_name
  version  = var.eks_version
  role_arn = aws_iam_role.eks_cluster.arn

  vpc_config {
    subnet_ids              = aws_subnet.public[*].id
    endpoint_public_access  = true
    endpoint_private_access = true          # nodes join via private endpoint within VPC
    public_access_cidrs     = [var.allowed_api_cidr]
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
}

# ─────────────────────────────────────────────
# IAM: node group role
# ─────────────────────────────────────────────
resource "aws_iam_role" "eks_nodes" {
  name = "${var.project_name}-eks-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Required managed policies for EKS worker nodes
resource "aws_iam_role_policy_attachment" "node_worker" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "node_cni" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "node_ecr" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# ─────────────────────────────────────────────
# EKS managed node group
# ─────────────────────────────────────────────
resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project_name}-nodes"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.public[*].id

  instance_types = [var.node_instance_type]
  capacity_type  = "ON_DEMAND"

  scaling_config {
    min_size     = var.node_min_size
    desired_size = var.node_desired_size
    max_size     = var.node_max_size
  }

  update_config {
    max_unavailable = 1 # rolling update: one node at a time
  }

  depends_on = [
    aws_iam_role_policy_attachment.node_worker,
    aws_iam_role_policy_attachment.node_cni,
    aws_iam_role_policy_attachment.node_ecr,
  ]
}

# ─────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────
output "eks_cluster_name" {
  description = "EKS cluster name (used by kubectl and CI/CD)."
  value       = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  description = "EKS API server endpoint."
  value       = aws_eks_cluster.main.endpoint
}

output "eks_cluster_ca" {
  description = "Base64-encoded cluster CA certificate."
  value       = aws_eks_cluster.main.certificate_authority[0].data
  sensitive   = true
}

output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.main.id
}
