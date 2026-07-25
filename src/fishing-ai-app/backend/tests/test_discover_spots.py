"""discover_spots.py の純粋関数（haversine_km・guess_fish_types）のテスト。"""

import discover_spots


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
