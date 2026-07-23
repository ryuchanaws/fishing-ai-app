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
from typing import Any

import boto3
from botocore.exceptions import ClientError

# DynamoDB / SSM クライアントはバッチ系Lambda全体で共有する
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))  # type: ignore[attr-defined]
ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))

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
