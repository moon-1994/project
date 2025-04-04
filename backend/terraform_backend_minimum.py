import boto3
import json
import re
import time
from datetime import datetime
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TerraformBackendManager:
    def __init__(self, region, bucket_name, ddb_table="terraform-lock"):
        if not self._validate_region(region):
            raise ValueError(f"유효하지 않은 AWS 리전: {region}")
        if not self._validate_bucket_name(bucket_name):
            raise ValueError(f"유효하지 않은 S3 버킷 이름: {bucket_name}")
        if not self._validate_ddb_table_name(ddb_table):
            raise ValueError(f"유효하지 않은 DynamoDB 테이블 이름: {ddb_table}")

        self.region = region
        self.bucket_name = bucket_name
        self.ddb_table = ddb_table

        try:
            self.s3_client = boto3.client("s3", region_name=region)
            self.dynamodb = boto3.client("dynamodb", region_name=region)
            self.iam = boto3.client("iam", region_name=region)
            self.sts = boto3.client("sts", region_name=region)
        except Exception as e:
            logger.error(f"AWS 클라이언트 초기화 실패: {str(e)}")
            raise

    def _validate_region(self, region):
        valid_regions = boto3.session.Session().get_available_regions('s3')
        return region in valid_regions

    def _validate_bucket_name(self, bucket_name):
        pattern = r'^[a-z0-9][a-z0-9\.-]{1,61}[a-z0-9]$'
        return bool(re.match(pattern, bucket_name))

    def _validate_ddb_table_name(self, table_name):
        pattern = r'^[a-zA-Z0-9_\.-]{3,255}$'
        return bool(re.match(pattern, table_name))

    def _validate_github_repo(self, repo_owner, repo_name):
        owner_pattern = r'^[a-zA-Z0-9][-a-zA-Z0-9]{0,38}$'
        repo_pattern = r'^[a-zA-Z0-9_.-]{1,100}$'
        return bool(re.match(owner_pattern, repo_owner) and re.match(repo_pattern, repo_name))

    def get_account_id(self):
        try:
            return self.sts.get_caller_identity()["Account"]
        except Exception as e:
            logger.error(f"계정 ID 조회 실패: {str(e)}")
            raise

    def wait_for_resource(self, resource_type, resource_name, status_method, expected_status):
        max_retries = 10
        for i in range(max_retries):
            try:
                status = getattr(self, status_method)(resource_name)
                if status == expected_status:
                    return True
                logger.info(f"{resource_type} {resource_name} 준비 대기 중... ({i+1}/{max_retries})")
                time.sleep(2)
            except Exception as e:
                logger.warning(f"{resource_type} 상태 확인 실패: {str(e)}")
        logger.error(f"{resource_type} {resource_name}가 준비되지 않음")
        return False

    def get_s3_bucket_status(self, bucket_name):
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
            return "ACTIVE"
        except:
            return "NOT_FOUND"

    def get_ddb_table_status(self, table_name):
        try:
            response = self.dynamodb.describe_table(TableName=table_name)
            return response['Table']['TableStatus']
        except:
            return "NOT_FOUND"

    def create_s3_bucket(self):
        try:
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
                logger.warning(f"⚠️ 이미 존재하는 버킷: {self.bucket_name}")
            except self.s3_client.exceptions.ClientError:
                self.s3_client.create_bucket(
                    Bucket=self.bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.region},
                    ObjectLockEnabledForBucket=True
                )
                logger.info(f"✅ S3 버킷 생성 완료 (삭제 방지 활성화): {self.bucket_name}")
                self.wait_for_resource("S3 버킷", self.bucket_name, "get_s3_bucket_status", "ACTIVE")

            self.s3_client.put_bucket_versioning(
                Bucket=self.bucket_name,
                VersioningConfiguration={'Status': 'Enabled'}
            )
            logger.info("📚 버전 관리 활성화 완료")

            self.s3_client.put_bucket_encryption(
                Bucket=self.bucket_name,
                ServerSideEncryptionConfiguration={
                    'Rules': [{
                        'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'},
                        'BucketKeyEnabled': True
                    }]
                }
            )
            logger.info("🔒 서버측 암호화 설정 완료")

            self.block_public_access()
            return True
        except Exception as e:
            logger.error(f"S3 버킷 생성 실패: {str(e)}")
            return False

    def block_public_access(self):
        try:
            self.s3_client.put_public_access_block(
                Bucket=self.bucket_name,
                PublicAccessBlockConfiguration={
                    'BlockPublicAcls': True,
                    'IgnorePublicAcls': True,
                    'BlockPublicPolicy': True,
                    'RestrictPublicBuckets': True
                }
            )
            logger.info("🚫 퍼블릭 접근 차단 설정 완료")
            return True
        except Exception as e:
            logger.error(f"퍼블릭 접근 차단 설정 실패: {str(e)}")
            return False

    def set_https_only_policy(self):
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowSSLRequestsOnly",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [
                        f"arn:aws:s3:::{self.bucket_name}",
                        f"arn:aws:s3:::{self.bucket_name}/*"
                    ],
                    "Condition": {
                        "Bool": {"aws:SecureTransport": "false"},
                        "NumericLessThan": {"s3:TlsVersion": 1.2}
                    }
                }
            ]
        }
        try:
            self.s3_client.put_bucket_policy(
                Bucket=self.bucket_name,
                Policy=json.dumps(policy)
            )
            logger.info("🔐 HTTPS 전용 접근 정책 적용 완료")
            return True
        except Exception as e:
            logger.error(f"HTTPS 전용 정책 설정 실패: {str(e)}")
            return False

    def create_dynamodb_table(self):
        try:
            try:
                self.dynamodb.describe_table(TableName=self.ddb_table)
                logger.warning(f"⚠️ 이미 존재하는 테이블: {self.ddb_table}")
            except self.dynamodb.exceptions.ResourceNotFoundException:
                self.dynamodb.create_table(
                    TableName=self.ddb_table,
                    AttributeDefinitions=[{'AttributeName': 'LockID', 'AttributeType': 'S'}],
                    KeySchema=[{'AttributeName': 'LockID', 'KeyType': 'HASH'}],
                    BillingMode='PAY_PER_REQUEST',
                    SSESpecification={
                        'Enabled': True,
                        'SSEType': 'KMS'
                    },
                    Tags=[
                        {'Key': 'Purpose', 'Value': 'TerraformLock'},
                        {'Key': 'Environment', 'Value': 'Infrastructure'},
                        {'Key': 'CreatedBy', 'Value': 'TerraformBackendManager'},
                        {'Key': 'CreatedDate', 'Value': datetime.now().strftime("%Y-%m-%d")}
                    ]
                )
                logger.info(f"✅ DynamoDB 테이블 생성 완료: {self.ddb_table}")
                self.wait_for_resource("DynamoDB 테이블", self.ddb_table, "get_ddb_table_status", "ACTIVE")

            try:
                time.sleep(2)
                self.dynamodb.update_continuous_backups(
                    TableName=self.ddb_table,
                    PointInTimeRecoverySpecification={'PointInTimeRecoveryEnabled': True}
                )
                logger.info("💾 DynamoDB 연속 백업 활성화 완료")
            except Exception as backup_error:
                logger.warning(f"⚠️ DynamoDB 백업 설정 실패 (무시됨): {str(backup_error)}")

            return True
        except Exception as e:
            logger.error(f"DynamoDB 테이블 생성 실패: {str(e)}")
            return False

    def _get_github_thumbprint(self):
        return "6938fd4d98bab03faadb97b34396831e3780aea1"

    def ensure_github_oidc_provider(self):
        oidc_url = "token.actions.githubusercontent.com"
        provider_arn = f"arn:aws:iam::{self.get_account_id()}:oidc-provider/{oidc_url}"
        try:
            try:
                self.iam.get_open_id_connect_provider(OpenIDConnectProviderArn=provider_arn)
                logger.info(f"✓ GitHub OIDC 제공자 이미 존재함: {oidc_url}")
                return provider_arn
            except self.iam.exceptions.NoSuchEntityException:
                thumbprint = self._get_github_thumbprint()
                response = self.iam.create_open_id_connect_provider(
                    Url=f"https://{oidc_url}",
                    ClientIDList=["sts.amazonaws.com"],
                    ThumbprintList=[thumbprint]
                )
                logger.info(f"✅ GitHub OIDC 제공자 생성 완료: {oidc_url}")
                return response['OpenIDConnectProviderArn']
        except Exception as e:
            logger.error(f"GitHub OIDC 제공자 생성 실패: {str(e)}")
            raise

    def create_github_oidc_role(self, repo_owner, repo_name):
        if not self._validate_github_repo(repo_owner, repo_name):
            raise ValueError(f"유효하지 않은 GitHub 저장소: {repo_owner}/{repo_name}")

        role_name = f"GitHubTerraformOIDCRole-{repo_name}"
        account_id = self.get_account_id()  # Move this line here

        try:
            provider_arn = self.ensure_github_oidc_provider()
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Federated": provider_arn},
                        "Action": "sts:AssumeRoleWithWebIdentity",
                        "Condition": {
                            "StringEquals": {
                                "token.actions.githubusercontent.com:sub": f"repo:{repo_owner}/{repo_name}:environment:production",
                                "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                            }
                        }
                    }
                ]
            }

            try:
                self.iam.get_role(RoleName=role_name)
                logger.warning(f"⚠️ 이미 존재하는 IAM Role: {role_name}")
                self.iam.update_assume_role_policy(
                    RoleName=role_name,
                    PolicyDocument=json.dumps(trust_policy)
                )
                logger.info(f"🔄 IAM Role 신뢰 정책 업데이트 완료: {role_name}")
            except self.iam.exceptions.NoSuchEntityException:
                self.iam.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(trust_policy),
                    Description=f"GitHub Actions OIDC Role for {repo_owner}/{repo_name}",
                    Tags=[
                        {'Key': 'Purpose', 'Value': 'GitHubOIDC'},
                        {'Key': 'Repository', 'Value': f"{repo_owner}/{repo_name}"},
                        {'Key': 'CreatedBy', 'Value': 'TerraformBackendManager'},
                        {'Key': 'CreatedDate', 'Value': datetime.now().strftime("%Y-%m-%d")}
                    ]
                )
                logger.info(f"✅ IAM Role 생성 완료: {role_name}")

            terraform_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "iam:CreateRole",
                "iam:PutRolePolicy",
                "iam:CreatePolicy",
                "iam:AttachRolePolicy",
                "iam:DetachRolePolicy",
                "iam:GetRole",
                "iam:GetPolicy",
                "iam:GetRolePolicy",
                "iam:GetPolicyVersion",
                "iam:ListRolePolicies",
                "iam:ListAttachedRolePolicies",
                "iam:ListPolicyVersions",
                "iam:ListInstanceProfilesForRole",
                "iam:DeletePolicy",
                "iam:DeleteRole",
                "iam:PassRole",
                "iam:DeleteRolePolicy"
            ],
            "Resource": f"arn:aws:iam::{account_id}:role/tf-*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject", "s3:PutObject", "s3:ListBucket"
            ],
            "Resource": [
                f"arn:aws:s3:::{self.bucket_name}",
                f"arn:aws:s3:::{self.bucket_name}/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:CreateTable", "dynamodb:DescribeTable"
            ],
            "Resource": f"arn:aws:dynamodb:{self.region}:{account_id}:table/{self.ddb_table}"
        },
        {
            "Effect": "Allow",
            "Action": [
                "sns:ListTopics", "sns:GetTopicAttributes", "sns:ListTagsForResource", "sns:Subscribe", "sns:Unsubscribe", "sns:GetSubscriptionAttributes"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "lambda:GetFunctionCodeSigningConfig", "lambda:GetFunction", "lambda:ListVersionsByFunction", "lambda:AddPermission",
                "lambda:InvokeFunction", "lambda:GetFunctionConfiguration", "lambda:CreateFunction", "lambda:UpdateFunctionCode",
                "lambda:GetPolicy", "lambda:RemovePermission", "lambda:DeleteFunction"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": "iam:PassRole",
            "Resource": f"arn:aws:iam::{account_id}:role/lockcleaner-role*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "events:PutRule", "events:PutTargets", "events:DescribeRule", "events:RemoveTargets", "events:DeleteRule"
            ],
            "Resource": "arn:aws:events:ap-northeast-2:*:rule/lockcleaner-schedule"
        },
        {
            "Effect": "Allow",
            "Action": "events:ListTagsForResource",
            "Resource": "arn:aws:events:ap-northeast-2:*:rule/lockcleaner-schedule"
        }
    ]
}


            self.iam.put_role_policy(
                RoleName=role_name,
                PolicyName="TerraformStateAccess",
                PolicyDocument=json.dumps(terraform_policy)
            )

            logger.info("📝 IAM Role에 최소 권한 정책 적용 완료")

            return f"arn:aws:iam::{account_id}:role/{role_name}"
        except Exception as e:
            logger.error(f"GitHub OIDC 역할 생성 실패: {str(e)}")
            raise

if __name__ == "__main__":
    print("\U0001F4E6 Terraform 상태 저장소 자동화 도구 (최소 구성 버전)")

    try:
        region = input("\U0001F30D AWS 리전 입력 (예: ap-northeast-2): ").strip()
        bucket_name = input("\U0001FAA3 상태 저장용 S3 버킷 이름: ").strip()
        repo_owner = input("\U0001F419 GitHub 저장소 Owner (예: your-org): ").strip()
        repo_name = input("📁 GitHub 저장소 Name (예: your-repo): ").strip()

        manager = TerraformBackendManager(region, bucket_name)

        print("""
\U0001F4A1 실행할 작업을 선택하세요:
1. S3 버킷 생성
2. DynamoDB 테이블 생성
3. GitHub OIDC 역할 생성 + 정책 적용
4. 전체 자동 실행 (1~3)
        """)
        choice = input("👉 번호 입력 (예: 1): ").strip()

        if choice == "1":
            if manager.create_s3_bucket():
                manager.set_https_only_policy()

        elif choice == "2":
            manager.create_dynamodb_table()

        elif choice == "3":
            manager.create_github_oidc_role(repo_owner, repo_name)

        elif choice == "4":
            if manager.create_s3_bucket():
                manager.set_https_only_policy()
            manager.create_dynamodb_table()
            manager.create_github_oidc_role(repo_owner, repo_name)

        print("\n✅ 선택한 작업이 완료되었습니다!")

    except Exception as e:
        logger.error(f"프로그램 실행 중 오류 발생: {str(e)}")