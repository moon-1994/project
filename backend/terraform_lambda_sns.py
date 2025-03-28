import boto3
import json
import zipfile
import os

def create_lambda_zip():
    os.makedirs("lambda_package", exist_ok=True)

    # Lambda 함수 코드 작성
    with open("lambda_package/lambda_function.py", "w", encoding="utf-8") as f:
        f.write("""
import json
import boto3
import os

SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

def format_comparison(expected, deployed):
    lines = ["🔍 환경 비교 결과 🔍\\n"]
    for key in expected:
        ev = expected[key]
        dv = deployed.get(key, "(없음)")
        result = "✅ 일치" if ev == dv else "❌ 불일치"
        lines.append(f"• {key}: 예상 = `{ev}` / 실제 = `{dv}` → {result}")
    return "\\n".join(lines)

def lambda_handler(event, context):
    try:
        if "Records" in event and "Sns" in event["Records"][0]:
            message = json.loads(event['Records'][0]['Sns']['Message'])
        else:
            message = event

        expected = message.get("expected_env", {})
        deployed = message.get("deployed_env", {})

        if not expected or not deployed:
            return {
                'statusCode': 400,
                'body': 'expected_env 또는 deployed_env 정보가 없습니다.'
            }

        result = format_comparison(expected, deployed)

        sns = boto3.client("sns")
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="✅ 배포 환경 비교 결과",
            Message=result
        )

        print("📤 메일 전송 성공")
        return {
            'statusCode': 200,
            'body': '메일 전송 성공'
        }

    except Exception as e:
        print("❗ 오류 발생:", str(e))
        return {
            'statusCode': 500,
            'body': 'Lambda 처리 중 오류 발생'
        }
""")

    # zip으로 패키징
    with zipfile.ZipFile("lambda_function.zip", "w") as zipf:
        zipf.write("lambda_package/lambda_function.py", arcname="lambda_function.py")

def deploy_lambda_sns(lambda_name, topic_name, email):
    region = "ap-northeast-2"
    iam = boto3.client("iam")
    sns = boto3.client("sns", region_name=region)
    lambda_client = boto3.client("lambda", region_name=region)
    sts = boto3.client("sts")

    account_id = sts.get_caller_identity()["Account"]
    role_name = f"{lambda_name}-role"

    # IAM Role 생성
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    try:
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy)
        )
        print("✅ IAM Role 생성 완료")
    except iam.exceptions.EntityAlreadyExistsException:
        print("⚠️ IAM Role 이미 존재")

    # IAM Role에 정책 부여
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "logs:*",
                    "sns:Publish"
                ],
                "Resource": "*"
            }
        ]
    }
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=f"{lambda_name}-policy",
        PolicyDocument=json.dumps(policy)
    )
    print("✅ 정책 연결 완료")

    # SNS Topic 생성
    topic = sns.create_topic(Name=topic_name)
    topic_arn = topic["TopicArn"]
    print(f"✅ SNS Topic 생성됨: {topic_arn}")

    # 이메일 구독 추가
    sns.subscribe(
        TopicArn=topic_arn,
        Protocol="email",
        Endpoint=email
    )
    print(f"📧 이메일 구독 전송됨: {email}")

    # Lambda 함수 생성
    with open("lambda_function.zip", "rb") as f:
        zipped_code = f.read()

    try:
        lambda_client.create_function(
            FunctionName=lambda_name,
            Runtime="python3.13",
            Role=f"arn:aws:iam::{account_id}:role/{role_name}",
            Handler="lambda_function.lambda_handler",
            Code={"ZipFile": zipped_code},
            Timeout=10,
            MemorySize=128,
            Environment={"Variables": {"SNS_TOPIC_ARN": topic_arn}},
            Publish=True,
        )
        print("✅ Lambda 함수 생성 완료")
    except lambda_client.exceptions.ResourceConflictException:
        print("⚠️ Lambda 함수가 이미 존재합니다.")

    print("📩 이메일 수신함에서 구독 확인 링크를 눌러야 메일을 받을 수 있어요!")

# 실행
if __name__ == "__main__":
    create_lambda_zip()
    deploy_lambda_sns(
        lambda_name="testlambda",
        topic_name="MESSAGE-TESTER",
        email=input("📨 이메일 주소를 입력하세요: ")
    )
