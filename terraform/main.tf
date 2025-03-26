provider "aws" {
  region = var.region
}

resource "null_resource" "example" {
  provisioner "local-exec" {
    command = "echo '✅ Terraform GitHub Actions 테스트 완료!'"
  }
}
