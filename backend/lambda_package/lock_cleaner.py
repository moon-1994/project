import boto3
import time
import os

dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('LOCK_TABLE_NAME', 'terraform-lock')
lock_id = os.environ.get('LOCK_ID', 'global/s3/terraform.tfstate')
max_age_seconds = int(os.environ.get('MAX_LOCK_AGE_SECONDS', '300'))

def lambda_handler(event, context):
    table = dynamodb.Table(table_name)
    try:
        response = table.get_item(Key={"LockID": lock_id})
        item = response.get("Item")
        if not item:
            print("✅ 현재 잠금 없음")
            return
        created_time = item.get("Info", {}).get("CreatedTime")
        if not created_time:
            print("⚠️ 생성 시간 없음 → 삭제 생략")
            return
        lock_age = time.time() - float(created_time)
        if lock_age > max_age_seconds:
            print(f"⏱️ Lock이 {int(lock_age)}초 경과됨 → 삭제")
            table.delete_item(Key={"LockID": lock_id})
            print("🧹 Lock 삭제 완료")
        else:
            print(f"🕒 아직 유효한 Lock → 유지 ({int(lock_age)}초 경과)")
    except Exception as e:
        print(f"❗ 오류 발생: {e}")
