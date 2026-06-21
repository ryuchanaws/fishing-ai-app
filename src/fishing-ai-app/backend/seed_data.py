"""
seed_data.py

DynamoDB の fishing-spots テーブルに初期スポットデータを投入するスクリプト。

Usage:
    python seed_data.py

Requirements:
    - AWS認証情報が設定済みであること（~/.aws/credentials または環境変数）
    - DynamoDB テーブル "fishing-spots" が作成済みであること
    - boto3 がインストール済みであること（pip install boto3）
"""

import boto3
from decimal import Decimal
from typing import Any


# DynamoDB リソースを初期化
# type: ignore でPylanceの誤検知を抑制（boto3の型スタブ制限による警告）
# リージョンは東京（ap-northeast-1）を指定
dynamodb: Any = boto3.resource("dynamodb", region_name="ap-northeast-1")

# 投入先テーブルを指定
# dynamodb を Any 型にすることで Table へのアクセスエラーを回避
table: Any = dynamodb.Table("fishing-spots")


# 初期スポットデータ
# 各スポットの定義:
#   spotId      : スポットの一意識別子（PK）
#   name        : スポット名
#   lat / lng   : 緯度・経度（Google Maps表示に使用）
#   fishTypes   : 釣れる魚種リスト（AIのreason生成にも使用）
#   distanceKm  : 基準地点からの距離（スコア計算に使用）
#   costYen     : 入場・駐車場等の費用（0=無料）
SPOTS: list[dict[str, Any]] = [
    {
        "spotId": "spot-001",
        "name": "三浦半島・城ヶ島",
        "lat": Decimal("35.1397"),
        "lng": Decimal("139.6177"),
        "fishTypes": ["アジ", "イサキ", "メジナ", "カサゴ"],
        "distanceKm": Decimal("65"),
        "costYen": Decimal("0"),
    },
    {
        "spotId": "spot-002",
        "name": "江ノ島",
        "lat": Decimal("35.2991"),
        "lng": Decimal("139.4804"),
        "fishTypes": ["クロダイ", "シーバス", "サバ", "アジ"],
        "distanceKm": Decimal("50"),
        "costYen": Decimal("0"),
    },
    {
        "spotId": "spot-003",
        "name": "富津岬",
        "lat": Decimal("35.3019"),
        "lng": Decimal("139.7986"),
        "fishTypes": ["ハゼ", "シーバス", "カレイ"],
        "distanceKm": Decimal("70"),
        "costYen": Decimal("0"),
    },
    {
        "spotId": "spot-004",
        "name": "相模川河口",
        "lat": Decimal("35.3148"),
        "lng": Decimal("139.3975"),
        "fishTypes": ["シーバス", "ヒラメ", "サヨリ"],
        "distanceKm": Decimal("55"),
        "costYen": Decimal("0"),
    },
    {
        "spotId": "spot-005",
        "name": "葛西臨海公園",
        "lat": Decimal("35.6276"),
        "lng": Decimal("139.8652"),
        "fishTypes": ["クロダイ", "ハゼ", "シーバス"],
        "distanceKm": Decimal("20"),
        "costYen": Decimal("0"),
    },
]


def seed() -> None:
    """DynamoDB の fishing-spots テーブルに初期スポットデータを投入する。

    SPOTS リストに定義された全スポットを DynamoDB に put_item で書き込む。
    同一の spotId が既に存在する場合は上書きされる（冪等性あり）。

    Returns:
        None

    Raises:
        boto3.exceptions.Boto3Error: AWS接続や認証に失敗した場合
        botocore.exceptions.ClientError: DynamoDBのテーブルが存在しない場合
    """
    for spot in SPOTS:
        # 1件ずつDynamoDBに書き込む
        table.put_item(Item=spot)
        print(f"Inserted: {spot['name']}")

    print(f"\nDone. {len(SPOTS)} spots inserted.")


if __name__ == "__main__":
    seed()