output "bronze_bucket_name" {
  value = aws_s3_bucket.this["bronze"].id
}

output "silver_bucket_name" {
  value = aws_s3_bucket.this["silver"].id
}

output "bucket_arns" {
  value = { for k, b in aws_s3_bucket.this : k => b.arn }
}
