provider "aws" {
  region = "ap-northeast-2"
}

# ✅ 유니크한 이름을 위한 project_name 변수
variable "project_name" {
  description = "프로젝트 이름 또는 환경 구분용 태그 (예: tf-main-123)"
  type        = string
}

# ✅ Null 리소스 (GitHub Actions 테스트 메시지용)
resource "null_resource" "example" {
  provisioner "local-exec" {
    command = "echo '✅ Terraform GitHub Actions 테스트 완료!'"
  }
}

# ✅ Lambda 호출을 위한 IAM 역할
resource "aws_iam_role" "lambda_execution_role" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# ✅ Lambda 실행을 위한 정책
resource "aws_iam_policy" "lambda_execution_policy" {
  name        = "${var.project_name}-lambda-policy"
  description = "Policy for Lambda to publish to SNS and allow function invocation"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sns:Publish",
          "lambda:InvokeFunction"
        ]
        Resource = data.aws_sns_topic.existing_topic.arn
      }
    ]
  })
}

# ✅ 정책과 역할 연결
resource "aws_iam_role_policy_attachment" "lambda_policy_attach" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = aws_iam_policy.lambda_execution_policy.arn
}

# ✅ SNS Topic (존재하는 리소스)
data "aws_sns_topic" "existing_topic" {
  name = "MESSAGE-TESTER"
}

# ✅ Lambda 함수 (존재하는 리소스)
data "aws_lambda_function" "existing_lambda" {
  function_name = "testlambda"
}

# ✅ Lambda 함수에 SNS 권한 부여
resource "aws_lambda_permission" "allow_sns" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = data.aws_lambda_function.existing_lambda.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = data.aws_sns_topic.existing_topic.arn
}

# ✅ SNS → Lambda 구독 연결
resource "aws_sns_topic_subscription" "lambda_sns_subscription" {
  topic_arn = data.aws_sns_topic.existing_topic.arn
  protocol  = "lambda"
  endpoint  = data.aws_lambda_function.existing_lambda.arn
}