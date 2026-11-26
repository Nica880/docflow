variable "queue_name" {
  description = "Extraction queue name; the DLQ is \"<queue_name>-dlq\" (same convention as core/queue.py)."
  type        = string
}

variable "visibility_timeout_seconds" {
  description = "Visibility timeout; must exceed one filing's extraction time."
  type        = number
  default     = 900

  validation {
    condition     = var.visibility_timeout_seconds >= 0 && var.visibility_timeout_seconds <= 43200
    error_message = "visibility_timeout_seconds must be between 0 and 43200."
  }
}

variable "max_receive_count" {
  description = "Receives before a message is moved to the DLQ."
  type        = number
  default     = 3
}

variable "message_retention_seconds" {
  description = "Retention for the main queue."
  type        = number
  default     = 345600 # 4 days
}
