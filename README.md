# 全体の流れ
- UploadInquiry Lambda
→ ユーザーの問い合わせを受け取り、DynamoDBに保存し、SQSにidを送信。

- SQSキュー
→ UploadInquiryから送られてきたidを保持。

- Execution Lambda（SQS→Step Functions起動）
→ SQSメッセージからidを取り出し、Step Functionsステートマシンをinput={'id':...}で起動。

- Step Functions
Task1: JudgeCategory Lambdaを呼ぶ
Choice: カテゴリに応じて分岐
Task2: CreateAnswer Lambdaを呼ぶ（今回はRAGあり）

- DynamoDB
→ UploadInquiryで保存された問い合わせや、各Lambdaが書き込むカテゴリ・回答を保持。

---

# データ受け渡しの流れ
dataflow.md　を参照

---

# リソース作成順序

## 事前準備
1. Bedrock基盤モデルアクセス有効化
2. IAM基本ロール作成（Lambda用、Step Functions用）

## 基盤リソース作成
3. DynamoDB テーブル作成
4. SQS キュー作成（デッドレターキュー含む）

## Lambda関数作成・テスト
5. JudgeCategory Lambda作成・デプロイ
6. CreateAnswer Lambda作成・デプロイ
12. 各Lambda関数の環境変数設定
7. 個別Lambda関数テスト（Bedrock呼び出し確認）

## ワークフロー構築
8. Step Functions ステートマシン作成
9. ExecuteJob Lambda作成・デプロイ
10. UploadInquiry Lambda修正・デプロイ

## 統合設定
11. SQS → ExecuteJob トリガー設定
13. IAMロールの詳細権限追加

## テスト・検証
14. Step Functions実行テスト
15. エンドツーエンド統合テスト

## オプション機能（後から追加可能）
16. S3バケット作成・データアップロード（RAG用）
17. Bedrock Knowledge Base作成
18. CreateAnswer関数の環境変数にKnowledge Base ID設定

---

# 環境変数の設定

## UploadInquiry
- `TABLE_NAME` (必須): DynamoDBテーブル名（handson-table）
- `SQS_QUEUE_URL` (必須): SQSキューURL（https://sqs.us-east-1.amazonaws.com/166855511114/handson-sqs）

## ExecuteJob
- `STATE_MACHINE_ARN`: Step Function ステートマシーンのARN（arn:aws:states:us-east-1:166855511114:stateMachine:handson-stepfunction）

## JudgeCategory
- `TABLE_NAME` (必須): DynamoDBテーブル名（handson-table）
- `BEDROCK_MODEL_ID` (オプション): デフォルト anthropic.claude-3-sonnet-20240229-v1:0

## CreateAnswer
- `TABLE_NAME` (必須): DynamoDBテーブル名（handson-table）
- `BEDROCK_MODEL_ID` (オプション): デフォルト anthropic.claude-3-sonnet-20240229-v1:0
- `KNOWLEDGE_BASE_ID` (オプション): RAG用ナレッジベースID

---

# IAM権限の設定

## UploadInquiry
- DynamoDB（dynamodb:PutItem　※該当テーブルARN）
- SQS（sqs:SendMessage　※該当キューARN）
- CloudWatch Logs（logs:CreateLogStream, logs:PutLogEvents　※該当Lambda）

## ExecuteJob
- Step Functions実行権限（states:StartExecution）
- SQS（sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes）
- CloudWatch Logs関係（自動付与）

## StepFunctions State Machine
- Lambda（lambda:InvokeFunction）
- CloudWatch Logs（logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents）

## JudgeCategory
- DynamoDB（dynamodb:GetItem, dynamodb:UpdateItem ※該当テーブルARN）
- Bedrock（bedrock:InvokeModel）
- CloudWatch Logs（logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents）

## CreateAnswer
- DynamoDB（dynamodb:GetItem, dynamodb:UpdateItem ※該当テーブルARN）
- Bedrock（bedrock:InvokeModel, bedrock:Retrieve）
- CloudWatch Logs（logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents）