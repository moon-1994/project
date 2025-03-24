# main.py

import boto3

REGION = "ap-northeast-2"
BUCKET_NAME = "terraform-state-bucket-123456"  # 유니크한 이름
DDB_TABLE = "terraform-lock"

def create_s3_bucket():
    s3 = boto3.client("s3", region_name=REGION)
    
    # S3 버킷 생성
    try:
        s3.create_bucket(
            Bucket=BUCKET_NAME,
            CreateBucketConfiguration={'LocationConstraint': REGION}
        )
        print(f"✅ S3 버킷 생성 완료: {BUCKET_NAME}")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"⚠️ 이미 존재하는 버킷: {BUCKET_NAME}")
    
    # 버전 관리 활성화
    s3.put_bucket_versioning(
        Bucket=BUCKET_NAME,
        VersioningConfiguration={'Status': 'Enabled'}
    )

    # 암호화 설정
    s3.put_bucket_encryption(
        Bucket=BUCKET_NAME,
        ServerSideEncryptionConfiguration={
            'Rules': [{
                'ApplyServerSideEncryptionByDefault': {
                    'SSEAlgorithm': 'AES256'
                }
            }]
        }
    )

def create_dynamodb_table():
    dynamodb = boto3.client("dynamodb", region_name=REGION)
    try:
        dynamodb.create_table(
            TableName=DDB_TABLE,
            AttributeDefinitions=[
                {'AttributeName': 'LockID', 'AttributeType': 'S'}
            ],
            KeySchema=[
                {'AttributeName': 'LockID', 'KeyType': 'HASH'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        print(f"✅ DynamoDB 테이블 생성 완료: {DDB_TABLE}")
    except dynamodb.exceptions.ResourceInUseException:
        print(f"⚠️ 이미 존재하는 테이블: {DDB_TABLE}")

if __name__ == "__main__":
    create_s3_bucket()
    create_dynamodb_table()
