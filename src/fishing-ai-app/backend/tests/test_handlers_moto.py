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
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws


def _api_event(
    body: dict | None = None, path_params: dict | None = None, user_id: str | None = None
) -> dict:
    """API Gatewayイベントの最小限のダミーを組み立てる。

    user_id を指定すると、CognitoAuthorizerを通過した場合と同じ形の
    requestContext.authorizer.claims.sub を持つイベントを作る。
    """
    event: dict = {
        "body": json.dumps(body) if body is not None else None,
        "pathParameters": path_params,
        "queryStringParameters": None,
    }
    if user_id is not None:
        event["requestContext"] = {"authorizer": {"claims": {"sub": user_id}}}
    return event


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
        client.create_table(
            TableName=os.environ["USERS_TABLE"],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName=os.environ["SPOTS_TABLE"],
            AttributeDefinitions=[{"AttributeName": "spotId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "spotId", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName=os.environ["RECOMMENDATIONS_TABLE"],
            AttributeDefinitions=[{"AttributeName": "spotId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "spotId", "KeyType": "HASH"}],
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


def test_delete_post_by_other_user_returns_403(dynamodb_tables):
    """他人（別userId）の投稿を削除しようとすると403になり、投稿は消えない。"""
    handlers = dynamodb_tables

    create_resp = handlers.postPostsHandler(
        _api_event({"spotId": "spot-001", "content": "user-aの投稿"}, user_id="user-a"),
        None,
    )
    post_id = json.loads(create_resp["body"])["post"]["postId"]
    assert json.loads(create_resp["body"])["post"]["userId"] == "user-a"

    forbidden_resp = handlers.deletePostHandler(
        _api_event(path_params={"postId": post_id}, user_id="user-b"), None
    )
    assert forbidden_resp["statusCode"] == 403

    list_resp = handlers.getPostsHandler(_api_event(), None)
    items = json.loads(list_resp["body"])["items"]
    assert any(p["postId"] == post_id for p in items)


def test_delete_post_by_owner_succeeds(dynamodb_tables):
    """投稿者本人（同じuserId）による削除は成功する。"""
    handlers = dynamodb_tables

    create_resp = handlers.postPostsHandler(
        _api_event({"spotId": "spot-001", "content": "user-aの投稿"}, user_id="user-a"),
        None,
    )
    post_id = json.loads(create_resp["body"])["post"]["postId"]

    delete_resp = handlers.deletePostHandler(
        _api_event(path_params={"postId": post_id}, user_id="user-a"), None
    )
    assert delete_resp["statusCode"] == 200


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


def test_daily_usage_within_limit_allows_calls(dynamodb_tables):
    """上限に達するまでは _check_and_increment_daily_usage が True を返し続ける。"""
    handlers = dynamodb_tables

    for _ in range(3):
        assert handlers._check_and_increment_daily_usage("user-a", "chat", 3) is True


def test_daily_usage_exceeding_limit_returns_false(dynamodb_tables):
    """上限を超えた回数目の呼び出しはFalseを返す（Gemini呼び出しをスキップさせるため）。"""
    handlers = dynamodb_tables

    for _ in range(3):
        handlers._check_and_increment_daily_usage("user-a", "chat", 3)

    assert handlers._check_and_increment_daily_usage("user-a", "chat", 3) is False


def test_daily_usage_is_per_user(dynamodb_tables):
    """カウンタはuserId単位で独立している（他人の利用で自分の枠が減らない）。"""
    handlers = dynamodb_tables

    for _ in range(3):
        handlers._check_and_increment_daily_usage("user-a", "chat", 3)

    assert handlers._check_and_increment_daily_usage("user-b", "chat", 3) is True


def test_get_my_profile_returns_null_display_name_when_unset(dynamodb_tables):
    """一度もプロフィールを設定していないユーザーはdisplayName: nullで200を返す（404にしない）。"""
    handlers = dynamodb_tables

    resp = handlers.getMyProfileHandler(_api_event(user_id="user-a"), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["userId"] == "user-a"
    assert body["displayName"] is None


def test_put_my_profile_then_get_reflects_new_name(dynamodb_tables):
    """表示名を設定すると、以後のGET /meに反映される。"""
    handlers = dynamodb_tables

    put_resp = handlers.putMyProfileHandler(
        _api_event({"displayName": "りゅうちゃん"}, user_id="user-a"), None
    )
    assert put_resp["statusCode"] == 200
    assert json.loads(put_resp["body"])["displayName"] == "りゅうちゃん"

    get_resp = handlers.getMyProfileHandler(_api_event(user_id="user-a"), None)
    assert json.loads(get_resp["body"])["displayName"] == "りゅうちゃん"


def test_put_my_profile_rejects_empty_name(dynamodb_tables):
    """空文字・空白のみの表示名は400を返す。"""
    handlers = dynamodb_tables

    resp = handlers.putMyProfileHandler(_api_event({"displayName": "   "}, user_id="user-a"), None)
    assert resp["statusCode"] == 400


def test_put_my_profile_rejects_too_long_name(dynamodb_tables):
    """DISPLAY_NAME_MAX_LEN（30文字）を超える表示名は400を返す。"""
    handlers = dynamodb_tables

    resp = handlers.putMyProfileHandler(
        _api_event({"displayName": "あ" * 31}, user_id="user-a"), None
    )
    assert resp["statusCode"] == 400


def test_get_posts_includes_author_display_name(dynamodb_tables):
    """投稿一覧には投稿者の表示名（authorName）がUsersTableと結合されて付与される。"""
    handlers = dynamodb_tables

    handlers.putMyProfileHandler(_api_event({"displayName": "りゅうちゃん"}, user_id="user-a"), None)
    handlers.postPostsHandler(
        _api_event({"spotId": "spot-001", "content": "テスト投稿"}, user_id="user-a"), None
    )

    resp = handlers.getPostsHandler(_api_event(), None)
    items = json.loads(resp["body"])["items"]
    assert items[0]["authorName"] == "りゅうちゃん"


def test_get_posts_author_name_defaults_to_anonymous(dynamodb_tables):
    """表示名を未設定のユーザーの投稿はauthorName: "匿名"になる。"""
    handlers = dynamodb_tables

    handlers.postPostsHandler(
        _api_event({"spotId": "spot-001", "content": "テスト投稿"}, user_id="user-b"), None
    )

    resp = handlers.getPostsHandler(_api_event(), None)
    items = json.loads(resp["body"])["items"]
    assert items[0]["authorName"] == "匿名"


def test_build_spots_context_includes_score_and_fish_types(dynamodb_tables):
    """_build_spots_context はSpots/Recommendationsを結合し、魚種・スコアを含むテキストを返す。"""
    handlers = dynamodb_tables

    spots_table = handlers._get_table(os.environ["SPOTS_TABLE"])
    recs_table = handlers._get_table(os.environ["RECOMMENDATIONS_TABLE"])
    spots_table.put_item(Item={
        "spotId": "spot-001",
        "name": "テスト堤防",
        "lat": Decimal("35.0"),
        "lng": Decimal("139.0"),
        "fishTypes": ["アジ"],
        "description": "テスト県",
    })
    recs_table.put_item(Item={"spotId": "spot-001", "score": Decimal("80")})

    context = handlers._build_spots_context()
    assert "テスト堤防" in context
    assert "アジ" in context
    assert "スコア=80" in context


def test_build_spots_context_empty_when_no_spots(dynamodb_tables):
    """スポットが1件も無い場合は空文字列を返す（チャットのプロンプトに余計な文言を足さない）。"""
    handlers = dynamodb_tables

    assert handlers._build_spots_context() == ""


def test_build_spots_context_sorts_by_distance_when_location_given(dynamodb_tables):
    """現在地(lat/lng)を渡すと、距離が近いスポットが先に来る順にソートされる。"""
    handlers = dynamodb_tables

    spots_table = handlers._get_table(os.environ["SPOTS_TABLE"])
    spots_table.put_item(Item={
        "spotId": "far", "name": "遠いスポット",
        "lat": Decimal("36.0"), "lng": Decimal("140.0"), "fishTypes": [],
    })
    spots_table.put_item(Item={
        "spotId": "near", "name": "近いスポット",
        "lat": Decimal("35.01"), "lng": Decimal("139.01"), "fishTypes": [],
    })

    context = handlers._build_spots_context(35.0, 139.0)
    assert context.index("近いスポット") < context.index("遠いスポット")
    assert "現在地から" in context
