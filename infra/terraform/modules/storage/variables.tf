variable "bronze_bucket_name" {
  description = "Bronze (raw filings) bucket name."
  type        = string
}

variable "silver_bucket_name" {
  description = "Silver (sections, facts, Parquet lake) bucket name."
  type        = string
}

variable "bronze_glacier_after_days" {
  description = "Days before bronze objects transition to GLACIER."
  type        = number
  default     = 90

  validation {
    condition     = var.bronze_glacier_after_days >= 1
    error_message = "bronze_glacier_after_days must be >= 1."
  }
}

variable "noncurrent_version_expiration_days" {
  description = "Days before non-current object versions are deleted."
  type        = number
  default     = 30
}

variable "force_destroy" {
  description = "Allow deleting non-empty buckets."
  type        = bool
  default     = false
}
