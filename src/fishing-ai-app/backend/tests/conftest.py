"""
conftest.py

pytest 共通設定。backend/lambda/api・backend/lambda/batch は SAM の CodeUri
ディレクトリであり、それぞれ独立した Lambda パッケージとして扱われる
（このディレクトリ自体はテスト対象外なので import パスを明示的に通す必要がある）。

環境変数はモジュールを import する前に設定する（handlers.py 等は import 時に
os.environ.get(...) でテーブル名を読み、boto3 クライアントを生成するため）。
"""

import os
import sys

TESTS_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.dirname(TESTS_DIR)

for sub in ("lambda/api", "lambda/batch"):
    path = os.path.join(BACKEND_DIR, *sub.split("/"))
    if path not in sys.path:
        sys.path.insert(0, path)

# moto でのテストと一致させるテーブル名・リージョン
os.environ.setdefault("AWS_REGION", "ap-northeast-1")
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")
os.environ.setdefault("SPOTS_TABLE", "test-fishing-spots")
os.environ.setdefault("RECOMMENDATIONS_TABLE", "test-fishing-recommendations")
os.environ.setdefault("FAVORITES_TABLE", "test-fishing-favorites")
os.environ.setdefault("POSTS_TABLE", "test-fishing-posts")
os.environ.setdefault("CHATS_TABLE", "test-fishing-chats")
os.environ.setdefault("UPLOADS_BUCKET", "test-fishing-ai-app-uploads")
# moto用のダミー認証情報を強制的に上書きする（setdefaultではなく代入）。
# 実行環境（このプロジェクトのAWS CLI用など）に本物の認証情報が環境変数として
# 既に設定されている場合、setdefaultでは上書きされず、moto非対応の呼び出しが
# 万一残っていた際に実AWSへ到達してしまう恐れがあるため
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
