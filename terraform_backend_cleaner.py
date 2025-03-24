# terraform_backend_cleaner.py

# terraform_backend_cleaner.py

import boto3

class TerraformBackendCleaner:
    def __init__(self, region, bucket_name, ddb_table="terraform-lock", role_name="GitHubTerraformOIDCRole", policy_name="GitHubOIDCAccessPolicy", log_bucket_name=None):
        self.region = region
        self.bucket_name = bucket_name
        self.ddb_table = ddb_table
        self.role_name = role_name
        self.policy_name = policy_name
        self.log_bucket_name = log_bucket_name

        self.s3_client = boto3.client("s3", region_name=region)
        self.s3_resource = boto3.resource("s3", region_name=region)
        self.dynamodb = boto3.client("dynamodb", region_name=region)
        self.iam = boto3.client("iam")

    def delete_s3_bucket(self, target_bucket):
        bucket = self.s3_resource.Bucket(target_bucket)
        try:
            print(f"🗑️ S3 버킷 객체 삭제 중: {target_bucket}")
            bucket.object_versions.all().delete()
            bucket.objects.all().delete()
            bucket.delete()
            print(f"✅ S3 버킷 삭제 완료: {target_bucket}")
        except Exception as e:
            print(f"❌ S3 삭제 실패 ({target_bucket}): {e}")

    def delete_dynamodb_table(self):
        try:
            print(f"🗑️ DynamoDB 테이블 삭제 중: {self.ddb_table}")
            self.dynamodb.delete_table(TableName=self.ddb_table)
            print(f"✅ DynamoDB 삭제 완료: {self.ddb_table}")
        except Exception as e:
            print(f"❌ DynamoDB 삭제 실패: {e}")

    def delete_oidc_iam_role(self):
        try:
            print(f"🗑️ IAM 인라인 정책 삭제 중: {self.policy_name}")
            self.iam.delete_role_policy(RoleName=self.role_name, PolicyName=self.policy_name)
        except Exception as e:
            print(f"⚠️ 인라인 정책 삭제 실패: {e}")

        try:
            print(f"🗑️ IAM Role 삭제 중: {self.role_name}")
            self.iam.delete_role(RoleName=self.role_name)
            print(f"✅ IAM Role 삭제 완료: {self.role_name}")
        except Exception as e:
            print(f"❌ IAM Role 삭제 실패: {e}")

    def delete_all(self):
        self.delete_s3_bucket(self.bucket_name)
        if self.log_bucket_name:
            self.delete_s3_bucket(self.log_bucket_name)
        self.delete_dynamodb_table()
        self.delete_oidc_iam_role()


if __name__ == "__main__":
    print("⚠️ Terraform 백엔드 리소스 삭제 도구")
    region = input("🌍 AWS 리전 입력 (예: ap-northeast-2): ").strip()
    bucket_name = input("🪣 상태 저장용 S3 버킷 이름: ").strip()
    ddb_table = input("📄 DynamoDB 테이블 이름 (기본: terraform-lock): ").strip() or "terraform-lock"
    log_bucket = input("🪵 로그 저장용 S3 버킷 이름 (선택): ").strip()

    cleaner = TerraformBackendCleaner(region, bucket_name, ddb_table, log_bucket_name=log_bucket if log_bucket else None)

    confirm = input("🚨 정말 모든 리소스를 삭제하시겠습니까? (yes/no): ").strip().lower()
    if confirm == "yes":
        cleaner.delete_all()
    else:
        print("⏹️ 삭제가 취소되었습니다.")