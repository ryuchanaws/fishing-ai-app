"""
handlers.py

API Gateway から呼び出される Lambda ハンドラー群。
以下のエンドポイントに対応する:

    GET    /recommendations       : おすすめスポット一覧取得
    GET    /spots                 : 全スポット一覧取得
    GET    /posts                 : 投稿一覧取得
    GET    /favorites             : お気に入り一覧取得
    POST   /favorites             : お気に入り追加
    DELETE /favorites/{spotId}    : お気に入り削除

Requirements:
    - 環境変数に各DynamoDBテーブル名が設定済みであること
    - Lambda実行ロールにDynamoDBへのアクセス権限があること
"""

# pyright: basic
import json
import os
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

# DynamoDB リソースを初期化
# リージョンは環境変数から取得（デフォルト: 東京）
# type: ignore はPylanceの型スタブ制限による誤検知を抑制
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))  # type: ignore[attr-defined]

# 各DynamoDBテーブル名を環境変数から取得
# 環境変数が未設定の場合はデフォルト値を使用
SPOTS_TABLE           = os.environ.get("SPOTS_TABLE", "fishing-spots")
RECOMMENDATIONS_TABLE = os.environ.get("RECOMMENDATIONS_TABLE", "fishing-recommendations")
FAVORITES_TABLE       = os.environ.get("FAVORITES_TABLE", "fishing-favorites")
POSTS_TABLE           = os.environ.get("POSTS_TABLE", "fishing-posts")

# CORS ヘッダー
# フロントエンド（S3/CloudFront）からのアクセスを許可するために全オリジンを許可
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
}


def _resp(status: int, body: dict[str, Any]) -> dict[str, Any]:
    """API Gateway 形式のレスポンスを生成する。

    Args:
        status (int): HTTPステータスコード（例: 200, 201, 400）
        body (dict[str, Any]): レスポンスボディ（dict形式）

    Returns:
        dict[str, Any]: statusCode・headers・body を含む API Gateway レスポンス
    """
    return {"statusCode": status, "headers": CORS, "body": json.dumps(body, default=str)}


def _decimal_to_float(obj: Any) -> Any:
    """DynamoDB から取得した Decimal 型を float に再帰的に変換する。

    DynamoDB は数値を Decimal 型で返すため、
    JSON シリアライズ前にこの関数で float に変換する必要がある。

    Args:
        obj (Any): 変換対象のオブジェクト（list / dict / Decimal / その他）

    Returns:
        Any: Decimal を float に変換したオブジェクト
    """
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


def _get_table(name: str):  # type: ignore[return]
    """DynamoDB テーブルオブジェクトを取得する。

    Pylance の型スタブ制限による誤検知を1箇所に集約するためのヘルパー関数。

    Args:
        name (str): DynamoDB テーブル名

    Returns:
        boto3.resources.factory.dynamodb.Table: DynamoDB テーブルオブジェクト
    """
    return dynamodb.Table(name)  # type: ignore[attr-defined]


# ─── GET /recommendations ───────────────────────────────────────────
def get_recommendations(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """おすすめスポット一覧をスコア降順で返す。

    Recommendations テーブルの全レコードを取得し、
    各レコードに対応する Spots テーブルの情報を結合して返す。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: スコア降順にソートされたおすすめスポットリスト
            {
                "items": [
                    {
                        "spotId": str,
                        "score": float,
                        "fishTypes": list[str],
                        "reason": str,
                        "spot": dict  # Spots テーブルから結合
                    },
                    ...
                ]
            }
    """
    table_r = _get_table(RECOMMENDATIONS_TABLE)
    table_s = _get_table(SPOTS_TABLE)

    recs: list[dict[str, Any]] = table_r.scan()["Items"]
    spots: dict[str, Any] = {s["spotId"]: s for s in table_s.scan()["Items"]}

    for rec in recs:
        rec["spot"] = spots.get(rec["spotId"], {})

    recs_sorted = sorted(recs, key=lambda x: float(x.get("score", 0)), reverse=True)
    return _resp(200, {"items": _decimal_to_float(recs_sorted)})


# ─── GET /spots ─────────────────────────────────────────────────────
def get_spots(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """全釣りスポット一覧を返す。

    Spots テーブルの全レコードを取得して返す。
    地図画面やスポット一覧画面で使用する。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: 全スポットリスト
            {
                "items": [
                    {
                        "spotId": str,
                        "name": str,
                        "lat": float,
                        "lng": float
                    },
                    ...
                ]
            }
    """
    table = _get_table(SPOTS_TABLE)
    items: list[dict[str, Any]] = table.scan()["Items"]
    return _resp(200, {"items": _decimal_to_float(items)})


# ─── GET /posts ─────────────────────────────────────────────────────
def get_posts(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """投稿一覧を作成日時降順で返す。

    Posts テーブルの全レコードを取得し、
    createdAt フィールドの降順（新しい順）にソートして返す。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: 新しい順にソートされた投稿リスト
            {
                "items": [
                    {
                        "postId": str,
                        "spotId": str,
                        "content": str,
                        "createdAt": str
                    },
                    ...
                ]
            }
    """
    table = _get_table(POSTS_TABLE)
    items: list[dict[str, Any]] = table.scan()["Items"]
    items_sorted = sorted(items, key=lambda x: x.get("createdAt", ""), reverse=True)
    return _resp(200, {"items": _decimal_to_float(items_sorted)})


# ─── GET /favorites ─────────────────────────────────────────────────
def get_favorites(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """指定ユーザーのお気に入りスポット一覧を返す。

    クエリパラメータ userId に紐づくお気に入りを取得し、
    各レコードに対応する Spots テーブルの情報を結合して返す。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            queryStringParameters.userId (str): ユーザーID（省略時: "user-001"）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: お気に入りスポットリスト
            {
                "items": [
                    {
                        "userId": str,
                        "spotId": str,
                        "memo": str,
                        "spot": dict  # Spots テーブルから結合
                    },
                    ...
                ]
            }
    """
    qs = event.get("queryStringParameters") or {}
    user_id: str = qs.get("userId", "user-001")

    table_f = _get_table(FAVORITES_TABLE)
    table_s = _get_table(SPOTS_TABLE)

    resp = table_f.query(KeyConditionExpression=Key("userId").eq(user_id))
    items: list[dict[str, Any]] = resp["Items"]
    spots: dict[str, Any] = {s["spotId"]: s for s in table_s.scan()["Items"]}

    for item in items:
        item["spot"] = spots.get(item["spotId"], {})

    return _resp(200, {"items": _decimal_to_float(items)})


# ─── POST /favorites ────────────────────────────────────────────────
def create_favorite(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """お気に入りスポットを追加する。

    リクエストボディの userId・spotId・memo を Favorites テーブルに保存する。
    同一の userId + spotId が既に存在する場合は上書きされる（冪等性あり）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            body.userId (str): ユーザーID（省略時: "user-001"）
            body.spotId (str): スポットID（必須）
            body.memo   (str): メモ（省略可）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 201: {"message": "created"}
            失敗時 400: {"error": "spotId is required"}
    """
    body: dict[str, Any] = json.loads(event.get("body", "{}") or "{}")
    user_id: str = body.get("userId", "user-001")
    spot_id: str | None = body.get("spotId")
    memo: str = body.get("memo", "")

    if not spot_id:
        return _resp(400, {"error": "spotId is required"})

    table = _get_table(FAVORITES_TABLE)
    table.put_item(Item={"userId": user_id, "spotId": spot_id, "memo": memo})
    return _resp(201, {"message": "created"})


# ─── DELETE /favorites/{spotId} ─────────────────────────────────────
def delete_favorite(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """お気に入りスポットを削除する。

    パスパラメータ spotId とクエリパラメータ userId に紐づく
    お気に入りレコードを Favorites テーブルから削除する。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            pathParameters.spotId       (str): 削除対象のスポットID（必須）
            queryStringParameters.userId (str): ユーザーID（省略時: "user-001"）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"message": "deleted"}
            失敗時 400: {"error": "spotId is required"}
    """
    spot_id: str | None = (event.get("pathParameters") or {}).get("spotId")
    qs: dict[str, Any] = event.get("queryStringParameters") or {}
    user_id: str = qs.get("userId", "user-001")

    if not spot_id:
        return _resp(400, {"error": "spotId is required"})

    table = _get_table(FAVORITES_TABLE)
    table.delete_item(Key={"userId": user_id, "spotId": spot_id})
    return _resp(200, {"message": "deleted"})