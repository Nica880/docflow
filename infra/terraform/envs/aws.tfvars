# Real AWS: used for `terraform validate` / `terraform plan` only - never applied (no cost).
use_localstack = false
aws_region     = "eu-central-1"
environment    = "prod"

# S3 bucket names are global: replace the suffix with something unique before any plan.
bronze_bucket_name = "docflow-bronze-change-me"
silver_bucket_name = "docflow-silver-change-me"
queue_name         = "docflow-extract"

force_destroy_buckets = false
