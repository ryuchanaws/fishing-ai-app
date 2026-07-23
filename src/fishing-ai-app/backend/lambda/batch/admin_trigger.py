"""
admin_trigger.py

POST /admin/run-ai-batch のハンドラー。

フロントエンドの「AI実行ボタン」から呼び出され、
generateSpotScoreBatch Lambda を非同期に invoke してすぐに応答を返す。

処理フロー:
    1. フロントエンドから POST /admin/run-ai-batch を受信
    2. generateSpotScoreBatch Lambda を Event（非同期）で invoke
    3. 呼び出しを受け付けた旨を即座にフロントエンドへ返却
    4. フロントエンドは GET /recommendations をポーリングして完了を検知する

Note:
    以前は InvocationType="RequestResponse" で同期呼び出しし、
    バッチ完了まで待ってから結果を返していた。しかし API Gateway
    (REST API) の統合タイムアウトは 29 秒が上限で、Gemini API 呼び出しを
    含むバッチ処理（5スポット分）はこれを超えることがあり、Lambda自体は
    成功しているのに API Gateway 側が 504 Timeout を返す問題があった。
    非同期呼び出しに変更し即座に応答することでこの問題を回避している。

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
    """generateSpotScoreBatch Lambda を非同期起動し、即座に受付応答を返す。

    OPTIONS リクエスト（CORS プリフライト）は即座に 200 を返す。
    POST リクエスト時は generateSpotScoreBatch を非同期呼び出し（Event）し、
    完了を待たずに「受け付けた」旨のレスポンスを返す。
    実際の完了確認はフロントエンド側で GET /recommendations をポーリングして行う。

    Args:
        event   (dict): API Gateway イベントオブジェクト
            httpMethod (str): HTTPメソッド（"OPTIONS" or "POST"）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict:
            受付成功時 202:
                {
                    "status": "started",
                    "startedAt": str  # ISO 8601
                }
            起動失敗時 500:
                {
                    "status": "failed",
                    "message": str  # エラー内容
                }
    """
    # CORS プリフライトリクエストを処理
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS, "body": ""}

    from datetime import datetime, timezone

    try:
        # generateSpotScoreBatch を非同期呼び出し（応答を待たずに起動だけ行う）
        lambda_client.invoke(
            FunctionName=BATCH_FUNCTION,
            InvocationType="Event",
            Payload=json.dumps({}),
        )
        body = {
            "status": "started",
            "startedAt": datetime.now(timezone.utc).isoformat(),
        }
        return {
            "statusCode": 202,
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
