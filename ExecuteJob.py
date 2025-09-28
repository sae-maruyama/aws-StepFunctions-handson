import json
import boto3
import os

def lambda_handler(event, context):
    """
    SQSトリガーでStepFunctionsを実行するLambda関数
    """
    # SQSメッセージの処理（複数メッセージに対応）
    for record in event['Records']:
        try:
            # SQSメッセージのbodyをパース
            message_body = json.loads(record['body'])
            
            # idパラメータの検証
            if 'id' not in message_body or not message_body['id']:
                print(f"Error: Missing required parameter 'id' in message: {message_body}")
                continue
            
            inquiry_id = message_body['id']
            
            # Step Functions クライアントの初期化
            stepfunctions_client = boto3.client('stepfunctions')
            
            # 環境変数からStep FunctionsのARNを取得
            state_machine_arn = os.environ.get('STATE_MACHINE_ARN')
            if not state_machine_arn:
                print("Error: STATE_MACHINE_ARN environment variable not set")
                continue
            
            # Step Functions実行用の入力パラメータ
            execution_input = {
                'id': inquiry_id
            }
            
            # Step Functionsを実行
            response = stepfunctions_client.start_execution(
                stateMachineArn=state_machine_arn,
                name=f"inquiry-processing-{inquiry_id}",
                input=json.dumps(execution_input)
            )
            
            print(f"Successfully started Step Functions execution for inquiry ID: {inquiry_id}")
            print(f"Execution ARN: {response['executionArn']}")
            
        except json.JSONDecodeError as e:
            print(f"Error parsing SQS message body: {str(e)}")
            continue
        except Exception as e:
            print(f"Error processing SQS record: {str(e)}")
            continue
    
    return {
        'statusCode': 200,
        'body': json.dumps('SQS messages processed successfully')
    }