"""
discover_spots.py

Google Places API を使って新しい釣りスポット候補を探索し、
Spots テーブルに自動追加するバッチ処理。

run_discovery() が中核ロジックで、2つの経路から呼ばれる:
    1. generate_score.py の handler（「AI分析を実行」）から、位置指定なしで毎回呼ばれる
       （日本国内を広くカバーする固定キーワード検索）
    2. POST /admin/run-spot-discovery（フロントの「現在地から探す」ボタン）から、
       ユーザーの現在地（lat/lng）を指定して呼ばれる（現在地周辺に絞った検索）

背景:
    generateSpotScoreBatch は元々 Spots テーブルの中身を毎回re-scoreするだけで、
    新しいスポットを増やす手段がなかった。実在の場所データを使うため、
    LLMにスポット名や座標を直接生成させるのではなく、Google Places API の
    テキスト検索結果（実POIデータ）のみを候補として採用する。
    Gemini は座標や実在性に関わらない付随情報（想定される魚種）の推測にのみ使う。

Requirements:
    - 環境変数 SPOTS_TABLE が設定済みであること
    - SSM パラメータ /fishing-ai/google-places-api-key が登録済みであること
    - Lambda 実行ロールに SSM 読み取り・DynamoDB 読み書き権限があること
"""

import json
import os
import math
import random
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import quote

import google.generativeai as genai

from batch_common import http_get_json, get_table, get_ssm_parameter

PLACES_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

# SSMパラメータ名は "/"を含む階層型のため先頭スラッシュ必須（AWSの仕様）
GOOGLE_PLACES_API_KEY_PARAM = "/fishing-ai/google-places-api-key"
GEMINI_API_KEY_PARAM = "/fishing-ai/gemini-api-key"

SPOTS_TABLE = os.environ.get("SPOTS_TABLE", "fishing-spots")

# 位置指定なし（全国探索）時の検索キーワード
NATIONWIDE_QUERIES = ["釣り 堤防", "釣り 波止", "釣り公園"]
# 現在地指定あり（近傍探索）時の検索キーワード。位置バイアスで絞り込むためクエリは単純でよい
NEARBY_QUERY = "釣り"
# 現在地指定時の検索半径（メートル）
NEARBY_RADIUS_M = 15000

# 基準地点（東京駅）。位置指定なしの場合の distanceKm 算出に使用。
# フロントの MapPage.tsx の DEFAULT_CENTER と一致させている
DEFAULT_BASE_LAT = 35.681
DEFAULT_BASE_LNG = 139.767

# 重複とみなす距離のしきい値（メートル）
DUPLICATE_THRESHOLD_M = 300

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """2点間の距離をhaversine公式でkm単位で算出する。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def search_places(query: str, api_key: str, location_bias: Optional[dict[str, float]] = None) -> list[dict[str, Any]]:
    """Google Places API Text Search で候補地点を検索する。

    Args:
        query         (str): 検索クエリ（例: "釣り 堤防"）
        api_key       (str): Google Places API キー
        location_bias (dict, optional): {"lat": ..., "lng": ...} が指定された場合、
            NEARBY_RADIUS_M 以内の近傍検索として絞り込む

    Returns:
        list[dict[str, Any]]: 検索結果（name / lat / lng / address を含む辞書のリスト）。
            APIエラー時は空リストを返しバッチ全体は継続させる。
    """
    try:
        # http_get_json は値をそのまま連結する（URLエンコードしない）ため、
        # 日本語クエリはここで事前に percent-encode する
        params = {
            "query": quote(query),
            "region": "jp",
            "language": "ja",
            "key": api_key,
        }
        if location_bias:
            params["location"] = f"{location_bias['lat']},{location_bias['lng']}"
            params["radius"] = str(NEARBY_RADIUS_M)

        data = http_get_json(PLACES_TEXT_SEARCH_URL, params)
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


def run_discovery(location_bias: Optional[dict[str, float]] = None) -> dict[str, Any]:
    """新規釣りスポット候補を探索し、Spots テーブルに追加する中核ロジック。

    generate_score.py の handler（位置指定なし）と、
    POST /admin/run-spot-discovery（現在地指定あり）の両方から呼ばれる。
    既存スポットと近傍（300m以内）の候補は重複として除外する。

    Args:
        location_bias (dict, optional): {"lat": ..., "lng": ...}。
            指定時は現在地周辺（NEARBY_RADIUS_M以内）に絞った検索を行う。
            未指定時は全国向けの固定キーワードで検索する。

    Returns:
        dict[str, Any]: {"status": "completed"|"skipped", "addedCount": int, "skippedCount": int, "message"?: str}
    """
    places_key = get_ssm_parameter(GOOGLE_PLACES_API_KEY_PARAM)
    if not places_key:
        return {"status": "skipped", "message": "Google Places API key not configured", "addedCount": 0, "skippedCount": 0}

    spots_table = get_table(SPOTS_TABLE)
    existing_spots: list[dict[str, Any]] = spots_table.scan()["Items"]
    existing_coords = [(float(s.get("lat", 0)), float(s.get("lng", 0))) for s in existing_spots]

    queries = [NEARBY_QUERY] if location_bias else NATIONWIDE_QUERIES

    # 複数クエリの結果を集約し、クエリ間の重複も除去する
    candidates: dict[str, dict[str, Any]] = {}
    for query in queries:
        for c in search_places(query, places_key, location_bias):
            key = f"{c['lat']:.5f},{c['lng']:.5f}"
            candidates.setdefault(key, c)

    gemini_key = get_ssm_parameter(GEMINI_API_KEY_PARAM)
    base_lat = location_bias["lat"] if location_bias else DEFAULT_BASE_LAT
    base_lng = location_bias["lng"] if location_bias else DEFAULT_BASE_LNG
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

        distance_km = haversine_km(base_lat, base_lng, c["lat"], c["lng"])
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

    return {"status": "completed", "addedCount": added, "skippedCount": skipped}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """POST /admin/run-spot-discovery（adminRunSpotDiscovery経由）のエントリーポイント。

    「現在地から探す」ボタンから呼ばれ、event に lat/lng が含まれていれば
    現在地周辺に絞った検索を、含まれていなければ全国向けの検索を行う。

    Args:
        event   (dict[str, Any]): Lambda イベント。lat (float) / lng (float) を含み得る
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: statusCode=200、body に run_discovery() の結果
    """
    print("discoverSpotsBatch started")

    lat, lng = event.get("lat"), event.get("lng")
    location_bias = {"lat": float(lat), "lng": float(lng)} if lat is not None and lng is not None else None

    result = run_discovery(location_bias)
    return {"statusCode": 200, "headers": CORS, "body": json.dumps(result)}
