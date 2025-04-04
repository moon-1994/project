import boto3
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TerraformBackendCleaner:
    def __init__(self, region, bucket_name, ddb_table, role_name):
        self.region = region
        self.bucket_name = bucket_name
        self.ddb_table = ddb_table
        self.role_name = role_name

        self.s3 = boto3.client("s3", region_name=region)
        self.dynamodb = boto3.client("dynamodb", region_name=region)
        self.iam = boto3.client("iam", region_name=region)

    def delete_s3_bucket(self):
        try:
            logger.info(f"🔄 S3 버킷 내 객체 삭제 중: {self.bucket_name}")
            paginator = self.s3.get_paginator('list_object_versions')
            for page in paginator.paginate(Bucket=self.bucket_name):
                versions = page.get('Versions', []) + page.get('DeleteMarkers', [])
                for version in versions:
                    self.s3.delete_object(
                        Bucket=self.bucket_name,
                        Key=version['Key'],
                        VersionId=version['VersionId']
                    )
            self.s3.delete_bucket(Bucket=self.bucket_name)
            logger.info(f"🧹 S3 버킷 삭제 완료: {self.bucket_name}")
        except Exception as e:
            logger.error(f"S3 버킷 삭제 실패: {str(e)}")

    def delete_dynamodb_table(self):
        try:
            self.dynamodb.delete_table(TableName=self.ddb_table)
            logger.info(f"🗑️ DynamoDB 테이블 삭제 완료: {self.ddb_table}")
        except Exception as e:
            logger.error(f"DynamoDB 테이블 삭제 실패: {str(e)}")

    def delete_iam_role(self):
        try:
            # 인라인 정책 삭제
            self.iam.delete_role_policy(
                RoleName=self.role_name,
                PolicyName="TerraformStateAccess"
            )
            # 역할 삭제
            self.iam.delete_role(RoleName=self.role_name)
            logger.info(f"🚫 IAM 역할 삭제 완료: {self.role_name}")
        except Exception as e:
            logger.error(f"IAM 역할 삭제 실패: {str(e)}")

if __name__ == "__main__":
    print("\n🧨 Terraform 상태 저장소 리소스 정리 도구")
    try:
        region = input("🌍 AWS 리전 입력 (예: ap-northeast-2): ").strip()
        bucket_name = input("🪣 삭제할 S3 버킷 이름: ").strip()
        ddb_table = input("📄 삭제할 DynamoDB 테이블 이름: ").strip()
        role_name = input("🔐 삭제할 IAM Role 이름: ").strip()

        cleaner = TerraformBackendCleaner(region, bucket_name, ddb_table, role_name)

        confirm = input("⚠️ 모든 리소스를 삭제하시겠습니까? (yes/no): ").strip().lower()
        if confirm == "yes":
            cleaner.delete_s3_bucket()
            cleaner.delete_dynamodb_table()
            cleaner.delete_iam_role()
            print("\n✅ 리소스 삭제 완료!")
        else:
            print("⛔ 삭제 취소됨.")

    except Exception as e:
        logger.error(f"삭제 도중 오류 발생: {str(e)}")
