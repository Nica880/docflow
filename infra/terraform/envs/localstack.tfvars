# LocalStack (free, local): `terraform apply -var-file=envs/localstack.tfvars`
use_localstack      = true
localstack_endpoint = "http://localhost:4566"
aws_region          = "us-east-1"
environment         = "local"

# Same names the app uses (BRONZE_BUCKET / SILVER_BUCKET / SQS_QUEUE_NAME).
bronze_bucket_name = "docflow-bronze"
silver_bucket_name = "docflow-silver"
queue_name         = "docflow-extract"

force_destroy_buckets = true
