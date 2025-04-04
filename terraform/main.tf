resource "aws_iam_role" "lambda_role" {
  name = "tf-lambda-common-role-${var.project_name}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "tf-lambda-common-policy-${var.project_name}"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "s3:ListBucket"
        ],
        Resource = [
          "arn:aws:s3:::${var.pre_deploy_state_bucket}",
          "arn:aws:s3:::${var.post_deploy_state_bucket}"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject"
        ],
        Resource = [
          "arn:aws:s3:::${var.pre_deploy_state_bucket}/*",
          "arn:aws:s3:::${var.post_deploy_state_bucket}/*"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "sns:Publish"
        ],
        Resource = var.sns_topic_arn
      }
    ]
  })
}

resource "aws_lambda_function" "tfstate_compare" {
  function_name = "tfstate-compare-lambda-${var.project_name}"
  role          = aws_iam_role.lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.9"
  timeout       = 10
  filename      = "tfstate_compare.zip"

  environment {
    variables = {
      SNS_TOPIC_ARN            = var.sns_topic_arn
      PRE_DEPLOY_STATE_BUCKET  = var.pre_deploy_state_bucket
      POST_DEPLOY_STATE_BUCKET = var.post_deploy_state_bucket
    }
  }
}

resource "null_resource" "trigger_tfstate_compare" {
  provisioner "local-exec" {
    command = <<EOT
aws lambda invoke \
  --function-name ${aws_lambda_function.tfstate_compare.function_name} \
  --invocation-type Event \
  --region ap-northeast-2 \
  --cli-binary-format raw-in-base64-out \
  --payload '{}' \
  lambda_response.json
EOT
  }

  depends_on = [aws_lambda_function.tfstate_compare]
}