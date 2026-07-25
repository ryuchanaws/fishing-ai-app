"""
handlers.py

API Gateway から呼び出される Lambda ハンドラー群。

Endpoints:
    GET    /recommendations
    GET    /spots
    PUT    /spots/{spotId}/image
    GET    /posts
    POST   /posts
    DELETE /posts/{postId}
    GET    /favorites
    POST   /favorites
    DELETE /favorites/{spotId}
    POST   /uploads/presign
    POST   /chat
    GET    /chats
    GET    /chats/{chatId}
    DELETE /chats/{chatId}

Requirements:
    - 環境変数にDynamoDBテーブル名が設定済み
    - Lambda実行ロールにDynamoDBアクセス権限が必要
"""

import json
import os
import uuid
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

import boto3
import google.generativeai as genai
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
# SSM（Gemini APIキー。postChatHandlerのAIチャット応答生成に使用）
# ─────────────────────────────
ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))
# "/"を含む階層型のSSMパラメータ名は先頭スラッシュ必須（AWSの仕様。generate_score.pyと同じ注意点）
GEMINI_API_KEY_PARAM = "/fishing-ai/gemini-api-key"

# 直近何往復分の会話をGeminiに渡すか（トークン量とレイテンシを抑えるための上限）
CHAT_HISTORY_LIMIT = 10
# ユーザー単体運用のため固定（他エンドポイントと同じ規約）
DEFAULT_USER_ID = "user-001"


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


# ─────────────────────────────
# /posts (POST)
# ─────────────────────────────
@handler_guard
def postPostsHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """POST /posts — 釣果投稿を作成する。

    リクエストボディの spotId / content を PostsTable に登録する。
    postId はサーバー側で uuid4 を採番し、createdAt は現在時刻を設定する。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            body (str): JSON文字列。spotId(必須) / content(必須) /
                userId(省略可) / imageUrl(省略可) / fishCaught(省略可) を含む
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
        "userId": body.get("userId", "user-001"),
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

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            pathParameters.postId (str): 削除対象の投稿ID
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"message": "deleted"}
            postId 未指定時 400: {"error": "postId is required"}
    """
    post_id = (event.get("pathParameters") or {}).get("postId")

    if not post_id:
        return _resp(400, {"error": "postId is required"})

    table = _get_table(POSTS_TABLE)
    table.delete_item(Key={"postId": post_id})

    return _resp(200, {"message": "deleted"})


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
# AIチャット共通ヘルパー
# ─────────────────────────────
def _get_gemini_api_key() -> str:
    """SSM Parameter StoreからGemini APIキーを取得する（generate_score.pyと同じパターン）。"""
    try:
        response = ssm.get_parameter(Name=GEMINI_API_KEY_PARAM, WithDecryption=True)
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


def _generate_chat_reply(history: list[dict[str, Any]], message: str, image_url: str | None) -> str:
    """Gemini APIを使ってチャット応答を生成する（テキスト、または画像+テキストのマルチモーダル）。

    APIキー未設定時・エラー時はフォールバック文言を返し、Lambdaを継続させる
    （generate_score.py の generate_reason() と同じ思想）。

    Args:
        history     (list[dict[str, Any]]): 直近の会話履歴（{"role", "content"}のリスト）
        message     (str): 今回のユーザーメッセージ
        image_url   (str | None): 添付画像の公開URL（省略可）

    Returns:
        str: AIの応答テキスト
    """
    api_key = _get_gemini_api_key()
    if not api_key:
        return "現在AI機能を利用できません（APIキー未設定）。しばらくしてからお試しください。"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-flash-latest",
            system_instruction=(
                "あなたは釣行AIアプリに組み込まれた釣りの専門家アシスタントです。"
                "魚種の判定、エサ・仕掛けの適否、釣果へのコメントなど、釣りに関する質問に"
                "日本語で親しみやすく、かつ具体的に答えてください。写真が添付されている場合は"
                "その内容（魚種・エサ・釣り場の様子等）を踏まえて回答してください。"
            ),
        )

        # 直近の履歴をGeminiのchat形式（role: user/model）に変換
        chat_history = [
            {"role": "user" if h["role"] == "user" else "model", "parts": [h["content"]]}
            for h in history[-CHAT_HISTORY_LIMIT:]
        ]
        chat = model.start_chat(history=chat_history)

        parts: list[Any] = [message]
        if image_url:
            fetched = _fetch_image_bytes(image_url)
            if fetched:
                image_bytes, content_type = fetched
                parts.append({"mime_type": content_type, "data": image_bytes})

        response = chat.send_message(parts)
        return response.text.strip()

    except Exception as e:
        print(f"Gemini chat error: {e}")
        return "回答の生成に失敗しました。もう一度お試しください。"


# ─────────────────────────────
# /chat (POST)
# ─────────────────────────────
@handler_guard
def postChatHandler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """POST /chat — AIチャットにメッセージを送信する（新規 or 既存チャットへの追記）。

    chatId が未指定の場合は新規チャットを作成する。写真が添付されている場合は
    Geminiへマルチモーダル入力として渡す。応答は同期的に返す
    （バッチ処理と違い、チャットのUXにはポーリングが合わないため）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト
            body (str): JSON文字列。message(必須) / chatId(省略可) / imageUrl(省略可) を含む
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200: {"chatId": str, "reply": str, "updatedAt": str}
            message 未指定時 400: {"error": "..."}
    """
    body = json.loads(event.get("body") or "{}")
    message = body.get("message")
    chat_id = body.get("chatId")
    image_url = body.get("imageUrl")

    if not message:
        return _resp(400, {"error": "message is required"})

    table = _get_table(CHATS_TABLE)
    now = datetime.now(timezone.utc).isoformat()

    if chat_id:
        existing = table.get_item(Key={"userId": DEFAULT_USER_ID, "chatId": chat_id}).get("Item")
        messages: list[dict[str, Any]] = existing["messages"] if existing else []
        title = existing["title"] if existing else message[:30]
        created_at = existing["createdAt"] if existing else now
    else:
        chat_id = str(uuid.uuid4())
        messages = []
        title = message[:30]
        created_at = now

    messages.append({"role": "user", "content": message, "imageUrl": image_url or "", "createdAt": now})

    reply = _generate_chat_reply(messages[:-1], message, image_url)

    reply_at = datetime.now(timezone.utc).isoformat()
    messages.append({"role": "assistant", "content": reply, "createdAt": reply_at})

    table.put_item(Item={
        "userId": DEFAULT_USER_ID,
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
        event (dict[str, Any]): API Gateway イベントオブジェクト（本エンドポイントでは未使用）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: statusCode=200、body に {"items": [{chatId, title, updatedAt}, ...]}（updatedAt降順）
    """
    table = _get_table(CHATS_TABLE)
    resp = table.query(KeyConditionExpression=Key("userId").eq(DEFAULT_USER_ID))
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
    item = table.get_item(Key={"userId": DEFAULT_USER_ID, "chatId": chat_id}).get("Item")

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
    table.delete_item(Key={"userId": DEFAULT_USER_ID, "chatId": chat_id})

    return _resp(200, {"message": "deleted"})