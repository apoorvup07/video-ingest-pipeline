output "origin_bucket" {
  value = aws_s3_bucket.origin.bucket
}

output "cdn_domain" {
  value = aws_cloudfront_distribution.cdn.domain_name
}

output "uploader_policy_arn" {
  description = "Attach to the role the ingest container runs as (ECS task role, CI OIDC role, ...)"
  value       = aws_iam_policy.uploader.arn
}
