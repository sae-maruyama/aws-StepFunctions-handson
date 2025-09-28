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

        # 5. RAGを使用してBedrockで回答を生成
        knowledge_base_id = os.environ.get('KNOWLEDGE_BASE_ID')
        model_id = os.environ.get('BEDROCK_MODEL_ID', "anthropic.claude-3-sonnet-20240229-v1:0")

        if knowledge_base_id:
            # RAGを使用した回答生成
            bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

            # RAG検索を実行
            retrieve_response = bedrock_agent_runtime.retrieve(
                knowledgeBaseId=knowledge_base_id,
                retrievalQuery={'text': review_text},
                retrievalConfiguration={
                    'vectorSearchConfiguration': {'numberOfResults': 3}
                }
            )

            # 検索結果からコンテキストを構築
            context_text = ""
            if 'retrievalResults' in retrieve_response:
                for result in retrieve_response['retrievalResults']:
                    context_text += result['content']['text'] + "\n"

            # プロンプトを構築
            prompt = f"""
以下の情報を基に、お客様の問い合わせに丁寧で親切な回答を生成してください。
ホテル情報：
{context_text}
お客様の問い合わせ：
{review_text}
回答は以下の点を考慮してください：
- 丁寧で親切な言葉遣いを使用する
- 具体的で役立つ情報を提供する
- ホテル情報に基づいて正確に回答する
- 不明な点があれば、直接お問い合わせいただくよう案内する
回答：
"""
        else:
            # RAGを使用しない場合の回答生成
            prompt = f"""
お客様の問い合わせに対して、丁寧で親切な回答を生成してください。
お客様の問い合わせ：
{review_text}
回答は以下の点を考慮してください：
- 丁寧で親切な言葉遣いを使用する
- 一般的なホテルサービスに関する回答を提供する
- 具体的な情報が必要な場合は、直接お問い合わせいただくよう案内する
回答：
"""

        # 6. Bedrockで回答を生成
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())
        generated_answer = response_body['content'][0]['text']

        # 7. 生成された回答をInquiryTableに保存
        timestamp = datetime.now().isoformat()
        table.update_item(
            Key={'id': inquiry_id},
            UpdateExpression='SET answer = :answer, updatedAt = :updatedAt',
            ExpressionAttributeValues={
                ':answer': generated_answer,
                ':updatedAt': timestamp
            }
        )

        # 8. 成功レスポンスを返す
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Answer generated and saved successfully',
                'id': inquiry_id,
                'answer': generated_answer
            })
        }

    except Exception as e:
        # 9. エラーハンドリング
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f'Error processing request: {str(e)}'
            })
        }