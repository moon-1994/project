# ✅ Lambda 코드(zip) 생성 + 락 클리너 배포 포함
from terraform_lambda_sns import create_lambda_zip, deploy_lock_cleaner_lambda
from terraform_backend_minimum import TerraformBackendManager

if __name__ == "__main__":
    print("\U0001F4E6 Terraform Backend 전체 자동화 (S3 + DynamoDB + GitHub OIDC + Lambda)")

    try:
        region = input("\U0001F30D AWS 리전 입력 (예: ap-northeast-2): ").strip()
        bucket_name = input("\U0001FAA3 상태 저장용 S3 버킷 이름: ").strip()
        repo_owner = input("\U0001F419 GitHub 저장소 Owner (예: your-org): ").strip()
        repo_name = input("📁 GitHub 저장소 Name (예: your-repo): ").strip()

        manager = TerraformBackendManager(region, bucket_name)

        print("\n✅ Lambda 패키징 및 Cleaner 배포 시작...")
        create_lambda_zip()
        deploy_lock_cleaner_lambda()

        print("\n✅ 백엔드 리소스 생성 시작...")
        if manager.create_s3_bucket():
            manager.set_https_only_policy()
        manager.create_dynamodb_table()
        manager.create_github_oidc_role(repo_owner, repo_name)

        print("\n✅ 전체 자동화 완료!")

    except Exception as e:
        print(f"❗ 오류 발생: {str(e)}")
