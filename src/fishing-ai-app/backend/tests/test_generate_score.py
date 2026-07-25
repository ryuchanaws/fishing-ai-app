"""generate_score.py の純粋関数（calc_score）のテスト。"""

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
