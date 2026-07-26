"""
handlers.py

API Gateway から呼び出される Lambda ハンドラー群。

Endpoints:
    GET    /recommendations
    GET    /spots
    PUT    /spots/{spotId}/image
    GET    /posts
    POST   /posts
    PUT    /posts/{postId}
    DELETE /posts/{postId}
    GET    /favorites
    POST   /favorites
    DELETE /favorites/{spotId}
    POST   /uploads/presign
    POST   /chat
    GET    /chats
    GET    /chats/{chatId}
    DELETE /chats/{chatId}
    GET    /me
    PUT    /me

Requirements:
    - 環境変数にDynamoDBテーブル名が設定済み
    - Lambda実行ロールにDynamoDBアクセス権限が必要
"""

import json
import math
import os
import uuid
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

import base64

import boto3
import anthropic
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

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
CHATS_TABLE = os.environ.get("CHATS_TABLE", "fishing-chats")
USAGE_TABLE = os.environ.get("USAGE_TABLE", "fishing-usage")
# ユーザーが自分で設定する表示名（ユーザー名）を保存するテーブル（2026-07-26追加）
USERS_TABLE = os.environ.get("USERS_TABLE", "fishing-users")

# ─────────────────────────────
# S3（スポット写真・投稿写真のアップロード先）
# ─────────────────────────────
s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))
UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "")
PRESIGNED_URL_EXPIRES_SEC = 300  # 署名付きURLの有効期限（5分）

# アップロード可能な画像形式とその拡張子（想定外の形式のアップロードを防ぐ）
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

# アップロード可能な画像の最大サイズ（バイト）。generate_presigned_post の
# content-length-range 条件でS3側に強制させる。フロント側（api/client.ts）にも
# 同じ値を定義しており、アップロード試行前の早期エラー表示に使っている
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8MB

# ─────────────────────────────
# SSM（Anthropic APIキー。postChatHandlerのAIチャット応答生成に使用）
# ─────────────────────────────
ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))
# "/"を含む階層型のSSMパラメータ名は先頭スラッシュ必須（AWSの仕様。generate_score.pyと同じ注意点）
ANTHROPIC_API_KEY_PARAM = "/fishing-ai/anthropic-api-key"

# Claude Haiku（低コスト・高速なモデル）を使用。詳細設計.html参照
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# 直近何往復分の会話をClaudeに渡すか（トークン量とレイテンシを抑えるための上限）
CHAT_HISTORY_LIMIT = 10
# Cognito未対応のエンドポイント・オーソライザーを未通過のリクエスト向けフォールバック
# （2026-07-26時点では認証必須エンドポイントは全てCognitoAuthorizerを通るため実質使われない）
DEFAULT_USER_ID = "user-001"

# 1ユーザーが1日に送れるAIチャットメッセージ数の上限。Claude呼び出しコストを抑えるための
# 簡易レート制限（2026-07-26追加。友人にアプリを共有したことで複数人が使うようになったため）
DAILY_CHAT_LIMIT = 30


def _get_user_id(event: dict[str, Any]) -> str:
    """Cognitoオーソライザーが付与したクレームから実ユーザーIDを取得する。

    API Gateway が CognitoAuthorizer を通過させたリクエストには
    event.requestContext.authorizer.claims.sub にユーザーの一意なID（sub）が入る。
    オーソライザーを経由していないエンドポイント（保護対象外）や、テスト等で
    claims が無い場合は DEFAULT_USER_ID にフォールバックする。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト

    Returns:
        str: Cognitoのsub（ユーザー識別子）。取得できない場合は DEFAULT_USER_ID
    """
    claims = ((event.get("requestContext") or {}).get("authorizer") or {}).get("claims") or {}
    return claims.get("sub", DEFAULT_USER_ID)


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
    各投稿にはUsersTableと突き合わせた投稿者の表示名（authorName）を付与する
    （2026-07-26追加。投稿時点でフリーズさせず、表示のたびに最新の表示名を反映する。
    SpotsTable/FavoritesTableの結合と同じ「NoSQLはJOINできないのでアプリ側で辞書を作って結合」パターン。
    表示名未設定のユーザーは"匿名"として表示する）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（本エンドポイントでは未使用）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: statusCode=200、body に {"items": [...]}（createdAt 降順、各itemにauthorName付き）
    """
    table = _get_table(POSTS_TABLE)
    table_u = _get_table(USERS_TABLE)
    items = table.scan().get("Items", [])

    users = {u["userId"]: u for u in table_u.scan().get("Items", [])}
    for item in items:
        user = users.get(item.get("userId"))
        item["authorName"] = (user.get("displayName") if user else None) or "匿名"

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
    """GET /favorites — ログイン中ユーザーのお気に入り一覧を返す。

    各お気に入りレコードに対応するスポット情報（spot）を付与して返す。
    userIdはCognito認証のクレームから取得する（2026-07-26: クエリパラメータでの
    指定を廃止。他人のuserIdを指定して覗き見できてしまう問題があったため）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（Cognito認証必須）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: statusCode=200、body に {"items": [...]}
    """
    user_id = _get_user_id(event)

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
    userIdはCognito認証のクレームから取得する（リクエストボディでの指定は無視する。
    他人になりすまして登録できてしまう問題を防ぐため）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（Cognito認証必須）
            body (str): JSON文字列。spotId(必須) / memo(省略可) を含む
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 201: {"message": "created"}
            spotId 未指定時 400: {"error": "spotId is required"}
    """
    body = json.loads(event.get("body") or "{}")

    user_id = _get_user_id(event)
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

    パスパラメータ spotId とCognito認証のクレームから得たuserIdの組み合わせで
    FavoritesTable から該当レコードを削除する（userIdはFavoritesのpartition keyの
    一部なので、他人のuserIdでは元々そのレコードにアクセスできない）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（Cognito認証必須）
            pathParameters.spotId (str): 削除対象のスポットID
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"message": "deleted"}
            spotId 未指定時 400: {"error": "spotId is required"}
    """
    spot_id = (event.get("pathParameters") or {}).get("spotId")
    user_id = _get_user_id(event)

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


# ─────────────────────────────
# /posts (POST)
# ─────────────────────────────
@handler_guard
def postPostsHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """POST /posts — 釣果投稿を作成する。

    リクエストボディの spotId / content を PostsTable に登録する。
    postId はサーバー側で uuid4 を採番し、createdAt は現在時刻を設定する。
    userIdはCognito認証のクレームから取得する（リクエストボディでの指定は無視する。
    他人になりすまして投稿できてしまう問題を防ぐため）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（Cognito認証必須）
            body (str): JSON文字列。spotId(必須) / content(必須) /
                imageUrl(省略可) / fishCaught(省略可) を含む
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 201: {"message": "created", "post": {...}}
            spotId/content 未指定時 400: {"error": "..."}
    """
    body = json.loads(event.get("body") or "{}")

    spot_id = body.get("spotId")
    content = body.get("content")

    if not spot_id or not content:
        return _resp(400, {"error": "spotId and content are required"})

    post = {
        "postId": str(uuid.uuid4()),
        "spotId": spot_id,
        "userId": _get_user_id(event),
        "content": content,
        "imageUrl": body.get("imageUrl", ""),
        "fishCaught": body.get("fishCaught", []),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    table = _get_table(POSTS_TABLE)
    table.put_item(Item=post)

    return _resp(201, {"message": "created", "post": post})


# ─────────────────────────────
# /posts/{postId} (DELETE)
# ─────────────────────────────
@handler_guard
def deletePostHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """DELETE /posts/{postId} — 釣果投稿を削除する。

    PostsTableはpostId単一PKで所有者情報がキーに含まれないため、Favorites/Chatsと
    異なり明示的な所有者チェックが必要（2026-07-26追加）。削除前に投稿を取得し、
    投稿のuserIdとリクエスト元のuserIdが一致しない場合は403を返す。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（Cognito認証必須）
            pathParameters.postId (str): 削除対象の投稿ID
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"message": "deleted"}
            postId 未指定時 400: {"error": "postId is required"}
            投稿が存在しない場合 404: {"error": "post not found"}
            自分の投稿でない場合 403: {"error": "forbidden"}
    """
    post_id = (event.get("pathParameters") or {}).get("postId")

    if not post_id:
        return _resp(400, {"error": "postId is required"})

    table = _get_table(POSTS_TABLE)
    item = table.get_item(Key={"postId": post_id}).get("Item")

    if not item:
        return _resp(404, {"error": "post not found"})

    if item.get("userId") != _get_user_id(event):
        return _resp(403, {"error": "forbidden"})

    table.delete_item(Key={"postId": post_id})

    return _resp(200, {"message": "deleted"})


# ─────────────────────────────
# /posts/{postId} (PUT)
# ─────────────────────────────
@handler_guard
def putPostHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """PUT /posts/{postId} — 釣果投稿を編集する（2026-07-26追加）。

    本文・釣れた魚種・画像URLを更新できる。所有者チェックはdeletePostHandlerと同じ理由・
    同じ実装（postId単一PKで所有者情報がキーに無いため、更新前にget_itemして
    自分の投稿か明示チェックする）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（Cognito認証必須）
            pathParameters.postId (str): 編集対象の投稿ID
            body (str): JSON文字列。content(省略可) / imageUrl(省略可) / fishCaught(省略可)。
                指定されたフィールドのみ更新する
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"message": "updated", "post": {...}}
            postId 未指定時 400: {"error": "postId is required"}
            content が空文字のとき 400: {"error": "content must not be empty"}
            投稿が存在しない場合 404: {"error": "post not found"}
            自分の投稿でない場合 403: {"error": "forbidden"}
    """
    post_id = (event.get("pathParameters") or {}).get("postId")

    if not post_id:
        return _resp(400, {"error": "postId is required"})

    body = json.loads(event.get("body") or "{}")

    table = _get_table(POSTS_TABLE)
    item = table.get_item(Key={"postId": post_id}).get("Item")

    if not item:
        return _resp(404, {"error": "post not found"})

    if item.get("userId") != _get_user_id(event):
        return _resp(403, {"error": "forbidden"})

    if "content" in body:
        content = (body.get("content") or "").strip()
        if not content:
            return _resp(400, {"error": "content must not be empty"})
        item["content"] = content
    if "imageUrl" in body:
        item["imageUrl"] = body.get("imageUrl", "")
    if "fishCaught" in body:
        item["fishCaught"] = body.get("fishCaught", [])

    item["updatedAt"] = datetime.now(timezone.utc).isoformat()

    table.put_item(Item=item)

    return _resp(200, {"message": "updated", "post": _decimal_to_float(item)})


# ─────────────────────────────
# /spots/{spotId}/image (PUT)
# ─────────────────────────────
@handler_guard
def putSpotImageHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """PUT /spots/{spotId}/image — スポットの写真URLを設定する。

    DetailModal からのアップロード完了後に呼び出され、
    SpotsTable の該当レコードの imageUrl 属性を更新する。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            pathParameters.spotId (str): 対象スポットID
            body (str): JSON文字列。imageUrl(必須) を含む
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"message": "updated"}
            spotId/imageUrl 未指定時 400: {"error": "..."}
    """
    spot_id = (event.get("pathParameters") or {}).get("spotId")
    body = json.loads(event.get("body") or "{}")
    image_url = body.get("imageUrl")

    if not spot_id or not image_url:
        return _resp(400, {"error": "spotId and imageUrl are required"})

    table = _get_table(SPOTS_TABLE)
    table.update_item(
        Key={"spotId": spot_id},
        UpdateExpression="SET imageUrl = :imageUrl",
        ExpressionAttributeValues={":imageUrl": image_url},
    )

    return _resp(200, {"message": "updated"})


# ─────────────────────────────
# /uploads/presign (POST)
# ─────────────────────────────
@handler_guard
def postPresignUploadHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """POST /uploads/presign — S3への直接アップロード用の署名付きPOSTフォームを発行する。

    フロントエンドはこのAPIで受け取った uploadUrl + uploadFields を使って
    multipart/form-data のPOSTでS3へ直接アップロードする
    （Lambda/API Gatewayを経由させないことでペイロードサイズ制限を回避する）。
    アップロード完了後は publicUrl を Post.imageUrl / Spot.imageUrl として保存する。

    2026-07-25: 単純な署名付きPUT URL（generate_presigned_url）から
    署名付きPOSTフォーム（generate_presigned_post）に変更した。PUT URLはURL自体に
    サイズ制限を埋め込めず、悪意あるクライアントが任意サイズをアップロードできてしまう。
    POSTフォームは Conditions に content-length-range を指定でき、S3側がその条件を
    満たさないアップロードを拒否するため、アップロード上限をサーバー側で強制できる。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            body (str): JSON文字列。contentType(省略可、デフォルト image/jpeg) を含む
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"uploadUrl": str, "uploadFields": dict, "publicUrl": str}
            未対応の画像形式時 400: {"error": "..."}
    """
    body = json.loads(event.get("body") or "{}")
    content_type = body.get("contentType", "image/jpeg")

    ext = ALLOWED_CONTENT_TYPES.get(content_type)
    if not ext:
        return _resp(400, {"error": f"unsupported contentType: {content_type}"})

    key = f"uploads/{uuid.uuid4()}.{ext}"

    presigned = s3.generate_presigned_post(
        Bucket=UPLOADS_BUCKET,
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            # 1バイト〜MAX_UPLOAD_BYTES の範囲外はS3側が413相当のエラーで拒否する
            ["content-length-range", 1, MAX_UPLOAD_BYTES],
        ],
        ExpiresIn=PRESIGNED_URL_EXPIRES_SEC,
    )
    public_url = f"https://{UPLOADS_BUCKET}.s3.{os.environ.get('AWS_REGION', 'ap-northeast-1')}.amazonaws.com/{key}"

    return _resp(200, {
        "uploadUrl": presigned["url"],
        "uploadFields": presigned["fields"],
        "publicUrl": public_url,
    })


# ─────────────────────────────
# レート制限（AIチャットの1日あたり利用回数）
# ─────────────────────────────
def _check_and_increment_daily_usage(user_id: str, action: str, limit: int) -> bool:
    """指定ユーザー・アクションの当日の利用回数をアトミックに加算し、上限内かどうかを返す。

    UsageTable（userId + dateKey）に対して ADD で単純加算する。DynamoDBのADDは
    アトミックなため、同時リクエストが来ても加算漏れは起きない。項目にはTTL
    （翌々日0時ごろ）を設定しており、DynamoDB側で自動的に古いカウンタが削除される。

    Args:
        user_id (str): 対象ユーザーID（Cognitoのsub）
        action  (str): アクション種別（例: "chat"）。dateKeyのプレフィックスに使う
        limit   (int): 1日あたりの上限回数

    Returns:
        bool: 上限内（呼び出しを継続してよい）なら True、上限超過なら False
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_key = f"{action}#{today}"
    # 翌々日0時（UTC）を目安にTTLで自動削除させる
    expires_at = int(datetime.now(timezone.utc).timestamp()) + 2 * 24 * 60 * 60

    table = _get_table(USAGE_TABLE)
    result = table.update_item(
        Key={"userId": user_id, "dateKey": date_key},
        UpdateExpression="ADD #c :inc SET expiresAt = if_not_exists(expiresAt, :exp)",
        ExpressionAttributeNames={"#c": "count"},
        ExpressionAttributeValues={":inc": 1, ":exp": expires_at},
        ReturnValues="UPDATED_NEW",
    )
    current_count = int(result["Attributes"]["count"])
    return current_count <= limit


# ─────────────────────────────
# AIチャット共通ヘルパー
# ─────────────────────────────
def _get_anthropic_api_key() -> str:
    """SSM Parameter StoreからAnthropic APIキーを取得する（generate_score.pyと同じパターン）。"""
    try:
        response = ssm.get_parameter(Name=ANTHROPIC_API_KEY_PARAM, WithDecryption=True)
        return response["Parameter"]["Value"]
    except ClientError as e:
        print(f"SSM get_parameter error: {e}")
        return ""


def _fetch_image_bytes(image_url: str) -> tuple[bytes, str] | None:
    """S3公開URLからオブジェクトキーを抽出し、画像バイトを取得する。

    Args:
        image_url (str): アップロード済み画像の公開URL（UploadsBucket配下）

    Returns:
        tuple[bytes, str] | None: (画像バイト列, Content-Type)。取得失敗時は None
    """
    try:
        key = urlparse(image_url).path.lstrip("/")
        obj = s3.get_object(Bucket=UPLOADS_BUCKET, Key=key)
        return obj["Body"].read(), obj.get("ContentType", "image/jpeg")
    except Exception as e:
        print(f"S3 get_object error for chat image: {e}")
        return None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """2点間の距離をhaversine公式でkm単位で算出する（discover_spots.pyと同じ実装）。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# チャットのプロンプトに埋め込むスポット数の上限。スポットが増えてもClaude呼び出しの
# トークン量（＝コスト）が際限なく増えないようにするための上限（2026-07-26追加）
SPOTS_CONTEXT_LIMIT = 40


def _build_spots_context(user_lat: float | None = None, user_lng: float | None = None) -> str:
    """AI相談のプロンプトに埋め込む、実際のSpots/Recommendationsデータのコンパクトな要約を作る。

    discover_spots.pyが「座標などの実在情報はPlaces APIのみを採用しClaudeに生成させない」
    という方針を取っているのと同じ考え方で、チャットについても実データをそのまま渡すことで
    Claudeが存在しない釣り場を作り出す（ハルシネーション）のを防ぐ（2026-07-26追加）。

    Args:
        user_lat (float | None): ユーザーの現在地の緯度（省略可）
        user_lng (float | None): ユーザーの現在地の経度（省略可）

    Returns:
        str: 箇条書きテキスト。スポットが1件も無い場合は空文字列
    """
    table_s = _get_table(SPOTS_TABLE)
    table_r = _get_table(RECOMMENDATIONS_TABLE)

    spots = table_s.scan().get("Items", [])
    recs = {r["spotId"]: r for r in table_r.scan().get("Items", [])}

    rows = []
    for s in spots:
        rec = recs.get(s.get("spotId"), {})
        row: dict[str, Any] = {
            "name": s.get("name", "名称不明"),
            "place": s.get("prefecture") or s.get("description", ""),
            "fishTypes": s.get("fishTypes", []),
            "score": float(rec.get("score", 0)),
        }
        if user_lat is not None and user_lng is not None and "lat" in s and "lng" in s:
            row["distanceKm"] = round(_haversine_km(user_lat, user_lng, float(s["lat"]), float(s["lng"])), 1)
        rows.append(row)

    # 現在地が分かる場合は近い順、分からない場合はスコア降順で並べ、上限件数に絞る
    if user_lat is not None and user_lng is not None:
        rows.sort(key=lambda r: r.get("distanceKm", float("inf")))
    else:
        rows.sort(key=lambda r: r["score"], reverse=True)
    rows = rows[:SPOTS_CONTEXT_LIMIT]

    if not rows:
        return ""

    lines = []
    for r in rows:
        parts = [f"魚種={','.join(r['fishTypes']) or '不明'}", f"スコア={r['score']:.0f}"]
        if "distanceKm" in r:
            parts.append(f"現在地から{r['distanceKm']}km")
        lines.append(f"- {r['name']}（{r['place']}）: {', '.join(parts)}")

    return "\n".join(lines)


def _generate_chat_reply(
    history: list[dict[str, Any]], message: str, image_url: str | None, spots_context: str = ""
) -> str:
    """Claude APIを使ってチャット応答を生成する（テキスト、または画像+テキストのマルチモーダル）。

    APIキー未設定時・エラー時はフォールバック文言を返し、Lambdaを継続させる
    （generate_score.py の generate_reason() と同じ思想）。

    Args:
        history       (list[dict[str, Any]]): 直近の会話履歴（{"role", "content"}のリスト）
        message       (str): 今回のユーザーメッセージ
        image_url     (str | None): 添付画像の公開URL（省略可）
        spots_context (str): `_build_spots_context()` が生成した実スポットデータの要約
            （2026-07-26追加。「近くの釣り場は？」等に実データで答えられるようにする）

    Returns:
        str: AIの応答テキスト
    """
    api_key = _get_anthropic_api_key()
    if not api_key:
        return "現在AI機能を利用できません（APIキー未設定）。しばらくしてからお試しください。"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        system_instruction = (
            "あなたは釣行AIアプリに組み込まれた釣りの専門家アシスタントです。"
            "魚種の判定、エサ・仕掛けの適否、釣果へのコメントなど、釣りに関する質問に"
            "日本語で親しみやすく、かつ具体的に答えてください。写真が添付されている場合は"
            "その内容（魚種・エサ・釣り場の様子等）を踏まえて回答してください。"
        )
        if spots_context:
            system_instruction += (
                "\n\n以下はこのアプリに実際に登録されている釣り場データです。"
                "「近くの釣り場は？」「〇〇県のおすすめは？」のような質問には、"
                "このデータの中から該当するものを具体的に案内してください。"
                "該当する場所がデータに無い場合は正直にその旨を伝え、存在しない場所を作り出さないでください。\n"
                f"{spots_context}"
            )

        # 直近の履歴をClaudeのmessages形式に変換。DynamoDBの保存形式が既に
        # role: "user"/"assistant" で交互に並んでいるため、そのままcontentのみ抜き出せばよい
        # （imageUrl・createdAt等の余計なキーはAPIに送らないよう除外する）
        messages: list[dict[str, Any]] = [
            {"role": h["role"], "content": h["content"]}
            for h in history[-CHAT_HISTORY_LIMIT:]
        ]

        user_content: list[dict[str, Any]] = [{"type": "text", "text": message}]
        if image_url:
            fetched = _fetch_image_bytes(image_url)
            if fetched:
                image_bytes, content_type = fetched
                user_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": content_type,
                        "data": base64.b64encode(image_bytes).decode("utf-8"),
                    },
                })
        messages.append({"role": "user", "content": user_content})

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            system=system_instruction,
            messages=messages,
        )
        return response.content[0].text.strip()

    except Exception as e:
        print(f"Claude chat error: {e}")
        return "回答の生成に失敗しました。もう一度お試しください。"


# ─────────────────────────────
# /chat (POST)
# ─────────────────────────────
@handler_guard
def postChatHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """POST /chat — AIチャットにメッセージを送信する（新規 or 既存チャットへの追記、または既存メッセージの編集）。

    chatId が未指定の場合は新規チャットを作成する。写真が添付されている場合は
    Claudeへマルチモーダル入力として渡す。応答は同期的に返す
    （バッチ処理と違い、チャットのUXにはポーリングが合わないため）。

    editIndex が指定された場合は「送信済みメッセージの訂正・再送信」として扱う（2026-07-26追加）。
    対象メッセージ（ユーザー発言のみ編集可）以降の会話を切り詰め、新しい本文でAI応答を生成し直す。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            body (str): JSON文字列。message(必須) / chatId(省略可) / imageUrl(省略可) /
                lat・lng(省略可、現在地に近い釣り場の案内精度を上げるため。2026-07-26追加) /
                editIndex(省略可、既存メッセージを編集して再送信する場合に指定) を含む
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"chatId": str, "reply": str, "updatedAt": str}
            message 未指定時 400: {"error": "..."}
            editIndex が不正な場合 400: {"error": "..."}
            チャットが存在しない場合 404: {"error": "..."}
            本日の利用上限に達している場合 429: {"error": "rate_limited", "message": "..."}
    """
    body = json.loads(event.get("body") or "{}")
    message = body.get("message")
    chat_id = body.get("chatId")
    image_url = body.get("imageUrl")
    lat, lng = body.get("lat"), body.get("lng")
    edit_index = body.get("editIndex")

    if not message:
        return _resp(400, {"error": "message is required"})

    user_id = _get_user_id(event)

    # Claude呼び出しコストを抑えるための1日あたりレート制限（2026-07-26追加）。
    # 上限超過時はClaudeを呼ばずに即座に返す（編集による再送信も同様にカウントする）
    if not _check_and_increment_daily_usage(user_id, "chat", DAILY_CHAT_LIMIT):
        return _resp(429, {
            "error": "rate_limited",
            "message": f"本日のAI相談の利用回数（{DAILY_CHAT_LIMIT}件）に達しました。明日またお試しください。",
        })

    table = _get_table(CHATS_TABLE)
    now = datetime.now(timezone.utc).isoformat()

    if chat_id:
        existing = table.get_item(Key={"userId": user_id, "chatId": chat_id}).get("Item")
        if edit_index is not None and not existing:
            return _resp(404, {"error": "chat not found"})
        messages: list[dict[str, Any]] = existing["messages"] if existing else []
        title = existing["title"] if existing else message[:30]
        created_at = existing["createdAt"] if existing else now

        if edit_index is not None:
            if not (0 <= edit_index < len(messages)) or messages[edit_index].get("role") != "user":
                return _resp(400, {"error": "invalid editIndex"})
            # 編集は本文のみが対象。元メッセージに添付されていた画像はそのまま維持する
            image_url = messages[edit_index].get("imageUrl") or None
            messages = messages[:edit_index]
            if edit_index == 0:
                title = message[:30]
    else:
        chat_id = str(uuid.uuid4())
        messages = []
        title = message[:30]
        created_at = now

    messages.append({"role": "user", "content": message, "imageUrl": image_url or "", "createdAt": now})

    spots_context = _build_spots_context(
        float(lat) if lat is not None else None, float(lng) if lng is not None else None
    )
    reply = _generate_chat_reply(messages[:-1], message, image_url, spots_context)

    reply_at = datetime.now(timezone.utc).isoformat()
    messages.append({"role": "assistant", "content": reply, "createdAt": reply_at})

    table.put_item(Item={
        "userId": user_id,
        "chatId": chat_id,
        "title": title,
        "messages": messages,
        "createdAt": created_at,
        "updatedAt": reply_at,
    })

    return _resp(200, {"chatId": chat_id, "reply": reply, "updatedAt": reply_at})


# ─────────────────────────────
# /chats (GET)
# ─────────────────────────────
@handler_guard
def getChatsHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """GET /chats — チャット履歴一覧を新しい順で返す。

    履歴パネルの一覧表示用に、messages配列を含まない軽量なレスポンスを返す。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（Cognito認証必須）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: statusCode=200、body に {"items": [{chatId, title, updatedAt}, ...]}（updatedAt降順）
    """
    table = _get_table(CHATS_TABLE)
    resp = table.query(KeyConditionExpression=Key("userId").eq(_get_user_id(event)))
    items = resp.get("Items", [])

    summaries = [
        {"chatId": i["chatId"], "title": i.get("title", ""), "updatedAt": i.get("updatedAt", "")}
        for i in items
    ]
    summaries.sort(key=lambda x: x["updatedAt"], reverse=True)

    return _resp(200, {"items": summaries})


# ─────────────────────────────
# /chats/{chatId} (GET)
# ─────────────────────────────
@handler_guard
def getChatHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """GET /chats/{chatId} — 特定チャットの全メッセージを返す。

    履歴一覧から選んだ会話を再開する際に使用する。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            pathParameters.chatId (str): 対象チャットID
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {chatId, title, messages, createdAt, updatedAt}
            存在しない場合 404: {"error": "..."}
    """
    chat_id = (event.get("pathParameters") or {}).get("chatId")

    table = _get_table(CHATS_TABLE)
    item = table.get_item(Key={"userId": _get_user_id(event), "chatId": chat_id}).get("Item")

    if not item:
        return _resp(404, {"error": "chat not found"})

    return _resp(200, item)


# ─────────────────────────────
# /chats/{chatId} (DELETE)
# ─────────────────────────────
@handler_guard
def deleteChatHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """DELETE /chats/{chatId} — チャットを削除する。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            pathParameters.chatId (str): 削除対象のチャットID
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"message": "deleted"}
            chatId 未指定時 400: {"error": "chatId is required"}
    """
    chat_id = (event.get("pathParameters") or {}).get("chatId")

    if not chat_id:
        return _resp(400, {"error": "chatId is required"})

    table = _get_table(CHATS_TABLE)
    table.delete_item(Key={"userId": _get_user_id(event), "chatId": chat_id})

    return _resp(200, {"message": "deleted"})


# ─────────────────────────────
# /me (GET / PUT) — ユーザー自身のプロフィール（表示名）
# 2026-07-26追加。友人と使うようになりメールアドレスがナビに出るのが微妙という声を受けて、
# 自分で登録・編集できる表示名を追加した
# ─────────────────────────────
DISPLAY_NAME_MAX_LEN = 30


@handler_guard
def getMyProfileHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """GET /me — ログイン中ユーザー自身のプロフィールを返す。

    UsersTable に未登録（=表示名を一度も設定していない）の場合もエラーにはせず、
    displayName: null で200を返す（フロント側で「未設定」の判定に使う）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（Cognito認証必須）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: statusCode=200、body に {"userId": str, "displayName": str|None, "email": str}
    """
    user_id = _get_user_id(event)
    claims = ((event.get("requestContext") or {}).get("authorizer") or {}).get("claims") or {}
    email = claims.get("email", "")

    table = _get_table(USERS_TABLE)
    item = table.get_item(Key={"userId": user_id}).get("Item")

    return _resp(200, {
        "userId": user_id,
        "displayName": item.get("displayName") if item else None,
        "email": item.get("email") if item else email,
    })


@handler_guard
def putMyProfileHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """PUT /me — ログイン中ユーザー自身の表示名を設定・更新する。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（Cognito認証必須）
            body (str): JSON文字列。displayName(必須、1〜30文字) を含む
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"userId": str, "displayName": str}
            displayName未指定/文字数超過時 400: {"error": "..."}
    """
    body = json.loads(event.get("body") or "{}")
    display_name = (body.get("displayName") or "").strip()

    if not display_name:
        return _resp(400, {"error": "displayName is required"})
    if len(display_name) > DISPLAY_NAME_MAX_LEN:
        return _resp(400, {"error": f"displayName must be {DISPLAY_NAME_MAX_LEN} characters or fewer"})

    user_id = _get_user_id(event)
    claims = ((event.get("requestContext") or {}).get("authorizer") or {}).get("claims") or {}
    email = claims.get("email", "")
    now = datetime.now(timezone.utc).isoformat()

    table = _get_table(USERS_TABLE)
    table.update_item(
        Key={"userId": user_id},
        UpdateExpression=(
            "SET displayName = :d, email = :e, updatedAt = :u, "
            "createdAt = if_not_exists(createdAt, :u)"
        ),
        ExpressionAttributeValues={":d": display_name, ":e": email, ":u": now},
    )

    return _resp(200, {"userId": user_id, "displayName": display_name})