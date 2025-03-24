# delete_resources.py

import boto3

REGION = "ap-northeast-2"
BUCKET_NAME = "terraform-state-bucket-123456"   # 생성했던 버킷 이름
DDB_TABLE = "terraform-lock"

def delete_s3_bucket():
    s3 = boto3.resource("s3", region_name=REGION)
    bucket = s3.Bucket(BUCKET_NAME)
    
    print(f"🗑️ S3 버킷 안의 객체 삭제 중: {BUCKET_NAME}")
    bucket.objects.all().delete()  # 버킷 안에 있는 모든 객체 먼저 삭제

    print(f"🗑️ S3 버킷 삭제 중: {BUCKET_NAME}")
    bucket.delete()
    print("✅ S3 버킷 삭제 완료")

def delete_dynamodb_table():
    dynamodb = boto3.client("dynamodb", region_name=REGION)
    print(f"🗑️ DynamoDB 테이블 삭제 중: {DDB_TABLE}")
    dynamodb.delete_table(TableName=DDB_TABLE)
    print("✅ DynamoDB 테이블 삭제 완료")

if __name__ == "__main__":
    delete_s3_bucket()
    delete_dynamodb_table()
