# UploadInquiry Lambda
ユーザーの問い合わせを受け取り、DynamoDBに保存し、SQSにidを送信。

# SQSキュー
UploadInquiryから送られてきたidを保持。Lambdaがトリガーで受け取る。

# Execution Lambda（SQS→Step Functions起動）
SQSメッセージからidを取り出し、Step Functionsステートマシンをinput={'id':...}で起動。

# Step Functions
- Task1: JudgeCategory Lambdaを呼ぶ
- Choice: カテゴリに応じて分岐
- Task2: CreateAnswer Lambdaを呼ぶ（今回はRAGあり）

# DynamoDB
UploadInquiryで保存された問い合わせや、各Lambdaが書き込むカテゴリ・回答を保持。

## 📨 各ステップの受け渡しデータ

### ① UploadInquiry Lambda

**入力例**

```json
{
  "mailAddress": "test@example.com",
  "userName": "テストユーザー",
  "reviewText": "チェックイン時間は何時ですか？"
}
```
- lambda_handler(event, context) の event にそのまま入る。

**データ保存とSQS送信（コード）**

```python
item = {
    'id': item_id,
    'mailAddress': mailAddress,
    'userName': userName,
    'reviewText': reviewText,
    'createdAt': timestamp,
    'updatedAt': timestamp
}
table.put_item(Item=item)   # DynamoDBに保存

message_body = {'id': item_id}
sqs_client.send_message(
    QueueUrl=queue_url,
    MessageBody=json.dumps(message_body)
)
```
-DynamoDBにはitemがそのまま保存。
- SQSには{"id":"xxxx-uuid"}がメッセージとして送られる。

### ② SQS（メッセージの中身）

UploadInquiryがSQSに送った内容：

```json
{
  "id": "xxxx-uuid"
}
```
- SQSがLambdaをトリガーする時のイベント（event）：

```json
{
  "Records": [
    {
      "body": "{\"id\":\"xxxx-uuid\"}"
    }
  ]
}
```
- Execution Lambda の for record in event['Records']: で回す。

### ③ Execution Lambda（SQS→Step Functions）

**SQSイベントのパース（コード）**

```python
for record in event['Records']:
    message_body = json.loads(record['body'])
    if 'id' not in message_body: continue
    inquiry_id = message_body['id']
```
- ここで inquiry_id に "xxxx-uuid" が入ります。

**Step Functions起動（コード）**

```python
execution_input = {'id': inquiry_id}
response = stepfunctions_client.start_execution(
    stateMachineArn=state_machine_arn,
    name=f"inquiry-processing-{inquiry_id}",
    input=json.dumps(execution_input)
)
```
- ステートマシンのinputは {"id":"xxxx-uuid"}。

### ④ Step Functions（JudgeCategory → CheckCategory → CreateAnswer）

**ステートマシンのinput**

```json
{
  "id": "xxxx-uuid"
}
```

**JudgeCategoryステート（コード）**
```json
"Parameters": {
  "FunctionName": "JudgeCategory",
  "Payload": {
    "id.$": "$.id"
  }
},
"ResultPath": "$.judgeCategoryResult"
```
- Payload が Lambda の event になります。
- JudgeCategory Lambda に渡される event：

```json
{ "id": "xxxx-uuid" }
```

**JudgeCategory Lambda内（コード）**
```python
if 'id' not in event: ...
inquiry_id = event['id']

response = table.get_item(Key={'id': inquiry_id})
review_text = inquiry_item.get('reviewText', '')

# Bedrockに分類プロンプトを投げる
raw_category = response_body['content'][0]['text'].strip()

# カテゴリを決定
category = ...
table.update_item(... Category = :category ...)

return {
  'statusCode': 200,
  'body': json.dumps({...}),
  'category': category
}
```
- DynamoDBから reviewText を取得。
- Bedrockでカテゴリ分類。
- DynamoDBの該当項目にCategoryを更新。
- Lambdaの戻り値全体が $.judgeCategoryResult に格納される。

```json
{
  "id": "xxxx-uuid",
  "judgeCategoryResult": {
    "statusCode": 200,
    "body": "{\"message\":...}",
    "category": "質問"
  }
}
```

**Choiceステート（コード）**
```json
"Choices": [
  {
    "Variable": "$.judgeCategoryResult.category",
    "StringEquals": "質問",
    "Next": "CreateAnswer"
  }
]
```

$.judgeCategoryResult.category を見て分岐。

**CreateAnswerステート（コード）**
```json
"Parameters": {
  "FunctionName": "CreateAnswer",
  "Payload": {
    "id.$": "$.id"
  }
},
"ResultPath": "$.createAnswerResult"
```

CreateAnswer Lambda に渡る event：

```json
{ "id": "xxxx-uuid" }
```

**CreateAnswer Lambda内（コード）**
```python
if 'id' not in event: ...
inquiry_id = event['id']

response = table.get_item(Key={'id': inquiry_id})
review_text = inquiry_item.get('reviewText', '')

# 必要ならナレッジベース検索
retrieve_response = bedrock_agent_runtime.retrieve(... review_text ...)
context_text = ...
prompt = f"...{context_text}...{review_text}..."

# Bedrockで回答生成
generated_answer = response_body['content'][0]['text']

# DynamoDBに保存
table.update_item(
    Key={'id': inquiry_id},
    UpdateExpression='SET answer = :answer, updatedAt = :updatedAt',
    ExpressionAttributeValues={
        ':answer': generated_answer,
        ':updatedAt': timestamp
    }
)

return {
  'statusCode': 200,
  'body': json.dumps({
    'message': 'Answer generated and saved successfully',
    'id': inquiry_id,
    'answer': generated_answer
  })
}
```
- DynamoDBから問い合わせを再取得。
- ナレッジベース（あれば）で関連情報を検索し、プロンプトを作成。
- Bedrockで回答を生成。
- DynamoDBに answer と updatedAt を書き込み。
- Lambdaの戻り値は $.createAnswerResult に格納される。

### ⑤ 最終的なStep Functionsデータ

Step Functions実行が終わった時点の全体データイメージ：

```json
{
  "id": "xxxx-uuid",
  "judgeCategoryResult": {
    "statusCode": 200,
    "body": "{\"message\":\"...\",\"id\":\"xxxx-uuid\",\"category\":\"質問\"}",
    "category": "質問"
  },
  "createAnswerResult": {
    "statusCode": 200,
    "body": "{\"message\":\"Answer generated and saved successfully\",\"id\":\"xxxx-uuid\",\"answer\":\"チェックイン時間は15時からです…\"}"
  }
}
```
- DynamoDBの項目は最終的にこうなる↓

```json
{
  "id": "xxxx-uuid",
  "mailAddress": "test@example.com",
  "userName": "テストユーザー",
  "reviewText": "チェックイン時間は何時ですか？",
  "Category": "質問",
  "answer": "チェックイン時間は15時からです…",
  "createdAt": "...",
  "updatedAt": "..."
}
```