terraform {
  backend "s3" {
    bucket         = "terraform-moon1994" # 너가 만든 S3 버킷 이름
    key            = "global/s3/terraform.tfstate"
    region         = "ap-northeast-2"
    dynamodb_table = "terraform-lock"
    encrypt        = true
  }
}
