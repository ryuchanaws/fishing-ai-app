"""batch_common.py の get_user_id / check_and_increment_daily_usage のテスト
（moto で DynamoDB をモック。2026-07-26追加）。
"""

import importlib
import os

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def usage_table():
    """moto上にUsageTableを作成し、batch_commonをモック配下で再読み込みして返す。

    他のテストファイル同様、batch_common.py はimport時にモジュールレベルで
    boto3クライアントを生成するため、mock_aws()を開始した後にreloadする必要がある。
    """
    with mock_aws():
        client = boto3.client("dynamodb", region_name=os.environ["AWS_REGION"])
        client.create_table(
            TableName=os.environ["USAGE_TABLE"],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "dateKey", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "dateKey", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        import batch_common as bc

        importlib.reload(bc)
        yield bc


def test_get_user_id_from_claims_and_fallback():
    """Cognitoクレームがあればsubを、無ければDEFAULT_USER_IDを返す。"""
    import batch_common as bc

    assert bc.get_user_id({"requestContext": {"authorizer": {"claims": {"sub": "abc-123"}}}}) == "abc-123"
    assert bc.get_user_id({}) == bc.DEFAULT_USER_ID


def test_check_and_increment_daily_usage_within_and_over_limit(usage_table):
    """上限内はTrue、超過するとFalseを返す（handlers.pyの同名関数と同じ挙動）。"""
    bc = usage_table

    for _ in range(3):
        assert bc.check_and_increment_daily_usage("user-a", "ai-batch", 3) is True

    assert bc.check_and_increment_daily_usage("user-a", "ai-batch", 3) is False


def test_check_and_increment_daily_usage_is_per_action(usage_table):
    """アクション名ごとにカウンタが独立している（ai-batchの利用がspot-discoveryの枠を消費しない）。"""
    bc = usage_table

    for _ in range(3):
        bc.check_and_increment_daily_usage("user-a", "ai-batch", 3)

    assert bc.check_and_increment_daily_usage("user-a", "spot-discovery", 3) is True
