import boto3
import json
import os
import logging
from botocore.exceptions import ClientError

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger()

# 환경 변수
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
PRE_DEPLOY_STATE_BUCKET = os.environ.get("PRE_DEPLOY_STATE_BUCKET", "")
POST_DEPLOY_STATE_BUCKET = os.environ.get("POST_DEPLOY_STATE_BUCKET", "")

# AWS 클라이언트
s3 = boto3.client("s3")
sns = boto3.client("sns")

def extract_resources(state):
    resources = {}
    for res in state.get("resources", []):
        res_key = f"{res['type']}.{res['name']}"
        attr = res.get("instances", [{}])[0].get("attributes", {})
        resources[res_key] = attr
    return resources

def compare_resources(pre, post):
    pre_keys = set(pre.keys())
    post_keys = set(post.keys())
    added = post_keys - pre_keys
    removed = pre_keys - post_keys
    changed = []

    for key in pre_keys & post_keys:
        if pre[key] != post[key]:
            changed.append(key)

    messages = []
    if added:
        messages.append("\n🆕 추가된 리소스:")
        messages.extend(f"  + {k}" for k in sorted(added))
    if removed:
        messages.append("\n❌ 삭제된 리소스:")
        messages.extend(f"  - {k}" for k in sorted(removed))
    for key in sorted(changed):
        pre_attr = pre[key]
        post_attr = post[key]
        diffs = [f"    • {k}: '{pre_attr.get(k)}' → '{post_attr.get(k)}'"
                 for k in set(pre_attr) | set(post_attr) if pre_attr.get(k) != post_attr.get(k)]
        if diffs:
            messages.append(f"\n🔁 변경된 리소스: {key}")
            messages.extend(diffs)

    return "\n".join(messages) if messages else "✅ 리소스 구성 변경 없음"

def lambda_handler(event, context):
    try:
        # pre 상태 로드
        try:
            pre_obj = s3.get_object(Bucket=PRE_DEPLOY_STATE_BUCKET, Key="pre_terraform.tfstate")
            pre_state = json.loads(pre_obj["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning(f"⚠️ pre_terraform.tfstate 파일이 {PRE_DEPLOY_STATE_BUCKET}에 없습니다. 빈 상태로 간주합니다.")
                pre_state = {"version": 4, "terraform_version": "1.5.7", "resources": []}
            else:
                raise

        # post 상태 로드
        try:
            post_obj = s3.get_object(Bucket=POST_DEPLOY_STATE_BUCKET, Key="post_terraform.tfstate")
            post_state = json.loads(post_obj["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning(f"⚠️ post_terraform.tfstate 파일이 {POST_DEPLOY_STATE_BUCKET}에 없습니다. 빈 상태로 간주합니다.")
                post_state = {"version": 4, "terraform_version": "1.5.7", "resources": []}
            else:
                raise

        pre = extract_resources(pre_state)
        post = extract_resources(post_state)
        result = compare_resources(pre, post)

        message = f"""
=================== 🔍 Terraform 상태 비교 결과 🔍 ===================

📁 [Pre-State 버킷]: {PRE_DEPLOY_STATE_BUCKET}
📁 [Post-State 버킷]: {POST_DEPLOY_STATE_BUCKET}

📊 [리소스 비교 결과 요약]
{result}

================================================================
"""

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="📣 Terraform 리소스 상태 비교 결과 (tfstate 기반)",
            Message=message
        )
        logger.info("✅ 비교 결과 SNS 전송 완료")
        return {"status": "done", "message": "비교 완료 및 알림 전송됨"}

    except Exception as e:
        error_message = f"❌ 오류 발생: {str(e)}"
        logger.error(error_message)

        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject="⚠️ Terraform 상태 비교 중 오류 발생",
                Message=error_message
            )
        except Exception as sns_error:
            logger.error(f"SNS 메시지 전송 실패: {str(sns_error)}")

        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Lambda 함수 실행 중 오류 발생", "error": str(e)})
        }