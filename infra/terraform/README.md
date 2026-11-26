# DocFlow infrastructure (Terraform)

The same configuration targets **LocalStack** (free, applied locally) and **real AWS**
(`validate`/`plan` only - never applied, so it costs nothing).

| Module | Resources |
|---|---|
| `modules/storage` | `docflow-bronze` + `docflow-silver` S3 buckets: versioning, SSE-S3 (AES256, bucket key), public access block, BucketOwnerEnforced ownership, lifecycle (bronze -> `GLACIER` after 90 days, non-current versions expire after 30 days, abort stale multipart uploads) |
| `modules/queue` | `docflow-extract` SQS queue (visibility timeout 900 s, SSE) + `docflow-extract-dlq` dead-letter queue (redrive after 3 receives, 14-day retention, redrive-allow policy) |

`providers.tf` switches on `var.use_localstack`:

- `true` (default): all service endpoints -> `var.localstack_endpoint`, dummy credentials,
  `skip_credentials_validation`, `skip_requesting_account_id`, `s3_use_path_style`.
- `false`: the standard AWS provider (credentials from the normal AWS chain).

## LocalStack

```sh
docker compose up -d localstack          # or `make up`; LocalStack runs SERVICES=sqs,s3
cd infra/terraform
terraform init
terraform apply -var-file=envs/localstack.tfvars
terraform output app_env
```

(`make tf-apply-local` does the same.)

Notes:

- The app itself stores objects in **MinIO**; LocalStack S3 is only the Terraform target, to
  prove the bucket configuration applies cleanly against an S3 API.
- `docflow init-db` (the compose `migrate` service) also creates the queue + DLQ imperatively
  (`core/queue.py`, same names and redrive settings) so the stack works without Terraform. If the
  queues already exist with different attributes, either apply Terraform on a fresh LocalStack
  (`docker compose rm -sf localstack && docker compose up -d localstack`) or adopt them:
  `terraform import -var-file=envs/localstack.tfvars module.queue.aws_sqs_queue.this http://localhost:4566/000000000000/docflow-extract`.

## Real AWS (validate only)

```sh
cd infra/terraform
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
# optional, needs AWS credentials, creates nothing:
# terraform plan -var-file=envs/aws.tfvars
```

`envs/aws.tfvars` uses placeholder bucket names (S3 names are global) - change them before a plan.
There is no remote backend configured on purpose: nothing is ever applied to AWS.
`make tf-validate` runs fmt + init + validate; CI runs the same.

`.terraform.lock.hcl` is committed (hashes for linux, darwin and windows) so every machine and CI
resolve the same AWS provider build.
