# 釣行AIアプリ — デプロイ手順

## 前提条件

- AWS CLI がインストール済みで認証済みであること
- GitHub リポジトリが作成済みであること
- Python 3.12 / Node.js 20 がインストール済みであること

---

## 1. AWS SSM にシークレット登録

Gemini API キーを AWS Systems Manager パラメータストアに安全に保存する。
Lambda の環境変数に直接書かずに SSM から取得することでセキュリティを高める。
（AIコメント生成にのみ使用。天気・潮汐データは APIキー不要の Open-Meteo を使用しており、
このシークレットは不要）

```bash
aws ssm put-parameter \
  --name fishing-ai/gemini-api-key \
  --value "AIzaxxxxxxxx" \
  --type SecureString
```

> `AIzaxxxxxxxx` は実際の Gemini API キーに置き換えること。
> Google AI Studio（https://aistudio.google.com/apikey）で取得できる。
>
> **注意:** パラメータ名の先頭にスラッシュを付けないこと（`fishing-ai/...` であって `/fishing-ai/...` ではない）。
> `template.yaml` の `SSMParameterReadPolicy` は内部で `parameter/${ParameterName}` として ARN を組み立てるため、
> 先頭にスラッシュを付けると `parameter//fishing-ai/...` という二重スラッシュのARNになり、
> 実際のパラメータと一致せず AccessDenied になる（2026-07-23 に実際に踏んだ不具合）。

---

## 2. GitHub Secrets 登録

GitHub Actions のワークフローから AWS や外部サービスに安全にアクセスするために
以下の Secrets をリポジトリに登録する。

**登録場所:** GitHub リポジトリ → Settings → Secrets and variables → Actions

| シークレット名 | 説明 | 取得場所 |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | AWS IAM ユーザーのアクセスキーID | AWS IAM コンソール |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM ユーザーのシークレットキー | AWS IAM コンソール |
| `S3_BUCKET` | フロントエンドをホストする S3 バケット名 | 手順3で作成 |
| `CLOUDFRONT_DISTRIBUTION_ID` | CloudFront ディストリビューション ID | AWS CloudFront コンソール |
| `VITE_API_BASE_URL` | API Gateway のエンドポイント URL | SAM デプロイ後の出力値 |
| `VITE_GOOGLE_MAPS_KEY` | Google Maps API キー | Google Cloud Console |

---

## 3. S3 バケット作成（静的ウェブホスティング）

React ビルド成果物をホストする S3 バケットを作成し、
静的ウェブサイトホスティングを有効化する。

```bash
# バケット作成（YOUR_BUCKET_NAME は一意の名前に変更すること）
aws s3 mb s3://YOUR_BUCKET_NAME --region ap-northeast-1

# 静的ウェブホスティング設定
# index.html をエントリーポイント、エラー時も index.html を返すことで
# React Router の SPA ルーティングを有効にする
aws s3 website s3://YOUR_BUCKET_NAME \
  --index-document index.html \
  --error-document index.html
```

> バケット名は全世界で一意である必要がある。
> 例: `fishing-ai-app-prod-202401` のように日付やプロジェクト名を含めると安全。

---

## 4. 初期データ投入

DynamoDB の `fishing-spots` テーブルにサンプルスポットデータを投入する。
このデータが AI 分析・スコア計算の対象となる。

```bash
cd backend

# boto3 をインストール（AWS SDK for Python）
pip install boto3

# シードスクリプト実行
# 実行前に AWS 認証情報が設定済みであること（~/.aws/credentials）
python seed_data.py
```

> `seed_data.py` には三浦半島・江ノ島など5スポットが定義済み。
> スポットを追加したい場合は `SPOTS` リストに追記して再実行すること。

---

## 5. デプロイ

main ブランチに push することで GitHub Actions が自動的に以下を実行する。

1. SAM ビルド → Lambda + DynamoDB を CloudFormation でデプロイ
2. React ビルド → S3 アップロード → CloudFront キャッシュ削除

```bash
git add .
git commit -m "feat: initial deploy"
git push origin main
```

> GitHub Actions の実行状況はリポジトリの Actions タブで確認できる。
> 初回デプロイは SAM スタック作成のため 5〜10 分程度かかる場合がある。

---

## 6. 動作確認

デプロイ完了後、以下の手順でアプリが正常に動作していることを確認する。

1. **CloudFront URL にアクセス**
   - AWS CloudFront コンソールでディストリビューションの URL を確認してブラウザで開く
   - 例: `https://xxxxxxxxxxxx.cloudfront.net`

2. **AI 分析を実行**
   - TOP ページの「AI 分析を実行」ボタンをクリック
   - ボタンが「AI 分析中...」に変わりスピナーが表示されることを確認
   - バッチ処理は非同期実行のため、ボタン押下直後にAPIは即座に応答するが、
     実際の完了（DynamoDB更新）まではフロントエンドが `GET /recommendations` を
     数秒おきにポーリングして待つ（5スポット分の天気・潮汐取得＋Gemini呼び出しで
     合計30秒前後かかる）。60秒待っても完了を検知できない場合は
     「バックグラウンドで実行中の可能性があります」という中立的な表示になる
     （エラーではなく、裏側では継続している可能性がある状態）

3. **結果を確認**
   - 分析完了後、釣りスポットのスコアと AI コメントが表示されることを確認
   - TOP3 ランキングと地図ピンが正しく表示されれば成功
   - スコアは実際の天気（Open-Meteo）・潮汐（Open-Meteo Marine、海面水位の変化率）に基づいて算出される

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| AI ボタンを押しても何も起きない | `VITE_API_BASE_URL` が未設定、または古いAPIエンドポイントを指している | GitHub Secrets とフロントの `.env` を確認して再デプロイ |
| AIコメントが毎回同じ定型文になる | Gemini API キーが読めていない、またはモデル名が廃止されている | SSMパラメータ名の先頭スラッシュ有無を確認（上記1参照）。CloudWatch Logs の `generateSpotScoreBatch` で `SSM get_parameter error` や `Gemini API error` が出ていないか確認 |
| 地図が表示されない | `VITE_GOOGLE_MAPS_KEY` が無効、または未設定 | Google Cloud Console で Maps JavaScript API を有効化。ローカルビルド（Cloudflare Pages等）には `frontend/.env` にも直接設定が必要（GitHub Secretsとは別管理） |
| スポットが表示されない | 初期データ未投入 | 手順4の `seed_data.py` を再実行 |
| Lambda がエラー | Gemini API キーが未設定・無効 | 手順1の SSM パラメータを確認 |

---

## 7. デプロイ先（2026-07-23 時点）

フロントエンドは2系統に並行デプロイしている。バックエンド（API Gateway/Lambda/DynamoDB）はAWS側1本のみで共通。

| デプロイ先 | URL | デプロイ方法 |
|---|---|---|
| AWS（CloudFront） | https://d2ny5ej5kn6jzs.cloudfront.net/ | `main` ブランチへの push で GitHub Actions が自動デプロイ |
| Cloudflare Pages | https://ryu-chan-fish.ryuchan-aws.workers.dev/ | `frontend` で `npm run build` の後 `npx wrangler pages deploy dist --project-name ryu-chan-fish`（手動デプロイ、CI化はしていない） |

> 独自ドメイン（有料）は未取得。無料で使える見た目のURLとして Cloudflare Pages の `*.workers.dev` サブドメインを利用している。