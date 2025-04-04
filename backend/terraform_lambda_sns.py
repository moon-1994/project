import boto3
import json
import zipfile
import os

# 경로 설정
LAMBDA_FOLDER = os.path.join("backend", "lambda_package")
ZIP_PATH = os.path.join("terraform", "tfstate_compare.zip")

# 디렉토리 생성
os.makedirs(LAMBDA_FOLDER, exist_ok=True)
os.makedirs("terraform", exist_ok=True)

# Lambda 코드 작성
lambda_code_path = os.path.join(LAMBDA_FOLDER, "lambda_function.py")
with open(lambda_code_path, "w", encoding="utf-8") as f:
    f.write("""import boto3
import json
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
sns = boto3.client("sns")

SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
PRE_DEPLOY_STATE_BUCKET = os.environ["PRE_DEPLOY_STATE_BUCKET"]
POST_DEPLOY_STATE_BUCKET = os.environ["POST_DEPLOY_STATE_BUCKET"]

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
        messages.append("🆕 추가된 리소스:\\n" + "\\n".join(f"+ {k}" for k in sorted(added)))
    if removed:
        messages.append("❌ 삭제된 리소스:\\n" + "\\n".join(f"- {k}" for k in sorted(removed)))
    if changed:
        messages.append("🔁 변경된 리소스:\\n" + "\\n".join(f"* {k}" for k in sorted(changed)))
    return "\\n\\n".join(messages) if messages else "✅ 변경 사항 없음"

def lambda_handler(event, context):
    try:
        try:
            pre_obj = s3.get_object(Bucket=PRE_DEPLOY_STATE_BUCKET, Key="pre_terraform.tfstate")
            pre_state = json.loads(pre_obj["Body"].read().decode("utf-8"))
        except s3.exceptions.NoSuchKey:
            logger.warning("pre_terraform.tfstate 파일 없음. 빈 상태로 처리합니다.")
            pre_state = {}

        post_obj = s3.get_object(Bucket=POST_DEPLOY_STATE_BUCKET, Key="post_terraform.tfstate")
        post_state = json.loads(post_obj["Body"].read().decode("utf-8"))

        pre = extract_resources(pre_state)
        post = extract_resources(post_state)
        result = compare_resources(pre, post)

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="📢 Terraform 리소스 변경 사항",
            Message=result
        )
        return {"status": "done"}
    except Exception as e:
        logger.error(f"오류 발생: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Lambda 오류 발생"})
        }
""")

# zip 파일 생성
with zipfile.ZipFile(ZIP_PATH, "w") as zipf:
    zipf.write(lambda_code_path, arcname="lambda_function.py")

print(f"✅ Lambda 패키징 완료: {ZIP_PATH}")

