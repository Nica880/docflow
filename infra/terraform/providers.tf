terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

# One provider block for both targets:
# - use_localstack = true  -> every service endpoint points at LocalStack, fake credentials,
#                             no account lookups, path-style S3 URLs.
# - use_localstack = false -> standard AWS provider (credentials from the usual AWS chain).
provider "aws" {
  region = var.aws_region

  access_key = var.use_localstack ? "test" : null
  secret_key = var.use_localstack ? "test" : null

  skip_credentials_validation = var.use_localstack
  skip_requesting_account_id  = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  s3_use_path_style           = var.use_localstack

  dynamic "endpoints" {
    for_each = var.use_localstack ? [var.localstack_endpoint] : []
    content {
      s3  = endpoints.value
      sqs = endpoints.value
      sts = endpoints.value
      iam = endpoints.value
    }
  }

  default_tags {
    tags = merge(
      {
        project     = "docflow"
        environment = var.environment
        managed_by  = "terraform"
      },
      var.extra_tags,
    )
  }
}
