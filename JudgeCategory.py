import json
import boto3
import os
from datetime import datetime

def lambda_handler(event, context):
    # 1. 入力パラメータのチェック
    if 'id' not in event or not event['id']:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'Missing required parameter: id'
            })
        }
    
    inquiry_id = event['id']
    
    # 2. DynamoDBリソースの初期化
    dynamodb = boto3.resource('dynamodb')
    table_name = os.environ.get('TABLE_NAME', 'my-inquiry-dev-table')
    table = dynamodb.Table(table_name)
    
    try:
        # 3. InquiryTableから問い合わせ内容を取得
        response = table.get_item(Key={'id': inquiry_id})
        
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'error': f'Inquiry with id {inquiry_id} not found'
                })
            }
        
        inquiry_item = response['Item']
        review_text = inquiry_item.get('reviewText', '')
        
        if not review_text:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'ReviewText is empty or missing'
                })
            }
        
        # 4. Bedrockクライアントの初期化
        bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
        model_id = os.environ.get('BEDROCK_MODEL_ID', "anthropic.claude-3-sonnet-20240229-v1:0")
        
        # 5. 分類用のプロンプトを構築
        prompt = f"""以下の問い合わせ内容を、指定されたカテゴリのいずれかに分類してください。

問い合わせ内容：
{review_text}

分類カテゴリ：
1. 質問 - 何かを尋ねている、情報を求めている
2. 改善要望 - サービスや設備の改善を求めている
3. ポジティブな感想 - 良かった点や褒め言葉
4. ネガティブな感想 - 不満や苦情
5. その他 - 上記に当てはまらないもの

分類ルール：
- 必ず1つのカテゴリを選択してください
- 複数の要素がある場合は、最も強い要素で判断してください
- 回答は以下の形式で返してください：「カテゴリ名」のみ

回答："""

        # 6. Bedrockで分類を実行
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps(request_body)
        )
        
        response_body = json.loads(response['body'].read())
        raw_category = response_body['content'][0]['text'].strip()
        
        # 7. 分類結果を正規化（有効なカテゴリに変換）
        valid_categories = ['質問', '改善要望', 'ポジティブな感想', 'ネガティブな感想', 'その他']
        category = 'その他'  # デフォルト値
        
        # 部分一致で有効なカテゴリを検索
        for valid_cat in valid_categories:
            if valid_cat in raw_category:
                category = valid_cat
                break
        
        # 8. 分類結果をInquiryTableに保存
        timestamp = datetime.now().isoformat()
        
        table.update_item(
            Key={'id': inquiry_id},
            UpdateExpression='SET Category = :category, updatedAt = :updatedAt',
            ExpressionAttributeValues={
                ':category': category,
                ':updatedAt': timestamp
            }
        )
        
        # 9. 成功レスポンスを返す（分類結果を出力値として返す）
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Category classified and saved successfully',
                'id': inquiry_id,
                'category': category
            }),
            'category': category  # Step Functionsで使用する出力値（Taskの出力が「ResultPath」に入るのがStep Functionsの標準動作）
        }
        
    except Exception as e:
        # 10. エラーハンドリング
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f'Error processing request: {str(e)}'
            })
        }