"""
admin_trigger.py

POST /admin/run-ai-batch のハンドラー。

フロントエンドの「AI実行ボタン」から呼び出され、
generateSpotScoreBatch Lambda を同期的に invoke して結果を返す。

処理フロー:
    1. フロントエンドから POST /admin/run-ai-batch を受信
    2. generateSpotScoreBatch Lambda を RequestResponse で同期呼び出し
    3. バッチ処理の結果をそのままフロントエンドに返却

Requirements:
    - 環境変数 BATCH_FUNCTION_NAME に呼び出し先 Lambda 名が設定済みであること
    - Lambda 実行ロールに対象 Lambda の invoke 権限があること
"""

import json
import os
import boto3

# Lambda クライアントを初期化
# リージョンは環境変数から取得（デフォルト: 東京）
lambda_client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))

# 呼び出し先バッチ Lambda の関数名
BATCH_FUNCTION = os.environ.get("BATCH_FUNCTION_NAME", "generateSpotScoreBatch")

# CORS ヘッダー（フロントエンドからのアクセスを許可）
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}


def handler(event, context):
    """generateSpotScoreBatch Lambda を同期実行してバッチ処理を開始する。

    OPTIONS リクエスト（CORS プリフライト）は即座に 200 を返す。
    POST リクエスト時は generateSpotScoreBatch を同期呼び出しし、
    バッチ処理の完了を待ってから結果をフロントエンドに返す。

    Args:
        event   (dict): API Gateway イベントオブジェクト
            httpMethod (str): HTTPメソッド（"OPTIONS" or "POST"）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict:
            成功時 200:
                {
                    "status": "completed",
                    "processedCount": int,
                    "completedAt": str
                }
            失敗時 500:
                {
                    "status": "failed",
                    "message": str  # エラー内容
                }

    Note:
        Lambda のタイムアウトは generateSpotScoreBatch の実行時間より
        長く設定すること（template.yaml で Timeout: 330 を指定済み）。
    """
    # CORS プリフライトリクエストを処理
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS, "body": ""}

    try:
        # generateSpotScoreBatch を同期呼び出し（完了まで待機）
        response = lambda_client.invoke(
            FunctionName=BATCH_FUNCTION,
            InvocationType="RequestResponse",
            Payload=json.dumps({}),
        )
        payload = json.loads(response["Payload"].read())
        body    = json.loads(payload.get("body", "{}"))
        return {
            "statusCode": 200,
            "headers": CORS,
            "body": json.dumps(body),
        }
    except Exception as e:
        print(f"Batch invoke error: {e}")
        return {
            "statusCode": 500,
            "headers": CORS,
            "body": json.dumps({"status": "failed", "message": str(e)}),
        }