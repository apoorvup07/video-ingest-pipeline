data "aws_caller_identity" "current" {}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized" # honours the Cache-Control headers the uploader sets
}

data "aws_cloudfront_response_headers_policy" "cors" {
  name = "Managed-SimpleCORS" # lets browser players on other origins fetch segments
}

###############################################################################
# Origin bucket: private, encrypted, versioned. Only CloudFront can read it.
###############################################################################
resource "aws_s3_bucket" "origin" {
  bucket = "${var.name}-origin-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "origin" {
  bucket                  = aws_s3_bucket.origin.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "origin" {
  bucket = aws_s3_bucket.origin.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "origin" {
  bucket = aws_s3_bucket.origin.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "origin" {
  bucket = aws_s3_bucket.origin.id
  versioning_configuration {
    status = "Enabled"
  }
}

###############################################################################
# CloudFront with Origin Access Control (the successor to OAI)
###############################################################################
resource "aws_cloudfront_origin_access_control" "origin" {
  name                              = "${var.name}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "cdn" {
  enabled         = true
  comment         = "${var.name} HLS delivery"
  price_class     = var.price_class
  is_ipv6_enabled = true

  origin {
    origin_id                = "s3-origin"
    domain_name              = aws_s3_bucket.origin.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.origin.id
  }

  default_cache_behavior {
    target_origin_id           = "s3-origin"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.cors.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

data "aws_iam_policy_document" "origin" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.origin.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.cdn.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "origin" {
  bucket     = aws_s3_bucket.origin.id
  policy     = data.aws_iam_policy_document.origin.json
  depends_on = [aws_s3_bucket_public_access_block.origin]
}

###############################################################################
# Least-privilege policy for whatever runs the ingest container
###############################################################################
data "aws_iam_policy_document" "uploader" {
  statement {
    sid       = "WritePackages"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.origin.arn}/*"]
  }
  statement {
    # Needed so a HEAD on a missing key returns 404 (not 403), which the
    # idempotent uploader relies on.
    sid       = "ListForHead"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.origin.arn]
  }
}

resource "aws_iam_policy" "uploader" {
  name   = "${var.name}-uploader"
  policy = data.aws_iam_policy_document.uploader.json
}
