variable "region" {
  description = "Region for the origin bucket"
  type        = string
  default     = "eu-west-1"
}

variable "name" {
  description = "Name prefix for all resources"
  type        = string
  default     = "video-ingest"
}

variable "price_class" {
  description = "CloudFront price class (PriceClass_100 = Europe + North America edges only, cheapest)"
  type        = string
  default     = "PriceClass_100"
}
