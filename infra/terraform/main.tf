module "storage" {
  source = "./modules/storage"

  bronze_bucket_name                 = var.bronze_bucket_name
  silver_bucket_name                 = var.silver_bucket_name
  bronze_glacier_after_days          = var.bronze_glacier_after_days
  noncurrent_version_expiration_days = var.noncurrent_version_expiration_days
  force_destroy                      = var.force_destroy_buckets
}

module "queue" {
  source = "./modules/queue"

  queue_name                 = var.queue_name
  visibility_timeout_seconds = var.visibility_timeout_seconds
  max_receive_count          = var.max_receive_count
}
