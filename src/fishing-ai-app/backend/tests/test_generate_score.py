"""generate_score.py の純粋関数（calc_score・_should_regenerate_reason）のテスト。"""

from datetime import datetime, timedelta, timezone

import generate_score


def test_calc_score_perfect_conditions_no_distance_no_cost():
    """好条件（fish_prob/weather/tide全て100、距離・費用0）でも、
    重み(0.4+0.2+0.2=0.8)の合計が1.0未満なのでスコアは80.0が上限になる。"""
    score = generate_score.calc_score(fish_prob=100, weather=100, tide=100, distance_km=0, cost_yen=0)
    assert score == 80.0


def test_calc_score_worst_conditions():
    """悪条件（全て0、距離・費用が上限超過）ならスコアは最低の0になる。"""
    score = generate_score.calc_score(fish_prob=0, weather=0, tide=0, distance_km=200, cost_yen=10000)
    assert score == 0.0


def test_calc_score_distance_penalty_is_capped():
    """distance_km が正規化上限(100km)を超えても、ペナルティはそれ以上大きくならない。"""
    score_at_cap = generate_score.calc_score(fish_prob=80, weather=80, tide=80, distance_km=100, cost_yen=0)
    score_over_cap = generate_score.calc_score(fish_prob=80, weather=80, tide=80, distance_km=500, cost_yen=0)
    assert score_at_cap == score_over_cap


def test_calc_score_is_within_valid_range():
    """スコアは常に0.0〜100.0の範囲に収まる。"""
    score = generate_score.calc_score(fish_prob=50, weather=50, tide=50, distance_km=50, cost_yen=2500)
    assert 0.0 <= score <= 100.0


def _fresh_recommendation(score: float, minutes_ago: float = 0) -> dict:
    """テスト用のRecommendationsTableアイテムを組み立てる。"""
    updated_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {"score": score, "reason": "テスト理由文", "updatedAt": updated_at.isoformat()}


def test_should_regenerate_reason_when_no_existing_recommendation():
    """初回（既存データが無い）場合は必ず再生成する（2026-07-26追加）。"""
    assert generate_score._should_regenerate_reason(None, new_score=80.0) is True


def test_should_regenerate_reason_when_existing_has_no_reason():
    """既存データにreasonが無い（壊れたデータ等）場合も再生成する。"""
    existing = {"score": 80.0, "updatedAt": datetime.now(timezone.utc).isoformat()}
    assert generate_score._should_regenerate_reason(existing, new_score=80.0) is True


def test_should_regenerate_reason_when_score_changed_significantly():
    """スコアがREASON_SCORE_CHANGE_THRESHOLD以上動いていれば再生成する。"""
    existing = _fresh_recommendation(score=50.0)
    new_score = 50.0 + generate_score.REASON_SCORE_CHANGE_THRESHOLD
    assert generate_score._should_regenerate_reason(existing, new_score) is True


def test_should_regenerate_reason_reuses_when_score_barely_changed_and_fresh():
    """スコアの変化が閾値未満かつ最近生成済みなら、前回の文章を使い回す（再生成しない）。"""
    existing = _fresh_recommendation(score=50.0, minutes_ago=10)
    new_score = 50.0 + (generate_score.REASON_SCORE_CHANGE_THRESHOLD - 1)
    assert generate_score._should_regenerate_reason(existing, new_score) is False


def test_should_regenerate_reason_when_stale_even_if_score_unchanged():
    """スコアが変わっていなくても、REASON_MAX_AGE_DAYS日以上経過していれば再生成する。"""
    old_days = generate_score.REASON_MAX_AGE_DAYS * 24 * 60 + 1
    existing = _fresh_recommendation(score=50.0, minutes_ago=old_days)
    assert generate_score._should_regenerate_reason(existing, new_score=50.0) is True


def test_should_regenerate_reason_when_updated_at_missing_or_invalid():
    """updatedAtが無い/壊れている場合は安全側に倒して再生成する。"""
    no_updated_at = {"score": 50.0, "reason": "テスト理由文"}
    assert generate_score._should_regenerate_reason(no_updated_at, new_score=50.0) is True

    bad_updated_at = {"score": 50.0, "reason": "テスト理由文", "updatedAt": "not-a-date"}
    assert generate_score._should_regenerate_reason(bad_updated_at, new_score=50.0) is True
