"""handlers.py の純粋なユーティリティ関数（_decimal_to_float）のテスト。"""

from decimal import Decimal

import handlers


def test_decimal_to_float_converts_nested_structures():
    """リスト・辞書にネストしたDecimalも再帰的にfloatへ変換する。"""
    data = {
        "score": Decimal("87.5"),
        "items": [Decimal("1"), Decimal("2.5")],
        "nested": {"distance": Decimal("3.14")},
        "unchanged": "text",
    }
    result = handlers._decimal_to_float(data)

    assert result["score"] == 87.5
    assert isinstance(result["score"], float)
    assert result["items"] == [1.0, 2.5]
    assert result["nested"]["distance"] == 3.14
    assert result["unchanged"] == "text"
