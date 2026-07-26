"""
admin_trigger.py

POST /admin/run-ai-batch のハンドラー。

フロントエンドの「AI実行ボタン」から呼び出され、
generateSpotScoreBatch Lambda を非同期に invoke してすぐに応答を返す。

処理フロー:
    1. フロントエンドから POST /admin/run-ai-batch （または /admin/run-spot-discovery）を受信
    2. 呼び出し先 Lambda（BATCH_FUNCTION_NAME環境変数で切り替え）を Event（非同期）で invoke
       このときリクエストボディをそのまま呼び出し先の event としてそのまま渡す
       （例: 「現在地から探す」ボタンから { lat, lng } が渡された場合、discoverSpotsBatch の
        event.lat / event.lng としてそのまま受け取れる）
    3. 呼び出しを受け付けた旨を即座にフロントエンドへ返却
    4. フロントエンドは GET /recommendations をポーリングして完了を検知する（AI分析実行時のみ）

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

2026-07-26追加: このLambdaはPlaces/Gemini APIを呼ぶバッチ処理を起動するため、
コスト保護のため1ユーザー1日あたりの起動回数に上限を設けている（handlers.pyの
postChatHandlerと同じ思想）。admin_trigger.pyはAI分析実行・現在地から探すの
両方で共用されているため、環境変数 RATE_LIMIT_ACTION / RATE_LIMIT_DAILY で
それぞれ別カウンタ・別上限を指定できるようにしている。
"""

import json
import os
from datetime import datetime, timezone

import boto3

from batch_common import check_and_increment_daily_usage, get_user_id

# Lambda クライアントを初期化
# リージョンは環境変数から取得（デフォルト: 東京）
lambda_client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))

# 呼び出し先バッチ Lambda の関数名
BATCH_FUNCTION = os.environ.get("BATCH_FUNCTION_NAME", "generateSpotScoreBatch")

# レート制限用のアクション名・1日あたり上限（関数ごとにtemplate.yamlで設定）
RATE_LIMIT_ACTION = os.environ.get("RATE_LIMIT_ACTION", "admin-trigger")
RATE_LIMIT_DAILY = int(os.environ.get("RATE_LIMIT_DAILY", "10"))

# CORS ヘッダー（フロントエンドからのアクセスを許可）
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
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
            本日の利用上限に達している場合 429:
                {
                    "status": "rate_limited",
                    "message": str
                }
    """
    # CORS プリフライトリクエストを処理
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS, "body": ""}

    # Places/Gemini API呼び出しを伴うバッチのコスト保護（2026-07-26追加）
    user_id = get_user_id(event)
    if not check_and_increment_daily_usage(user_id, RATE_LIMIT_ACTION, RATE_LIMIT_DAILY):
        return {
            "statusCode": 429,
            "headers": CORS,
            "body": json.dumps({
                "status": "rate_limited",
                "message": f"本日の利用回数（{RATE_LIMIT_DAILY}件）に達しました。明日またお試しください。",
            }),
        }

    try:
        # リクエストボディをそのまま呼び出し先Lambdaのeventとして転送する
        # （「現在地から探す」ボタンの lat/lng など、呼び出し先が使うパラメータを素通しする）
        payload = event.get("body") or "{}"

        # 非同期呼び出し（応答を待たずに起動だけ行う）
        lambda_client.invoke(
            FunctionName=BATCH_FUNCTION,
            InvocationType="Event",
            Payload=payload,
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
