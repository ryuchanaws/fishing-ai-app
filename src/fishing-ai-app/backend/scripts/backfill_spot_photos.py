"""
backfill_spot_photos.py

既存スポット（Gemini→Claude移行前・Google Places Photos対応前に登録されたもの）のうち
imageUrl が未設定のものに対して、Google Places API で写真を再検索・取得しS3へアップロードする
一度きりのメンテナンススクリプト。

discover_spots.run_discovery() は新規発見時にその場でphoto_referenceを持っているが、
既存スポットはそれを保存していないため、スポット名で再検索して写真を探し直す。

常設のLambda/APIエンドポイントにはしていない（一度きりの作業のため）。
discover_spots.py の関数（search_places / fetch_and_store_place_photo / get_ssm_parameter）を
そのままimportして再利用する。

実行方法（ローカル環境、AWS認証情報設定済みであること）:
    cd backend/lambda/batch
    SPOTS_TABLE=fishing-spots \
    UPLOADS_BUCKET=fishing-ai-app-uploads-<AWSアカウントID> \
    AWS_REGION=ap-northeast-1 \
    python ../../scripts/backfill_spot_photos.py

既にimageUrlが設定済みのスポットはスキップするため、再実行しても安全（冪等）。
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda", "batch"))

from discover_spots import search_places, fetch_and_store_place_photo, GOOGLE_PLACES_API_KEY_PARAM  # noqa: E402
from batch_common import get_table, get_ssm_parameter  # noqa: E402

# Places APIへの負荷・レート制限を避けるための待機（秒）
REQUEST_INTERVAL_SEC = 0.5


def backfill() -> None:
    spots_table = get_table(os.environ.get("SPOTS_TABLE", "fishing-spots"))
    places_key = get_ssm_parameter(GOOGLE_PLACES_API_KEY_PARAM)
    if not places_key:
        print("Google Places API key not configured (SSM). Aborting.")
        return

    spots = spots_table.scan()["Items"]
    targets = [s for s in spots if not s.get("imageUrl")]
    print(f"Total spots: {len(spots)} / missing imageUrl: {len(targets)}")

    updated, skipped = 0, 0
    for spot in targets:
        spot_id = spot["spotId"]
        name = spot.get("name", spot_id)
        lat, lng = spot.get("lat"), spot.get("lng")

        location_bias = {"lat": float(lat), "lng": float(lng)} if lat is not None and lng is not None else None
        candidates = search_places(name, places_key, location_bias)
        photo_reference = candidates[0].get("photo_reference") if candidates else None

        if not photo_reference:
            print(f"  [skip] {name} ({spot_id}): no photo found")
            skipped += 1
            time.sleep(REQUEST_INTERVAL_SEC)
            continue

        image_url = fetch_and_store_place_photo(photo_reference, spot_id, places_key)
        if not image_url:
            print(f"  [skip] {name} ({spot_id}): photo fetch/upload failed")
            skipped += 1
            time.sleep(REQUEST_INTERVAL_SEC)
            continue

        spots_table.update_item(
            Key={"spotId": spot_id},
            UpdateExpression="SET imageUrl = :u",
            ExpressionAttributeValues={":u": image_url},
        )
        print(f"  [ok]   {name} ({spot_id}) -> {image_url}")
        updated += 1
        time.sleep(REQUEST_INTERVAL_SEC)

    print(f"Done. updated={updated} skipped={skipped}")


if __name__ == "__main__":
    backfill()
