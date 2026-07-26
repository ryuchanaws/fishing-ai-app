"""admin_trigger.py のユニットテスト。

Lambda呼び出し(lambda_client.invoke)とレート制限チェックをmonkeypatchし、
実際のAWSには一切接続しない（2026-07-26追加: AI分析実行・新スポット探索のコスト保護用
レート制限を検証する）。
"""

import json
from unittest.mock import MagicMock

import admin_trigger


def test_handler_starts_batch_when_within_limit(monkeypatch):
    """レート制限内であれば通常通りバッチをEvent呼び出しし、202を返す。"""
    monkeypatch.setattr(admin_trigger, "get_user_id", lambda event: "user-a")
    monkeypatch.setattr(admin_trigger, "check_and_increment_daily_usage", lambda *a, **k: True)
    mock_invoke = MagicMock()
    monkeypatch.setattr(admin_trigger, "lambda_client", MagicMock(invoke=mock_invoke))

    resp = admin_trigger.handler({"httpMethod": "POST", "body": "{}"}, None)

    assert resp["statusCode"] == 202
    assert json.loads(resp["body"])["status"] == "started"
    mock_invoke.assert_called_once()


def test_handler_returns_429_when_rate_limited(monkeypatch):
    """1日あたりの上限に達している場合はバッチを起動せず429を返す。"""
    monkeypatch.setattr(admin_trigger, "get_user_id", lambda event: "user-a")
    monkeypatch.setattr(admin_trigger, "check_and_increment_daily_usage", lambda *a, **k: False)
    mock_invoke = MagicMock()
    monkeypatch.setattr(admin_trigger, "lambda_client", MagicMock(invoke=mock_invoke))

    resp = admin_trigger.handler({"httpMethod": "POST", "body": "{}"}, None)

    assert resp["statusCode"] == 429
    assert json.loads(resp["body"])["status"] == "rate_limited"
    mock_invoke.assert_not_called()


def test_handler_options_request_bypasses_rate_limit_check(monkeypatch):
    """CORSプリフライト（OPTIONS）はレート制限チェックより前に200を返す（カウントしない）。"""
    calls = []
    monkeypatch.setattr(
        admin_trigger, "check_and_increment_daily_usage", lambda *a, **k: calls.append(1) or True
    )

    resp = admin_trigger.handler({"httpMethod": "OPTIONS"}, None)

    assert resp["statusCode"] == 200
    assert calls == []
