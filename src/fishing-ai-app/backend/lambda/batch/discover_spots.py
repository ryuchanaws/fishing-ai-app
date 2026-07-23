"""
discover_spots.py

Google Places API を使って新しい釣りスポット候補を探索し、
Spots テーブルに自動追加するバッチ Lambda。

EventBridge スケジュール（毎週日曜 AM6:00 JST）または
POST /admin/run-spot-discovery による手動実行で起動される。

背景:
    generateSpotScoreBatch は既存の Spots テーブルの中身を毎回re-scoreする
    だけで、新しいスポットを増やすことはない（スポット候補の追加は本バッチの役目）。
    実在の場所データを使うため、LLMにスポット名や座標を直接生成させるのではなく、
    Google Places API のテキスト検索結果（実POIデータ）のみを候補として採用する。
    Gemini は座標や実在性に関わらない付随情報（想定される魚種）の推測にのみ使う。

処理フロー:
    1. Google Places API Text Search で「釣り 堤防 波止」等のキーワード検索
    2. 既存 Spots テーブルの全件と緯度経度を比較し、近傍（300m以内）の重複候補を除外
    3. 新規候補ごとに Gemini で想定される魚種を推測（失敗時は汎用デフォルト）
    4. 基準地点（東京駅）からの距離を算出し、Spots テーブルへ put_item

Requirements:
    - 環境変数 SPOTS_TABLE が設定済みであること
    - SSM パラメータ fishing-ai/google-places-api-key が登録済みであること
    - Lambda 実行ロールに SSM 読み取り・DynamoDB 読み書き権限があること
"""

import json
import os
import math
import random
import urllib.parse
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

# 同じ CodeUri (backend/lambda/batch/) 内の generate_score.py が持つ
# ヘルパーをそのまま再利用する（HTTP GET・SSM取得・Gemini呼び出し）
from generate_score import _http_get_json, _get_table, ssm, genai

PLACES_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

# Google Places API キーの SSM パラメータ名（先頭スラッシュなし。
# SAM の SSMParameterReadPolicy が "parameter/${ParameterName}" でARNを組み立てるため）
GOOGLE_PLACES_API_KEY_PARAM = "fishing-ai/google-places-api-key"
# Gemini API キーは generate_score.py と同じパラメータを共有する
GEMINI_API_KEY_PARAM = "/fishing-ai/gemini-api-key"

SPOTS_TABLE = os.environ.get("SPOTS_TABLE", "fishing-spots")

# 検索キーワード（複数投げて候補の網羅性を上げる）
SEARCH_QUERIES = ["釣り 堤防", "釣り 波止", "釣り公園"]

# 基準地点（東京駅）。distanceKm の算出に使用。フロントの MapPage.tsx の
# DEFAULT_CENTER と一致させている
BASE_LAT = 35.681
BASE_LNG = 139.767

# 重複とみなす距離のしきい値（メートル）
DUPLICATE_THRESHOLD_M = 300

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}


def _get_places_api_key() -> str:
    """SSM Parameter StoreからGoogle Places APIキーを取得する。"""
    try:
        response = ssm.get_parameter(Name=GOOGLE_PLACES_API_KEY_PARAM, WithDecryption=True)
        return response["Parameter"]["Value"]
    except ClientError as e:
        print(f"SSM get_parameter error (places key): {e}")
        return ""


def _get_gemini_api_key() -> str:
    """SSM Parameter StoreからGemini APIキーを取得する（generate_score.pyと同一パラメータ）。"""
    try:
        response = ssm.get_parameter(Name=GEMINI_API_KEY_PARAM, WithDecryption=True)
        return response["Parameter"]["Value"]
    except ClientError as e:
        print(f"SSM get_parameter error (gemini key): {e}")
        return ""


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """2点間の距離をhaversine公式でkm単位で算出する。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def search_places(query: str, api_key: str) -> list[dict[str, Any]]:
    """Google Places API Text Search で候補地点を検索する。

    Args:
        query   (str): 検索クエリ（例: "釣り 堤防"）
        api_key (str): Google Places API キー

    Returns:
        list[dict[str, Any]]: 検索結果（name / lat / lng / address を含む辞書のリスト）。
            APIエラー時は空リストを返しバッチ全体は継続させる。
    """
    try:
        # _http_get_json は値を "&".join(f"{k}={v}") でそのまま連結する（内部でURLエンコードしない
        # generate_score.py と同じ挙動）ため、日本語クエリはここで事前に percent-encode する
        params = {
            "query": urllib.parse.quote(query),
            "region": "jp",
            "language": "ja",
            "key": api_key,
        }
        data = _http_get_json(PLACES_TEXT_SEARCH_URL, params)
        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            print(f"Places API non-OK status for '{query}': {data.get('status')}")
            return []

        results = []
        for r in data.get("results", []):
            loc = r.get("geometry", {}).get("location", {})
            if "lat" not in loc or "lng" not in loc:
                continue
            results.append({
                "name": r.get("name", "名称不明"),
                "lat": float(loc["lat"]),
                "lng": float(loc["lng"]),
                "address": r.get("formatted_address", ""),
            })
        return results

    except Exception as e:
        print(f"Places API error for '{query}': {e}")
        return []


def guess_fish_types(spot_name: str, address: str, api_key: str) -> list[str]:
    """Gemini APIで地名・住所から想定される魚種を推測する。

    APIキー未設定時・エラー時は汎用デフォルトを返し、バッチを継続させる。

    Args:
        spot_name (str): スポット名
        address   (str): 住所
        api_key   (str): Gemini API キー

    Returns:
        list[str]: 推測された魚種リスト（3〜5種）
    """
    default_fish = ["アジ", "サバ", "イワシ"]
    if not api_key:
        return default_fish

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-flash-latest")
        prompt = f"""次の釣り場で一般的に釣れる魚種を3〜5種、日本語の魚名のみカンマ区切りで答えてください。前置き・説明は不要です。

場所: {spot_name}（{address}）"""
        response = model.generate_content(prompt)
        fish = [f.strip() for f in response.text.strip().split(",") if f.strip()]
        return fish[:5] if fish else default_fish

    except Exception as e:
        print(f"Gemini fish-type guess error: {e}")
        return default_fish


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Google Places API で新規釣りスポット候補を探索し、Spots テーブルに追加する。

    既存スポットと近傍（300m以内）の候補は重複として除外する。

    Args:
        event   (dict[str, Any]): Lambda イベントオブジェクト（内容は不使用）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200:
                {
                    "status": "completed",
                    "addedCount": int,   # 新規追加したスポット数
                    "skippedCount": int  # 重複として除外した数
                }
            Places APIキー未設定時 200:
                {"status": "skipped", "message": "..."}
    """
    print("discoverSpotsBatch started")

    places_key = _get_places_api_key()
    if not places_key:
        return {
            "statusCode": 200,
            "headers": CORS,
            "body": json.dumps({"status": "skipped", "message": "Google Places API key not configured"}),
        }

    spots_table = _get_table(SPOTS_TABLE)
    existing_spots: list[dict[str, Any]] = spots_table.scan()["Items"]
    existing_coords = [(float(s.get("lat", 0)), float(s.get("lng", 0))) for s in existing_spots]

    # 複数クエリの結果を集約し、クエリ間の重複も除去する
    candidates: dict[str, dict[str, Any]] = {}
    for query in SEARCH_QUERIES:
        for c in search_places(query, places_key):
            key = f"{c['lat']:.5f},{c['lng']:.5f}"
            candidates.setdefault(key, c)

    gemini_key = _get_gemini_api_key()
    added, skipped = 0, 0

    for c in candidates.values():
        # 既存スポットと近傍（300m以内）なら重複とみなしてスキップ
        is_duplicate = any(
            haversine_km(c["lat"], c["lng"], elat, elng) * 1000 < DUPLICATE_THRESHOLD_M
            for elat, elng in existing_coords
        )
        if is_duplicate:
            skipped += 1
            continue

        distance_km = haversine_km(BASE_LAT, BASE_LNG, c["lat"], c["lng"])
        fish_types = guess_fish_types(c["name"], c["address"], gemini_key)

        spot_id = f"spot-{random.getrandbits(32):08x}"
        spots_table.put_item(Item={
            "spotId": spot_id,
            "name": c["name"],
            "lat": Decimal(str(c["lat"])),
            "lng": Decimal(str(c["lng"])),
            "fishTypes": fish_types,
            "distanceKm": Decimal(str(round(distance_km, 1))),
            "costYen": Decimal("0"),
            "description": c["address"],
        })
        # 次の候補との重複判定にも反映させる
        existing_coords.append((c["lat"], c["lng"]))
        added += 1
        print(f"  Added: {c['name']} ({c['address']})")

    result = {"status": "completed", "addedCount": added, "skippedCount": skipped}
    return {"statusCode": 200, "headers": CORS, "body": json.dumps(result)}
