# terraform_backend_manager.py

import boto3
import json
import time
from datetime import datetime, timedelta

class TerraformBackendManager:
    def __init__(self, region, bucket_name, ddb_table="terraform-lock"):
        self.region = region
        self.bucket_name = bucket_name
        self.ddb_table = ddb_table

        self.s3_client = boto3.client("s3", region_name=region)
        self.s3_resource = boto3.resource("s3", region_name=region)
        self.dynamodb = boto3.client("dynamodb", region_name=region)
        self.iam = boto3.client("iam")

    def get_account_id(self):
        sts = boto3.client("sts")
        return sts.get_caller_identity()["Account"]

    def create_s3_bucket(self):
        try:
            self.s3_client.create_bucket(
                Bucket=self.bucket_name,
                CreateBucketConfiguration={'LocationConstraint': self.region},
                ObjectLockEnabledForBucket=True
            )
            print(f"✅ S3 버킷 생성 완료 (삭제 방지 활성화): {self.bucket_name}")
        except self.s3_client.exceptions.BucketAlreadyOwnedByYou:
            print(f"⚠️ 이미 존재하는 버킷: {self.bucket_name}")

        self.apply_s3_security_settings(self.bucket_name)

    def apply_s3_security_settings(self, bucket):
        self.s3_client.put_bucket_versioning(
            Bucket=bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )

        self.s3_client.put_bucket_encryption(
            Bucket=bucket,
            ServerSideEncryptionConfiguration={
                'Rules': [{
                    'ApplyServerSideEncryptionByDefault': {
                        'SSEAlgorithm': 'AES256'
                    }
                }]
            }
        )

        self.s3_client.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': True,
                'IgnorePublicAcls': True,
                'BlockPublicPolicy': True,
                'RestrictPublicBuckets': True
            }
        )
        print(f"🔐 S3 보안 설정 완료: {bucket}")

    def check_or_create_bucket(self, bucket_name):
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
            print(f"✅ 로그 버킷 존재 확인 완료: {bucket_name}")
        except self.s3_client.exceptions.ClientError:
            self.s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': self.region}
            )
            print(f"🪵 로그 버킷 자동 생성 완료: {bucket_name}")
            self.apply_s3_security_settings(bucket_name)

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
                        "Bool": {
                            "aws:SecureTransport": "false"
                        }
                    }
                }
            ]
        }
        self.s3_client.put_bucket_policy(
            Bucket=self.bucket_name,
            Policy=json.dumps(policy)
        )
        print("🔐 HTTPS 전용 접근 정책 적용 완료")

    def create_dynamodb_table(self):
        try:
            self.dynamodb.create_table(
                TableName=self.ddb_table,
                AttributeDefinitions=[{'AttributeName': 'LockID', 'AttributeType': 'S'}],
                KeySchema=[{'AttributeName': 'LockID', 'KeyType': 'HASH'}],
                BillingMode='PAY_PER_REQUEST'
            )
            print(f"✅ DynamoDB 테이블 생성 완료: {self.ddb_table}")
        except self.dynamodb.exceptions.ResourceInUseException:
            print(f"⚠️ 이미 존재하는 테이블: {self.ddb_table}")

    def create_github_oidc_role(self, repo_owner, repo_name):
        role_name = "GitHubTerraformOIDCRole"
        oidc_url = "token.actions.githubusercontent.com"
        provider_arn = f"arn:aws:iam::{self.get_account_id()}:oidc-provider/{oidc_url}"

        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Federated": provider_arn},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            f"{oidc_url}:sub": f"repo:{repo_owner}/{repo_name}:ref:refs/heads/main"
                        }
                    }
                }
            ]
        }

        try:
            self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="GitHub Actions OIDC Terraform CI/CD Role"
            )
            print(f"✅ IAM Role 생성 완료: {role_name}")
        except self.iam.exceptions.EntityAlreadyExistsException:
            print(f"⚠️ 이미 존재하는 IAM Role: {role_name}")

        time.sleep(5)

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                    "Resource": [
                        f"arn:aws:s3:::{self.bucket_name}",
                        f"arn:aws:s3:::{self.bucket_name}/*"
                    ]
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem", "dynamodb:PutItem",
                        "dynamodb:DeleteItem", "dynamodb:Scan", "dynamodb:Query"
                    ],
                    "Resource": f"arn:aws:dynamodb:{self.region}:{self.get_account_id()}:table/{self.ddb_table}"
                }
            ]
        }

        self.iam.put_role_policy(
            RoleName=role_name,
            PolicyName="GitHubOIDCAccessPolicy",
            PolicyDocument=json.dumps(policy)
        )

        return f"arn:aws:iam::{self.get_account_id()}:role/{role_name}"

    def restrict_to_github_oidc(self, github_role_arn):
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowOnlyGitHubOIDCRole",
                    "Effect": "Allow",
                    "Principal": {"AWS": github_role_arn},
                    "Action": "s3:*",
                    "Resource": [
                        f"arn:aws:s3:::{self.bucket_name}",
                        f"arn:aws:s3:::{self.bucket_name}/*"
                    ],
                    "Condition": {
                        "StringEquals": {
                            "aws:PrincipalArn": github_role_arn
                        }
                    }
                }
            ]
        }
        self.s3_client.put_bucket_policy(
            Bucket=self.bucket_name,
            Policy=json.dumps(policy)
        )
        print("🔐 GitHub OIDC 전용 접근 정책 적용 완료")

if __name__ == "__main__":
    print("📦 Terraform 상태 저장소 자동화 도구")
    region = input("🌍 AWS 리전 입력 (예: ap-northeast-2): ").strip()
    bucket_name = input("🪣 상태 저장용 S3 버킷 이름: ").strip()
    repo_owner = input("🐙 GitHub 저장소 Owner (예: your-org): ").strip()
    repo_name = input("📁 GitHub 저장소 Name (예: your-repo): ").strip()
    log_bucket = input("🪵 접근 로그 저장용 S3 버킷 이름 (선택): ").strip()

    manager = TerraformBackendManager(region, bucket_name)

    manager.create_s3_bucket()
    manager.create_dynamodb_table()

    oidc_role_arn = manager.create_github_oidc_role(repo_owner, repo_name)
    print(f"🔍 생성된 OIDC Role ARN: {oidc_role_arn}")
    time.sleep(5)
    manager.restrict_to_github_oidc(oidc_role_arn)

    if log_bucket:
        manager.check_or_create_bucket(log_bucket)
        # log_bucket에 대한 접근 로그 설정, 태그, 수명 주기 등은 이후에 추가 가능
