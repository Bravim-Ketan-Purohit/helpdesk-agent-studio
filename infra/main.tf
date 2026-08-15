# Terraform — infrastructure surrounding the cluster.
# KMS CMK, IAM roles for service accounts, S3 for audit-log archival, VPC.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "cluster_name" {
  type    = string
  default = "helpdesk-studio"
}

# --- KMS ---

resource "aws_kms_key" "token_encryption" {
  description             = "Helpdesk Studio - OAuth token envelope encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = {
    Project     = "helpdesk-agent-studio"
    Environment = var.environment
    Purpose     = "token-encryption"
  }
}

resource "aws_kms_alias" "token_encryption" {
  name          = "alias/helpdesk-studio-${var.environment}"
  target_key_id = aws_kms_key.token_encryption.id
}

# --- S3 for audit log archival ---

resource "aws_s3_bucket" "audit_archive" {
  bucket = "helpdesk-studio-audit-${var.environment}-${data.aws_caller_identity.current.account_id}"

  tags = {
    Project     = "helpdesk-agent-studio"
    Environment = var.environment
    Purpose     = "audit-log-archival"
  }
}

resource "aws_s3_bucket_versioning" "audit_archive" {
  bucket = aws_s3_bucket.audit_archive.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_archive" {
  bucket = aws_s3_bucket.audit_archive.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.token_encryption.arn
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audit_archive" {
  bucket = aws_s3_bucket.audit_archive.id

  rule {
    id     = "archive-old-logs"
    status = "Enabled"
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }
}

# --- IAM Roles for Kubernetes Service Accounts (IRSA) ---

# Agent role — read-only, KMS decrypt only
resource "aws_iam_role" "agent" {
  name = "helpdesk-studio-agent-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${var.cluster_name}"
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${var.cluster_name}:sub" = "system:serviceaccount:helpdesk:agent"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "agent_kms" {
  name = "kms-decrypt"
  role = aws_iam_role.agent.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "kms:Decrypt",
        "kms:DescribeKey",
      ]
      Resource = [aws_kms_key.token_encryption.arn]
    }]
  })
}

# Executor role — read/write, full KMS access
resource "aws_iam_role" "executor" {
  name = "helpdesk-studio-executor-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${var.cluster_name}"
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${var.cluster_name}:sub" = "system:serviceaccount:helpdesk:executor"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "executor_kms" {
  name = "kms-full"
  role = aws_iam_role.executor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "kms:Decrypt",
        "kms:Encrypt",
        "kms:GenerateDataKey",
        "kms:DescribeKey",
      ]
      Resource = [aws_kms_key.token_encryption.arn]
    }]
  })
}

resource "aws_iam_role_policy" "executor_s3" {
  name = "s3-audit-write"
  role = aws_iam_role.executor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:PutObject",
        "s3:GetObject",
      ]
      Resource = ["${aws_s3_bucket.audit_archive.arn}/*"]
    }]
  })
}

# --- Data sources ---

data "aws_caller_identity" "current" {}

# --- Outputs ---

output "kms_key_arn" {
  value = aws_kms_key.token_encryption.arn
}

output "kms_key_alias" {
  value = aws_kms_alias.token_encryption.name
}

output "audit_bucket_name" {
  value = aws_s3_bucket.audit_archive.id
}

output "agent_role_arn" {
  value = aws_iam_role.agent.arn
}

output "executor_role_arn" {
  value = aws_iam_role.executor.arn
}
