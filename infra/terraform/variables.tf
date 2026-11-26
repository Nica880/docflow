variable "use_localstack" {
  description = "Target LocalStack (true, free/local) or real AWS (false, `validate`/`plan` only)."
  type        = bool
  default     = true
}

variable "localstack_endpoint" {
  description = "LocalStack edge endpoint used for every AWS service when use_localstack = true."
  type        = string
  default     = "http://localhost:4566"
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name, used in tags and (for real AWS) bucket name suffixes."
  type        = string
  default     = "local"
}

variable "bronze_bucket_name" {
  description = "Bucket for raw filings (bronze). Must be globally unique on real AWS."
  type        = string
  default     = "docflow-bronze"
}

variable "silver_bucket_name" {
  description = "Bucket for sectioned text, extracted facts and the Parquet lake (silver)."
  type        = string
  default     = "docflow-silver"
}

variable "bronze_glacier_after_days" {
  description = "Transition bronze objects to GLACIER after this many days."
  type        = number
  default     = 90
}

variable "noncurrent_version_expiration_days" {
  description = "Delete non-current object versions after this many days."
  type        = number
  default     = 30
}

variable "queue_name" {
  description = "SQS extraction queue name (SQS_QUEUE_NAME in the app)."
  type        = string
  default     = "docflow-extract"
}

variable "visibility_timeout_seconds" {
  description = "Must exceed the slowest LLM extraction of one filing (incl. repair retries)."
  type        = number
  default     = 900
}

variable "max_receive_count" {
  description = "Deliveries before a message is moved to the dead-letter queue."
  type        = number
  default     = 3
}

variable "force_destroy_buckets" {
  description = "Allow `terraform destroy` to delete non-empty buckets (handy on LocalStack)."
  type        = bool
  default     = false
}

variable "extra_tags" {
  description = "Additional tags applied to every resource."
  type        = map(string)
  default     = {}
}
