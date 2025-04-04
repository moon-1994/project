variable "project_name" {
  type        = string
  description = "리소스 이름 접두사"
}

variable "pre_deploy_state_bucket" {
  type        = string
  description = "S3 버킷 이름 (pre 상태)"
}

variable "post_deploy_state_bucket" {
  type        = string
  description = "S3 버킷 이름 (post 상태)"
}

variable "sns_topic_arn" {
  type        = string
  description = "SNS 알림 수신 토픽 ARN"
}
