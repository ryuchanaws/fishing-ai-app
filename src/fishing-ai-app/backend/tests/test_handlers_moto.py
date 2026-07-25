"""
handlers.py のハンドラーレベルのテスト（moto で DynamoDB をモック）。

実AWSには接続せず、moto がインメモリで再現するDynamoDBに対して
API Gateway形式のイベントでハンドラーを直接呼び出し、レスポンスとテーブルの
状態を検証する。投稿・チャットそれぞれの「作成→取得→削除→消えていることを確認」
というライフサイクルを通しで検証する（削除機能の主な回帰防止が目的）。
"""

import importlib
import json
import os

import boto3
import pytest
from moto import mock_aws


def _api_event(body: dict | None = None, path_params: dict | None = None) -> dict:
    """API Gatewayイベントの最小限のダミーを組み立てる。"""
    return {
        "body": json.dumps(body) if body is not None else None,
        "pathParameters": path_params,
        "queryStringParameters": None,
    }


@pytest.fixture
def dynamodb_tables():
    """moto上にPosts/ChatsテーブルをSAMテンプレートと同じキー構成で作成し、
    handlers モジュールをこのモック配下で再読み込みして返す。

    handlers.py は import 時にモジュールレベルで boto3.resource("dynamodb") 等の
    クライアントを生成する。他のテストファイル（test_handlers_pure.py 等）が
    先にモック無しで import 済みだと、以後 `import handlers` しても
    キャッシュされた（モック非対応の）クライアントを参照してしまい実AWSに
    到達してしまう。importlib.reload でモック有効時に確実に再生成する。
    """
    with mock_aws():
        client = boto3.client("dynamodb", region_name=os.environ["AWS_REGION"])
        client.create_table(
            TableName=os.environ["POSTS_TABLE"],
            AttributeDefinitions=[{"AttributeName": "postId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "postId", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName=os.environ["CHATS_TABLE"],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "chatId", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "chatId", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        import handlers

        importlib.reload(handlers)
        yield handlers


def test_post_lifecycle_create_then_delete(dynamodb_tables):
    """投稿を作成→一覧に含まれる→削除→一覧から消えることを確認する。"""
    handlers = dynamodb_tables

    create_resp = handlers.postPostsHandler(
        _api_event({"spotId": "spot-001", "content": "テスト投稿"}), None
    )
    assert create_resp["statusCode"] == 201
    post_id = json.loads(create_resp["body"])["post"]["postId"]

    list_resp = handlers.getPostsHandler(_api_event(), None)
    items = json.loads(list_resp["body"])["items"]
    assert any(p["postId"] == post_id for p in items)

    delete_resp = handlers.deletePostHandler(_api_event(path_params={"postId": post_id}), None)
    assert delete_resp["statusCode"] == 200

    list_resp_after = handlers.getPostsHandler(_api_event(), None)
    items_after = json.loads(list_resp_after["body"])["items"]
    assert not any(p["postId"] == post_id for p in items_after)


def test_delete_post_without_id_returns_400(dynamodb_tables):
    """postId未指定でDELETEすると400を返す。"""
    handlers = dynamodb_tables

    resp = handlers.deletePostHandler(_api_event(path_params={}), None)
    assert resp["statusCode"] == 400


def test_chat_lifecycle_seed_then_delete(dynamodb_tables):
    """（Gemini呼び出しを避けるためDBへ直接シードした）チャットを取得→削除→404になることを確認する。"""
    handlers = dynamodb_tables

    table = handlers._get_table(os.environ["CHATS_TABLE"])
    table.put_item(Item={
        "userId": handlers.DEFAULT_USER_ID,
        "chatId": "chat-001",
        "title": "テスト会話",
        "messages": [],
        "createdAt": "2026-01-01T00:00:00+00:00",
        "updatedAt": "2026-01-01T00:00:00+00:00",
    })

    get_resp = handlers.getChatHandler(_api_event(path_params={"chatId": "chat-001"}), None)
    assert get_resp["statusCode"] == 200

    delete_resp = handlers.deleteChatHandler(_api_event(path_params={"chatId": "chat-001"}), None)
    assert delete_resp["statusCode"] == 200

    get_resp_after = handlers.getChatHandler(_api_event(path_params={"chatId": "chat-001"}), None)
    assert get_resp_after["statusCode"] == 404


def test_delete_chat_without_id_returns_400(dynamodb_tables):
    """chatId未指定でDELETEすると400を返す。"""
    handlers = dynamodb_tables

    resp = handlers.deleteChatHandler(_api_event(path_params={}), None)
    assert resp["statusCode"] == 400
