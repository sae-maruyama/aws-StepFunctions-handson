import json
import boto3
import uuid
import os
from datetime import datetime

def lambda_handler(event, context):
    # API Gateway経由の場合、bodyをパース
    if 'body' in event and event['body']:
        try:
            # bodyが文字列の場合（API Gateway）
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        except json.JSONDecodeError:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid JSON format'})
            }
    else:
        # 直接呼び出しの場合
        body = event

    # 1. 入力パラメータのチェック
    required_fields = ["mailAddress", "userName", "reviewText"]
    missing_fields = [field for field in required_fields if field not in body or not body[field]]

    if missing_fields:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'Validation failed',
                'missing_fields': missing_fields
            })
        }
    
    # 2.入力パラメータの取得
    mailAddress = body["mailAddress"]  # 投稿者のメールアドレス
    userName = body["userName"]  # 問い合わせの投稿者名（存在しない場合は空白）
    reviewText = body["reviewText"]  # 問い合わせの内容（存在しない場合は空白）
    
    # 3.idの生成（uuidを取得）
    item_id = str(uuid.uuid4()) # 例：058b2f0a-985a-4fa1-8d42-5c1313f1c0c4
    
    # 4.タイムスタンプの取得
    timestamp = datetime.now().isoformat() # 例：2025-09-01T23:11:11.541085
    
    # 5.DynamoDBリソースの初期化（テーブル名を環境変数から取得）
    dynamodb = boto3.resource('dynamodb')
    table_name = os.environ.get('TABLE_NAME', 'InquiryTable')  # Terraformから渡されるテーブル名
    table = dynamodb.Table(table_name)
    
    # 6.DynamoDBに更新するitemの内容を辞書で定義
    item = {
        'id': item_id,
        'mailAddress': mailAddress,
        'userName': userName,
        'reviewText': reviewText,
        'createdAt': timestamp,
        'updatedAt': timestamp
    }
    
    try:
        # 7.DynamoDBにデータを保存
        table.put_item(Item=item)
        
        # 8. SQSにメッセージを送信して非同期処理を開始
        sqs_client = boto3.client('sqs')
        queue_url = os.environ.get('SQS_QUEUE_URL')
        
        if queue_url:
            # SQSメッセージの内容
            message_body = {
                'id': item_id
            }
            
            # SQSにメッセージを送信
            sqs_response = sqs_client.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(message_body)
            )
            
            print(f"Message sent to SQS: {sqs_response['MessageId']}")
        else:
            print("Warning: SQS_QUEUE_URL environment variable not set")
            
    except Exception as e:
        # 9.エラーが発生した場合、ステータスコード500（内部サーバエラー）を返す
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error saving item to DynamoDB or sending SQS message: {str(e)}')
        }
    
    # 10.ステータスコード200（正常終了）を返す
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Inquiry saved successfully and processing started!',
            'id': item_id
        })
    }