"""
handlers.py

API Gateway から呼び出される Lambda ハンドラー群。

Endpoints:
    GET    /recommendations
    GET    /spots
    GET    /posts
    GET    /favorites
    POST   /favorites
    DELETE /favorites/{spotId}

Requirements:
    - 環境変数にDynamoDBテーブル名が設定済み
    - Lambda実行ロールにDynamoDBアクセス権限が必要
"""

import json
import os
import logging
from decimal import Decimal
from typing import Any, Callable

import boto3
from boto3.dynamodb.conditions import Key

# ─────────────────────────────
# logging
# ─────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─────────────────────────────
# DynamoDB
# ─────────────────────────────
dynamodb = boto3.resource(
    "dynamodb",
    region_name=os.environ.get("AWS_REGION", "ap-northeast-1")
)  # type: ignore[attr-defined]

SPOTS_TABLE = os.environ.get("SPOTS_TABLE", "fishing-spots")
RECOMMENDATIONS_TABLE = os.environ.get("RECOMMENDATIONS_TABLE", "fishing-recommendations")
FAVORITES_TABLE = os.environ.get("FAVORITES_TABLE", "fishing-favorites")
POSTS_TABLE = os.environ.get("POSTS_TABLE", "fishing-posts")


# ─────────────────────────────
# Common
# ─────────────────────────────
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
}


def _resp(status: int, body: dict[str, Any]) -> dict[str, Any]:
    """API Gateway 形式のレスポンスオブジェクトを組み立てる。

    Args:
        status (int): HTTP ステータスコード
        body (dict[str, Any]): レスポンスボディ（JSON シリアライズされる）

    Returns:
        dict[str, Any]: statusCode / headers / body を含む API Gateway レスポンス
    """
    return {
        "statusCode": status,
        "headers": CORS,
        "body": json.dumps(body, default=str),
    }


def _error_resp(e: Exception) -> dict[str, Any]:
    """例外発生時に 500 エラーレスポンスを組み立てる。

    スタックトレースを CloudWatch Logs に出力してからレスポンスを返す。

    Args:
        e (Exception): 発生した例外

    Returns:
        dict[str, Any]: statusCode=500 の API Gateway レスポンス
    """
    logger.exception("Lambda error occurred")
    return _resp(500, {"error": str(e)})


def handler_guard(fn: Callable):
    """
    全ハンドラー共通の例外ハンドリング

    各ハンドラー関数をラップし、内部で例外が発生した場合に
    500 エラーレスポンスへ変換して返す共通デコレーター。

    Args:
        fn (Callable): ラップ対象のハンドラー関数

    Returns:
        Callable: 例外ハンドリング付きのラップ済みハンドラー
    """
    def wrapper(event: dict[str, Any], context: Any):
        try:
            return fn(event, context)
        except Exception as e:
            return _error_resp(e)
    return wrapper


def _decimal_to_float(obj: Any) -> Any:
    """DynamoDB が返す Decimal 型を再帰的に float へ変換する。

    DynamoDB の数値型は Decimal で返却され、そのままでは
    json.dumps でシリアライズできないため、レスポンス生成前に変換する。

    Args:
        obj (Any): 変換対象（list / dict / Decimal / その他）

    Returns:
        Any: Decimal を float に置き換えた同じ構造のオブジェクト
    """
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


def _get_table(name: str):
    """DynamoDB テーブルオブジェクトを取得する。

    Args:
        name (str): DynamoDB テーブル名

    Returns:
        Table: boto3 の DynamoDB Table リソースオブジェクト
    """
    return dynamodb.Table(name)  # type: ignore[attr-defined]


# ─────────────────────────────
# /recommendations
# ─────────────────────────────
@handler_guard
def getRecommendationsHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """GET /recommendations — おすすめスポット一覧をスコア降順で返す。

    RecommendationsTable と SpotsTable を突き合わせ、
    各推薦データに対応するスポット情報（spot）を付与して返す。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（本エンドポイントでは未使用）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: statusCode=200、body に {"items": [...]}（スコア降順）
    """
    table_r = _get_table(RECOMMENDATIONS_TABLE)
    table_s = _get_table(SPOTS_TABLE)

    recs = table_r.scan().get("Items", [])
    # DynamoDB（NoSQL）はテーブル間JOINができないため、spotIdをキーにした辞書を作り、
    # アプリケーション側で手動で結合する
    spots = {s["spotId"]: s for s in table_s.scan().get("Items", [])}

    for rec in recs:
        rec["spot"] = spots.get(rec.get("spotId"), {})

    # スコア降順（高いほど先頭）。フロント側で上位3件をTOP3として強調表示する
    recs_sorted = sorted(
        recs,
        key=lambda x: float(x.get("score", 0)),
        reverse=True
    )

    return _resp(200, {"items": _decimal_to_float(recs_sorted)})


# ─────────────────────────────
# /spots
# ─────────────────────────────
@handler_guard
def getSpotsHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """GET /spots — 全釣りスポット一覧を返す。

    SpotsTable を全件スキャンして返却する。並び順は保証されない。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（本エンドポイントでは未使用）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: statusCode=200、body に {"items": [...]}
    """
    table = _get_table(SPOTS_TABLE)
    items = table.scan().get("Items", [])
    return _resp(200, {"items": _decimal_to_float(items)})


# ─────────────────────────────
# /posts
# ─────────────────────────────
@handler_guard
def getPostsHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """GET /posts — 投稿一覧を新しい順で返す。

    PostsTable を全件スキャンし、createdAt の降順（新しい順）にソートして返す。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（本エンドポイントでは未使用）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: statusCode=200、body に {"items": [...]}（createdAt 降順）
    """
    table = _get_table(POSTS_TABLE)
    items = table.scan().get("Items", [])

    items_sorted = sorted(
        items,
        key=lambda x: x.get("createdAt", ""),
        reverse=True
    )

    return _resp(200, {"items": _decimal_to_float(items_sorted)})


# ─────────────────────────────
# /favorites (GET)
# ─────────────────────────────
@handler_guard
def getFavoritesHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """GET /favorites — 指定ユーザーのお気に入り一覧を返す。

    クエリパラメータ userId でお気に入りを絞り込み、
    各お気に入りレコードに対応するスポット情報（spot）を付与して返す。
    userId 未指定時は固定ユーザー "user-001" を使用する（個人利用想定）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            queryStringParameters.userId (str, optional): 対象ユーザーID
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: statusCode=200、body に {"items": [...]}
    """
    qs = event.get("queryStringParameters") or {}
    user_id = qs.get("userId", "user-001")

    table_f = _get_table(FAVORITES_TABLE)
    table_s = _get_table(SPOTS_TABLE)

    resp = table_f.query(
        KeyConditionExpression=Key("userId").eq(user_id)
    )

    items = resp.get("Items", [])
    spots = {s["spotId"]: s for s in table_s.scan().get("Items", [])}

    for item in items:
        item["spot"] = spots.get(item.get("spotId"), {})

    return _resp(200, {"items": _decimal_to_float(items)})


# ─────────────────────────────
# /favorites (POST)
# ─────────────────────────────
@handler_guard
def postFavoritesHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """POST /favorites — お気に入りスポットを追加する。

    リクエストボディの spotId を FavoritesTable に登録する。
    同一の userId + spotId が既に存在する場合は上書きされる（冪等性あり）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            body (str): JSON文字列。userId(省略可) / spotId(必須) / memo(省略可) を含む
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 201: {"message": "created"}
            spotId 未指定時 400: {"error": "spotId is required"}
    """
    body = json.loads(event.get("body") or "{}")

    user_id = body.get("userId", "user-001")
    spot_id = body.get("spotId")
    memo = body.get("memo", "")

    if not spot_id:
        return _resp(400, {"error": "spotId is required"})

    table = _get_table(FAVORITES_TABLE)

    table.put_item(Item={
        "userId": user_id,
        "spotId": spot_id,
        "memo": memo
    })

    return _resp(201, {"message": "created"})


# ─────────────────────────────
# /favorites/{spotId} (DELETE)
# ─────────────────────────────
@handler_guard
def deleteFavoritesHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """DELETE /favorites/{spotId} — お気に入りスポットを削除する。

    パスパラメータ spotId とクエリパラメータ userId の組み合わせで
    FavoritesTable から該当レコードを削除する。
    userId 未指定時は固定ユーザー "user-001" を使用する（個人利用想定）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            pathParameters.spotId (str): 削除対象のスポットID
            queryStringParameters.userId (str, optional): 対象ユーザーID
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"message": "deleted"}
            spotId 未指定時 400: {"error": "spotId is required"}
    """
    spot_id = (event.get("pathParameters") or {}).get("spotId")
    qs = event.get("queryStringParameters") or {}
    user_id = qs.get("userId", "user-001")

    if not spot_id:
        return _resp(400, {"error": "spotId is required"})

    table = _get_table(FAVORITES_TABLE)

    table.delete_item(
        Key={
            "userId": user_id,
            "spotId": spot_id
        }
    )

    return _resp(200, {"message": "deleted"})