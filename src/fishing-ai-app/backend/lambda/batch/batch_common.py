"""
batch_common.py

バッチ系 Lambda（generate_score.py / discover_spots.py）で共有するヘルパー群。

generate_score.py が新スポット探索（discover_spots.py）の機能を呼び出すために
両者が同じヘルパーに依存する必要があるが、discover_spots.py 側から
generate_score.py を import すると循環importになるため、共通部分をこのファイルに切り出した。
"""

import os
import json
import urllib.request
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

# DynamoDB / SSM / S3 クライアントはバッチ系Lambda全体で共有する
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))  # type: ignore[attr-defined]
ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))
# discover_spots.py がスポット写真（Google Places Photos）をアップロードするために使用（2026-07-26追加）
s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))

# 外部API呼び出しのタイムアウト（秒）。バッチ全体のLambdaタイムアウトを圧迫しないよう短めに設定
EXTERNAL_API_TIMEOUT_SEC = 5


def get_table(name: str) -> Any:
    """DynamoDB テーブルオブジェクトを取得する。

    Args:
        name (str): DynamoDB テーブル名

    Returns:
        Any: DynamoDB テーブルオブジェクト
    """
    return dynamodb.Table(name)  # type: ignore[attr-defined]


def http_get_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    """指定URLにGETリクエストを送り、JSONレスポンスをdictで返す。

    追加の依存パッケージ（requests等）を避けるため標準ライブラリの
    urllib.request のみで実装している。値はそのまま連結するため、
    URLエンコードが必要な値（日本語など）は呼び出し側で事前にエンコードすること。

    Args:
        url (str): リクエスト先URL（クエリなし）
        params (dict[str, str]): クエリパラメータ（値は事前にエンコード済みであること）

    Returns:
        dict[str, Any]: パース済みJSONレスポンス

    Raises:
        urllib.error.URLError: 通信エラー・タイムアウト時
        json.JSONDecodeError: レスポンスがJSONとして不正な場合
    """
    query = "&".join(f"{k}={v}" for k, v in params.items())
    with urllib.request.urlopen(f"{url}?{query}", timeout=EXTERNAL_API_TIMEOUT_SEC) as resp:
        return json.loads(resp.read())


def http_get_bytes(url: str, params: dict[str, str]) -> bytes:
    """指定URLにGETリクエストを送り、レスポンスボディを生バイト列で返す（2026-07-26追加）。

    Google Places Photo API のように画像バイナリを直接返すエンドポイント向け。
    http_get_json と同じ理由で urllib.request のみで実装している。
    urlopen はHTTPリダイレクト（Places Photo APIが返す302など）を自動で追跡する。

    Args:
        url (str): リクエスト先URL（クエリなし）
        params (dict[str, str]): クエリパラメータ（値は事前にエンコード済みであること）

    Returns:
        bytes: レスポンスボディ

    Raises:
        urllib.error.URLError: 通信エラー・タイムアウト時
    """
    query = "&".join(f"{k}={v}" for k, v in params.items())
    with urllib.request.urlopen(f"{url}?{query}", timeout=EXTERNAL_API_TIMEOUT_SEC) as resp:
        return resp.read()


def get_ssm_parameter(name: str) -> str:
    """SSM Parameter Store から指定パラメータの値を取得する。

    Args:
        name (str): SSMパラメータ名（"/"を含む階層型の場合は先頭スラッシュ必須）

    Returns:
        str: パラメータ値。取得に失敗した場合は空文字列（呼び出し側でフォールバック処理する）
    """
    try:
        response = ssm.get_parameter(Name=name, WithDecryption=True)
        return response["Parameter"]["Value"]
    except ClientError as e:
        print(f"SSM get_parameter error ({name}): {e}")
        return ""


# 2026-07-26追加: AI分析実行・新スポット探索・釣具店検索はPlaces/Claude APIの呼び出しを伴い
# 課金対象のため、handlers.py の _get_user_id / _check_and_increment_daily_usage と同じ仕組みを
# バッチ系Lambda（admin_trigger.py・tackle_shops.py）向けにも用意する。
# api/ と batch/ はSAMの別デプロイパッケージのため、コードは共有できずここに複製している
# （discover_spots.py の haversine_km 等、既存の重複パターンを踏襲）。
DEFAULT_USER_ID = "user-001"


def get_user_id(event: dict[str, Any]) -> str:
    """Cognitoオーソライザーが付与したクレームから実ユーザーIDを取得する（handlers.pyと同じロジック）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト

    Returns:
        str: Cognitoのsub（ユーザー識別子）。取得できない場合は DEFAULT_USER_ID
    """
    claims = ((event.get("requestContext") or {}).get("authorizer") or {}).get("claims") or {}
    return claims.get("sub", DEFAULT_USER_ID)


def check_and_increment_daily_usage(user_id: str, action: str, limit: int) -> bool:
    """指定ユーザー・アクションの当日の利用回数をアトミックに加算し、上限内かどうかを返す
    （handlers.py の _check_and_increment_daily_usage と同じロジック）。

    Args:
        user_id (str): 対象ユーザーID（Cognitoのsub）
        action  (str): アクション種別（例: "ai-batch"・"spot-discovery"・"tackle-shop-search"）
        limit   (int): 1日あたりの上限回数

    Returns:
        bool: 上限内（呼び出しを継続してよい）なら True、上限超過なら False
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_key = f"{action}#{today}"
    expires_at = int(datetime.now(timezone.utc).timestamp()) + 2 * 24 * 60 * 60

    table = get_table(os.environ.get("USAGE_TABLE", "fishing-usage"))
    result = table.update_item(
        Key={"userId": user_id, "dateKey": date_key},
        UpdateExpression="ADD #c :inc SET expiresAt = if_not_exists(expiresAt, :exp)",
        ExpressionAttributeNames={"#c": "count"},
        ExpressionAttributeValues={":inc": 1, ":exp": expires_at},
        ReturnValues="UPDATED_NEW",
    )
    current_count = int(result["Attributes"]["count"])
    return current_count <= limit
