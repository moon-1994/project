from backend.terraform_backend_minimum import TerraformBackendManager

if __name__ == "__main__":
    print("\U0001f4e6 Terraform 백엔드 인프라 생성 CLI")

    region = input("🌍 AWS 리전 입력 (예: ap-northeast-2): ").strip()
    bucket_name = input("📺 상태 저장용 S3 버킷 이름: ").strip()
    repo_owner = input("👩‍💼 GitHub 저장소 Owner (예: your-org): ").strip()
    repo_name = input("📁 GitHub 저장소 Name (예: your-repo): ").strip()

    try:
        manager = TerraformBackendManager(region, bucket_name)

        print("\n🔢 S3 버킷 생성 중...")
        if manager.create_s3_bucket():
            manager.set_https_only_policy()

        print("\n📂 DynamoDB 테이블 생성 중...")
        manager.create_dynamodb_table()

        print("\n🔐 GitHub OIDC 역할 생성 중...")
        oidc_role_arn = manager.create_github_oidc_role(repo_owner, repo_name)
        manager.combine_bucket_policies(oidc_role_arn)

        print("\n✅ 모든 백엔드 리소스가 성공적으로 생성되었습니다!")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
