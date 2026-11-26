output "bronze_bucket" {
  description = "Bronze bucket name (BRONZE_BUCKET)."
  value       = module.storage.bronze_bucket_name
}

output "silver_bucket" {
  description = "Silver bucket name (SILVER_BUCKET)."
  value       = module.storage.silver_bucket_name
}

output "extraction_queue_url" {
  description = "SQS extraction queue URL."
  value       = module.queue.queue_url
}

output "extraction_queue_arn" {
  value = module.queue.queue_arn
}

output "dead_letter_queue_url" {
  description = "Messages that failed max_receive_count times end up here."
  value       = module.queue.dlq_url
}

output "app_env" {
  description = "Environment variables for the DocFlow app."
  value = {
    BRONZE_BUCKET  = module.storage.bronze_bucket_name
    SILVER_BUCKET  = module.storage.silver_bucket_name
    SQS_QUEUE_NAME = module.queue.queue_name
  }
}
