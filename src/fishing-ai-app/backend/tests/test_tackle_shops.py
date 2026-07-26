"""tackle_shops.py のユニットテスト。

DynamoDBへの書き込みが一切無いため moto は不要。search_places・get_ssm_parameter・
check_and_increment_daily_usage を monkeypatch し、実際のAWS/Google Places APIには
一切接続しない。
"""

import json

import pytest

import tackle_shops


@pytest.fixture(autouse=True)
def _allow_rate_limit(monkeypatch):
    """デフォルトではレート制限に掛からないようにする（レート制限自体のテストでは上書きする）。"""
    monkeypatch.setattr(tackle_shops, "check_and_increment_daily_usage", lambda *a, **k: True)


def test_handler_returns_empty_items_without_api_key(monkeypatch):
    """Places APIキー未登録時はitems: []を返す（discover_spots.pyのskipped方針を踏襲）。"""
    monkeypatch.setattr(tackle_shops, "get_ssm_parameter", lambda name: "")

    resp = tackle_shops.handler({"body": json.dumps({})}, None)

    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["items"] == []


def test_handler_sorts_results_by_distance_when_location_given(monkeypatch):
    """lat/lng指定時は距離を計算し、近い順にソートして返す。"""
    monkeypatch.setattr(tackle_shops, "get_ssm_parameter", lambda name: "fake-places-key")

    def fake_search_places(query, api_key, location_bias=None):
        assert "釣具店" in query
        return [
            {"name": "遠い店", "lat": 35.1, "lng": 139.1, "address": "住所1", "types": ["store"]},
            {"name": "近い店", "lat": 35.001, "lng": 139.001, "address": "住所2", "types": ["store"]},
        ]

    monkeypatch.setattr(tackle_shops, "search_places", fake_search_places)

    resp = tackle_shops.handler({"body": json.dumps({"lat": 35.0, "lng": 139.0})}, None)

    items = json.loads(resp["body"])["items"]
    assert items[0]["name"] == "近い店"
    assert items[0]["distanceKm"] < items[1]["distanceKm"]


def test_handler_keyword_search_without_location_has_no_distance(monkeypatch):
    """キーワード検索のみ（lat/lng省略）の場合、distanceKmは付与されない。"""
    monkeypatch.setattr(tackle_shops, "get_ssm_parameter", lambda name: "fake-places-key")

    captured = {}

    def fake_search_places(query, api_key, location_bias=None):
        captured["query"] = query
        captured["location_bias"] = location_bias
        return [{"name": "店", "lat": 35.0, "lng": 139.0, "address": "住所", "types": ["store"]}]

    monkeypatch.setattr(tackle_shops, "search_places", fake_search_places)

    resp = tackle_shops.handler({"body": json.dumps({"keyword": "神奈川県"})}, None)

    items = json.loads(resp["body"])["items"]
    assert "distanceKm" not in items[0]
    assert captured["location_bias"] is None
    assert "神奈川県" in captured["query"]


def test_handler_caps_results_at_max_results(monkeypatch):
    """検索結果がMAX_RESULTSを超えても、レスポンスはMAX_RESULTS件に切り詰められる。"""
    monkeypatch.setattr(tackle_shops, "get_ssm_parameter", lambda name: "fake-places-key")
    many_results = [
        {"name": f"店{i}", "lat": 35.0, "lng": 139.0, "address": "住所", "types": ["store"]}
        for i in range(tackle_shops.MAX_RESULTS + 10)
    ]
    monkeypatch.setattr(tackle_shops, "search_places", lambda *a, **k: many_results)

    resp = tackle_shops.handler({"body": json.dumps({})}, None)

    items = json.loads(resp["body"])["items"]
    assert len(items) == tackle_shops.MAX_RESULTS


def test_handler_returns_429_when_rate_limited(monkeypatch):
    """1日あたりの検索回数上限に達している場合はPlaces APIを呼ばずに429を返す（コスト保護）。"""
    monkeypatch.setattr(tackle_shops, "check_and_increment_daily_usage", lambda *a, **k: False)

    search_calls = []
    monkeypatch.setattr(tackle_shops, "search_places", lambda *a, **k: search_calls.append(1) or [])

    resp = tackle_shops.handler({"body": json.dumps({"keyword": "東京"})}, None)

    assert resp["statusCode"] == 429
    assert json.loads(resp["body"])["error"] == "rate_limited"
    assert search_calls == []
