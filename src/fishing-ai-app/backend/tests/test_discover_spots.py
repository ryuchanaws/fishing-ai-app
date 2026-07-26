"""discover_spots.py の純粋関数（haversine_km・guess_fish_types）のテスト、
および釣具店除外ロジック（run_discovery）のテスト（moto で DynamoDB をモック）。
"""

import importlib
import os

import boto3
import discover_spots
import pytest
from moto import mock_aws


def test_haversine_km_same_point_is_zero():
    """同一地点同士の距離は0km。"""
    d = discover_spots.haversine_km(35.681, 139.767, 35.681, 139.767)
    assert d == 0.0


def test_haversine_km_known_distance_tokyo_to_yokohama():
    """東京駅〜横浜駅は実際には約27kmであり、許容誤差3km以内に収まること。"""
    tokyo = (35.681, 139.767)
    yokohama = (35.466, 139.622)
    d = discover_spots.haversine_km(*tokyo, *yokohama)
    assert 24.0 <= d <= 30.0


def test_guess_fish_types_without_api_key_returns_default():
    """APIキーが空文字の場合、Gemini呼び出しをせず汎用デフォルトを返す。"""
    result = discover_spots.guess_fish_types("テストスポット", "テスト住所", api_key="")
    assert result == ["アジ", "サバ", "イワシ"]


@pytest.fixture
def spots_table_for_discovery():
    """moto上にSpotsTableを作成し、batch_common/discover_spotsをモック配下で再読み込みして返す。

    batch_common.py はimport時にモジュールレベルでboto3クライアントを生成するため、
    test_handlers_moto.py の dynamodb_tables フィクスチャと同じ理由でreloadが必要。
    discover_spots.py は batch_common から get_table/get_ssm_parameter を
    `from ... import` しているため、batch_common → discover_spots の順でreloadする
    （先にbatch_common側のモック対応クライアントを再生成してから、discover_spots側に
    その新しい関数を再bindさせる必要があるため）。
    """
    with mock_aws():
        client = boto3.client("dynamodb", region_name=os.environ["AWS_REGION"])
        client.create_table(
            TableName=os.environ["SPOTS_TABLE"],
            AttributeDefinitions=[{"AttributeName": "spotId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "spotId", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # スポット写真アップロード先（2026-07-26追加）。put_objectにはバケットの実在が必要
        s3_client = boto3.client("s3", region_name=os.environ["AWS_REGION"])
        s3_client.create_bucket(
            Bucket=os.environ["UPLOADS_BUCKET"],
            CreateBucketConfiguration={"LocationConstraint": os.environ["AWS_REGION"]},
        )
        import batch_common
        import discover_spots as ds

        importlib.reload(batch_common)
        importlib.reload(ds)
        yield ds


def test_run_discovery_excludes_tackle_shops(monkeypatch, spots_table_for_discovery):
    """Google Placesのtypesに'store'を含む候補（釣具店等）はSpotsに追加されない。"""
    ds = spots_table_for_discovery
    monkeypatch.setattr(ds, "get_ssm_parameter", lambda name: "fake-places-key")
    monkeypatch.setattr(ds, "guess_fish_types", lambda *a, **k: ["アジ"])

    def fake_search_places(query, api_key, location_bias=None):
        return [
            {
                "name": "テスト釣具店", "lat": 35.1, "lng": 139.1,
                "address": "テスト住所1", "types": ["store", "point_of_interest"],
            },
            {
                "name": "テスト堤防", "lat": 35.2, "lng": 139.2,
                "address": "テスト住所2", "types": ["point_of_interest"],
            },
        ]

    monkeypatch.setattr(ds, "search_places", fake_search_places)

    result = ds.run_discovery()
    assert result["addedCount"] == 1
    assert result["skippedCount"] == 1

    table = ds.get_table(os.environ["SPOTS_TABLE"])
    names = [i["name"] for i in table.scan()["Items"]]
    assert "テスト堤防" in names
    assert "テスト釣具店" not in names


def test_fetch_and_store_place_photo_uploads_and_returns_public_url(monkeypatch, spots_table_for_discovery):
    """写真バイトの取得に成功したらS3へアップロードし、公開URLを返す（2026-07-26追加）。"""
    ds = spots_table_for_discovery
    monkeypatch.setattr(ds, "http_get_bytes", lambda url, params: b"fake-jpeg-bytes")

    url = ds.fetch_and_store_place_photo("fake-photo-ref", "spot-abc123", "fake-places-key")

    assert url == f"https://{os.environ['UPLOADS_BUCKET']}.s3.{os.environ['AWS_REGION']}.amazonaws.com/spot-photos/spot-abc123.jpg"

    obj = ds.s3.get_object(Bucket=os.environ["UPLOADS_BUCKET"], Key="spot-photos/spot-abc123.jpg")
    assert obj["Body"].read() == b"fake-jpeg-bytes"


def test_fetch_and_store_place_photo_returns_none_on_error(monkeypatch, spots_table_for_discovery):
    """Places Photo API呼び出しが失敗した場合はNoneを返し、例外を投げない。"""
    ds = spots_table_for_discovery

    def raise_error(url, params):
        raise Exception("boom")

    monkeypatch.setattr(ds, "http_get_bytes", raise_error)

    assert ds.fetch_and_store_place_photo("fake-photo-ref", "spot-abc123", "fake-places-key") is None


def test_run_discovery_sets_image_url_when_photo_reference_present(monkeypatch, spots_table_for_discovery):
    """候補にphoto_referenceがあれば、写真を取得してSpotsのimageUrlに設定する。"""
    ds = spots_table_for_discovery
    monkeypatch.setattr(ds, "get_ssm_parameter", lambda name: "fake-places-key")
    monkeypatch.setattr(ds, "guess_fish_types", lambda *a, **k: ["アジ"])
    monkeypatch.setattr(ds, "fetch_and_store_place_photo", lambda ref, spot_id, key: "https://example.com/photo.jpg")

    def fake_search_places(query, api_key, location_bias=None):
        return [{
            "name": "写真ありスポット", "lat": 35.3, "lng": 139.3,
            "address": "テスト住所3", "types": ["point_of_interest"], "photo_reference": "ref-xyz",
        }]

    monkeypatch.setattr(ds, "search_places", fake_search_places)

    result = ds.run_discovery()
    assert result["addedCount"] == 1

    table = ds.get_table(os.environ["SPOTS_TABLE"])
    items = table.scan()["Items"]
    assert items[0]["imageUrl"] == "https://example.com/photo.jpg"
