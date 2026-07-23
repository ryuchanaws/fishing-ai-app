"""
generate_score.py

釣りスポットのスコアを計算し、AIによる推薦理由を生成するバッチ処理 Lambda。

EventBridge スケジュール（毎日AM6:00 JST）または
POST /admin/run-ai-batch による手動実行で起動される。

処理フロー:
    1. Spots テーブルから全スポットを取得
    2. 各スポットの天気・潮汐スコアを取得（外部API or シミュレーション）
    3. ルールベースのスコア式でスコアを計算
    4. Gemini API で推薦理由（reason）を日本語生成
    5. Recommendations テーブルに結果を保存

Requirements:
    - 環境変数 SPOTS_TABLE / RECOMMENDATIONS_TABLE / GEMINI_API_KEY が設定済みであること
    - Lambda 実行ロールに DynamoDB の読み書き権限があること
    - anthropic パッケージがインストール済みであること（pip install anthropic）
"""

import json
import os
import random
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any

import boto3
import google.generativeai as genai
from botocore.exceptions import ClientError

# DynamoDB リソースを初期化
# リージョンは環境変数から取得（デフォルト: 東京）
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))  # type: ignore[attr-defined]

ssm = boto3.client(
    "ssm",
    region_name=os.environ.get("AWS_REGION", "ap-northeast-1"),
)

# 環境変数からテーブル名・APIキーを取得
SPOTS_TABLE           = os.environ.get("SPOTS_TABLE", "fishing-spots")
RECOMMENDATIONS_TABLE = os.environ.get("RECOMMENDATIONS_TABLE", "fishing-recommendations")
GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY_PARAM",
    "/fishing-ai/gemini-api-key",
)

# CORS ヘッダー（手動実行APIからのレスポンスに付与）
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}


def _get_table(name: str) -> Any:
    """DynamoDB テーブルオブジェクトを取得する。

    Pylance の型スタブ制限による誤検知を1箇所に集約するためのヘルパー関数。

    Args:
        name (str): DynamoDB テーブル名

    Returns:
        Any: DynamoDB テーブルオブジェクト
    """
    return dynamodb.Table(name)  # type: ignore[attr-defined]

def _get_gemini_api_key() -> str:
    """SSM Parameter StoreからGemini APIキーを取得する。"""

    try:
        response = ssm.get_parameter(
            Name=GEMINI_API_KEY,
            WithDecryption=True,
        )
        return response["Parameter"]["Value"]

    except ClientError as e:
        print(f"SSM get_parameter error: {e}")
        return ""

# ─── Score formula ───────────────────────────────────────────────────
def calc_score(fish_prob: float, weather: float, tide: float,
               distance_km: float, cost_yen: float) -> float:
    """ルールベースのスコア式で釣りスポットの総合スコアを計算する。

    スコア式:
        score = fish_prob * 0.4
              + weather   * 0.2
              + tide      * 0.2
              - dist_norm * 0.1
              - cost_norm * 0.1

    distance と cost は 0〜100 に正規化してからマイナス方向に加算する。
    結果は 0.0〜100.0 の範囲にクランプされる。

    Args:
        fish_prob   (float): 魚が釣れる確率スコア（0〜100）
        weather     (float): 天気スコア（0〜100）
        tide        (float): 潮汐スコア（0〜100）
        distance_km (float): 基準地点からの距離（km）
        cost_yen    (float): 費用（円）

    Returns:
        float: 総合スコア（0.0〜100.0）
    """
    dist_norm = min(distance_km / 100.0, 1.0) * 100
    cost_norm = min(cost_yen / 5000.0, 1.0) * 100
    score = (
        fish_prob  * 0.4
        + weather  * 0.2
        + tide     * 0.2
        - dist_norm * 0.1
        - cost_norm * 0.1
    )
    return max(0.0, min(100.0, score))


# ─── Simulated weather/tide ──────────────────────────────────────────
def fetch_weather_score(lat: float, lng: float) -> float:
    """指定座標の天気スコアを取得する。

    現在はシミュレーション値を返す。
    本番環境では OpenWeatherMap または気象庁API に差し替えること。

    Args:
        lat (float): 緯度
        lng (float): 経度

    Returns:
        float: 天気スコア（0〜100）
    """
    return random.uniform(50, 95)


def fetch_tide_score(lat: float, lng: float) -> float:
    """指定座標の潮汐スコアを取得する。

    現在はシミュレーション値を返す。
    本番環境では WorldTides 等の潮汐APIに差し替えること。

    Args:
        lat (float): 緯度
        lng (float): 経度

    Returns:
        float: 潮汐スコア（0〜100）
    """
    return random.uniform(50, 95)


def estimate_fish_probability(spot_name: str, fish_types: list[str]) -> float:
    """季節ヒューリスティックに基づいて魚が釣れる確率スコアを推定する。

    春（4・5月）と秋（9・10月）はハイシーズンとしてスコアを加算し、
    冬（12・1・2月）はオフシーズンとしてスコアを減算する。
    将来的には ML モデルへの差し替えを想定している。

    Args:
        spot_name  (str): スポット名（将来の拡張用、現在は未使用）
        fish_types (list[str]): 釣れる魚種リスト（将来の拡張用、現在は未使用）

    Returns:
        float: 魚が釣れる確率スコア（20.0〜95.0）
    """
    month = datetime.now(timezone.utc).month
    base = 70
    if month in [4, 5, 9, 10]:
        base += 15
    elif month in [12, 1, 2]:
        base -= 20
    return min(95.0, max(20.0, base + random.uniform(-10, 10)))


# ─── AI reason generation via Gemini ─────────────────────────────────
def generate_reason(spot_name: str, fish_types: list[str], score: float,
                    weather_score: float, tide_score: float,
                    distance_km: float) -> str:
    """Gemini API を使って釣りスポットの推薦理由を日本語で生成する。

    GEMINI_API_KEY が未設定の場合はフォールバック文言を返す。
    API エラー時もフォールバック文言を返し、Lambda を継続させる。

    Args:
        spot_name     (str): スポット名
        fish_types    (list[str]): 期待できる魚種リスト
        score         (float): 総合スコア（0〜100）
        weather_score (float): 天気スコア（0〜100）
        tide_score    (float): 潮汐スコア（0〜100）
        distance_km   (float): 基準地点からの距離（km）

    Returns:
        str: 釣りスポットの推薦理由（2〜3文の日本語）
    """
    api_key = _get_gemini_api_key()
    if not api_key:
        return f"{spot_name}は現在の天気・潮汐条件が良好で、{', '.join(fish_types)}の釣果が期待できます。"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        prompt = f"""あなたは釣りの専門家です。以下のデータを元に、釣り人向けに「なぜこのスポットが今日おすすめか」を2〜3文の自然な日本語で説明してください。専門用語を使いつつも親しみやすい文体で。

スポット名: {spot_name}
期待できる魚種: {', '.join(fish_types)}
総合スコア: {score:.0f}/100
天気スコア: {weather_score:.0f}/100
潮汐スコア: {tide_score:.0f}/100
距離: {distance_km:.1f}km

説明文のみ出力してください（前置き不要）:"""

        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        print(f"Gemini API error: {e}")
        return f"{spot_name}は現在のコンディションが良好です。{', '.join(fish_types)}の釣果が見込めます。"


# ─── Main batch handler ───────────────────────────────────────────────
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """全スポットのスコア計算とAI推薦理由生成を実行するメインハンドラー。

    Spots テーブルの全レコードを処理し、スコアと推薦理由を
    Recommendations テーブルに保存する。

    EventBridge スケジュールまたは admin_trigger.py 経由で呼び出される。

    Args:
        event   (dict[str, Any]): Lambda イベントオブジェクト（内容は不使用）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200:
                {
                    "status": "completed",
                    "processedCount": int,  # 処理したスポット数
                    "completedAt": str      # 完了日時（ISO 8601）
                }
            スポットなし 200:
                {
                    "message": "No spots found",
                    "processedCount": 0
                }
    """
    print("generateSpotScoreBatch started")

    spots_table = _get_table(SPOTS_TABLE)
    rec_table   = _get_table(RECOMMENDATIONS_TABLE)

    spots: list[dict[str, Any]] = spots_table.scan()["Items"]
    if not spots:
        return {
            "statusCode": 200,
            "headers": CORS,
            "body": json.dumps({"message": "No spots found", "processedCount": 0}),
        }

    processed = 0
    for spot in spots:
        spot_id:     str       = spot["spotId"]
        spot_name:   str       = spot.get("name", spot_id)
        lat:         float     = float(spot.get("lat", 35.0))
        lng:         float     = float(spot.get("lng", 135.0))
        fish_types:  list[str] = spot.get("fishTypes", ["アジ", "サバ", "イワシ"])
        distance_km: float     = float(spot.get("distanceKm", 20.0))
        cost_yen:    float     = float(spot.get("costYen", 0))

        weather_score = fetch_weather_score(lat, lng)
        tide_score    = fetch_tide_score(lat, lng)
        fish_prob     = estimate_fish_probability(spot_name, fish_types)

        score  = calc_score(fish_prob, weather_score, tide_score, distance_km, cost_yen)
        reason = generate_reason(spot_name, fish_types, score,
                                 weather_score, tide_score, distance_km)

        rec_table.put_item(Item={
            "spotId":       spot_id,
            "score":        Decimal(str(round(score, 2))),
            "fishTypes":    fish_types,
            "reason":       reason,
            "distance":     Decimal(str(distance_km)),
            "cost":         Decimal(str(cost_yen)),
            "weatherScore": Decimal(str(round(weather_score, 2))),
            "tideScore":    Decimal(str(round(tide_score, 2))),
            "updatedAt":    datetime.now(timezone.utc).isoformat(),
        })
        processed += 1
        print(f"  Processed: {spot_name} → score={score:.1f}")

    result: dict[str, Any] = {
        "status": "completed",
        "processedCount": processed,
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    return {"statusCode": 200, "headers": CORS, "body": json.dumps(result)}