"""
tackle_shops.py

釣具店（タックルショップ）をGoogle Places APIで検索し、そのまま返すLambda。
discover_spots.pyと違いDynamoDBへの書き込みは一切行わない（永続化しない、都度検索するだけ）。
スコアも付与しない、単純な検索結果一覧。POST /tackle-shops/search から呼ばれる。

現在地(lat/lng)指定時はsearch_places()の近傍バイアス検索＋距離順ソート、
keyword指定時はテキスト検索（例: "神奈川県三浦市"）を行う。両方省略時は全国向けの"釣具店"検索になる。

2026-07-26追加: おすすめ・新スポット探索からは釣具店を除外する一方（discover_spots.pyの
EXCLUDED_PLACE_TYPES参照）、釣具店を探したいニーズ自体はあるため別枠の検索機能として切り出した。
"""

import json
from typing import Any

from batch_common import get_ssm_parameter
from discover_spots import search_places, haversine_km

# SSMパラメータ名は"/"を含む階層型のため先頭スラッシュ必須（discover_spots.pyと同じ注意点）
GOOGLE_PLACES_API_KEY_PARAM = "/fishing-ai/google-places-api-key"

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}

# レスポンスに含める最大件数
MAX_RESULTS = 20


def _resp(status: int, body: dict[str, Any]) -> dict[str, Any]:
    """API Gateway 形式のレスポンスを組み立てる。"""
    return {"statusCode": status, "headers": CORS, "body": json.dumps(body)}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """POST /tackle-shops/search — 釣具店を検索して返す（DB書き込みなし・スコアなし）。

    Args:
        event (dict[str, Any]): API Gateway イベントオブジェクト（Cognito認証必須。
            Places API呼び出しは課金を伴うため未ログインでは呼べないようにしている）
            body (str): JSON文字列。
                lat/lng (float, 省略可): 現在地。指定時は近傍検索＋距離順ソート
                keyword (str, 省略可): 地名・県名等のテキスト検索キーワード
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]: statusCode=200、body に
            {"items": [{"name", "lat", "lng", "address", "distanceKm"?(lat/lng指定時のみ)}, ...]}
            Places APIキー未登録時はitems: []を返す（discover_spots.pyのskipped方針を踏襲）
    """
    body = json.loads(event.get("body") or "{}")
    lat, lng = body.get("lat"), body.get("lng")
    keyword = (body.get("keyword") or "").strip()

    places_key = get_ssm_parameter(GOOGLE_PLACES_API_KEY_PARAM)
    if not places_key:
        return _resp(200, {"items": []})

    query = f"釣具店 {keyword}".strip()
    location_bias = {"lat": float(lat), "lng": float(lng)} if lat is not None and lng is not None else None

    results = search_places(query, places_key, location_bias)

    if location_bias:
        for r in results:
            r["distanceKm"] = round(
                haversine_km(location_bias["lat"], location_bias["lng"], r["lat"], r["lng"]), 1
            )
        results.sort(key=lambda r: r["distanceKm"])

    items = [
        {
            "name": r["name"],
            "lat": r["lat"],
            "lng": r["lng"],
            "address": r["address"],
            **({"distanceKm": r["distanceKm"]} if "distanceKm" in r else {}),
        }
        for r in results[:MAX_RESULTS]
    ]

    return _resp(200, {"items": items})
