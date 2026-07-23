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
  --name /fishing-ai/gemini-api-key \
  --value "AIzaxxxxxxxx" \
  --type SecureString
```

> `AIzaxxxxxxxx` は実際の Gemini API キーに置き換えること。
> Google AI Studio（https://aistudio.google.com/apikey）で取得できる。
>
> **注意（2026-07-24 訂正）:** `aws ssm put-parameter`/`get-parameter` の `--name` に渡す
> **実際のパラメータ名**は、`/`を含む階層型の場合は先頭にスラッシュが必須（AWSの仕様。
> 付けないと `must be a fully qualified name` エラーになる）。上記コマンドは
> `/fishing-ai/gemini-api-key`（先頭スラッシュあり）が正しい。<br>
> 一方、`template.yaml` の `SSMParameterReadPolicy.ParameterName` は**逆に先頭スラッシュを付けない**
> （`fishing-ai/gemini-api-key`）のが正しい。SAM側が内部で `parameter/${ParameterName}` として
> 自動でスラッシュを補ってARNを組み立てるため、ここで自分でも付けると `parameter//...` という
> 二重スラッシュのARNになり実際のパラメータと一致せず AccessDenied になる（2026-07-23に実際に踏んだ不具合）。
> この2つのフィールドで先頭スラッシュの要不要が逆になっている点に注意すること。

「新スポットを探す」機能（discoverSpotsBatch）が使う Google Places API キーも同様に登録する。
Google Cloud Console で既存の Maps API と同じプロジェクトの「Places API」を有効化し、
課金アカウントを紐付けたうえでキーを発行すること（個人利用の頻度なら月$200の無料クレジット枠に収まる想定）。

```bash
aws ssm put-parameter \
  --name /fishing-ai/google-places-api-key \
  --value "AIzaxxxxxxxx" \
  --type SecureString
```

> このパラメータが未登録の場合、discoverSpotsBatch は何もせず `{"status": "skipped"}` を返して正常終了する
> （エラーにはならないが、新スポットも増えない）。

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

> **補足:** スポット写真・投稿写真のアップロード先S3バケット（`fishing-ai-app-uploads-<アカウントID>`）は
> ここでは扱わない。こちらは `template.yaml` の `UploadsBucket` としてSAM/CloudFormationで自動作成されるため、
> 手動作成は不要（下記「3. S3 バケット作成」で扱うのはフロント静的ホスティング用の別バケット）。

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
     数秒おきにポーリングして待つ。**2026-07-24時点**でこのバッチは
     (a) Google Places APIによる新規スポット探索（全国向け、位置指定なし）→
     (b) 全スポットの天気・潮汐取得＋Gemini呼び出しによるスコア計算、の順に実行するため、
     合計60〜90秒程度かかる（従来のスコア計算のみの30秒前後から伸びている）。
     90秒待っても完了を検知できない場合は「バックグラウンドで実行中の可能性があります」
     という中立的な表示になる（エラーではなく、裏側では継続している可能性がある状態）

3. **結果を確認**
   - 分析完了後、釣りスポットのスコアと AI コメントが表示されることを確認
   - TOP3 ランキングと地図ピンが正しく表示されれば成功
   - スコアは実際の天気（Open-Meteo）・潮汐（Open-Meteo Marine、海面水位の変化率）に基づいて算出される

4. **現在地からのおすすめ（サブ機能）**
   - TOPページ右上の現在地アイコンをクリックし、ブラウザの位置情報許可ダイアログを承認する
   - メインのTOP3（基準地点からのスコア）とは別に、現在地からの実距離で再ランキングした上位3件が表示される
   - この再ランキングはクライアント側だけで計算しておりDBは書き換わらない

5. **新スポット自動発見（2026-07-24更新）**
   - 全国向けの探索は「AI分析を実行」に統合済み。押すたびに discover_spots.run_discovery() が
     まず実行され、見つかった新規スポットもその回のスコア計算対象に含まれる
   - 「現在地から新スポットを探す」ボタンは現在地に絞った探索専用。押すと位置情報の許可を求め、
     取得できたら現在地周辺15km圏内で discoverSpotsBatch を非同期起動する（スコア計算は行わない）
   - Google Places API キー未登録の場合はどちらも何も追加されずに正常終了する（上記1参照）
   - 数分後にスポット一覧ページを更新すると、新しいスポットが増えていることを確認できる

6. **釣果投稿**
   - ナビの「釣果」タブから投稿一覧・投稿フォームを確認する
   - 写真を選択して投稿すると、S3への直接アップロード（署名付きURL）→投稿作成の順に実行される

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| AI ボタンを押しても何も起きない | `VITE_API_BASE_URL` が未設定、または古いAPIエンドポイントを指している | GitHub Secrets とフロントの `.env` を確認して再デプロイ |
| AIコメントが毎回同じ定型文になる | Gemini API キーが読めていない、またはモデル名が廃止されている | SSMパラメータ名の先頭スラッシュ有無を確認（上記1参照）。CloudWatch Logs の `generateSpotScoreBatch` で `SSM get_parameter error` や `Gemini API error` が出ていないか確認 |
| 地図が表示されない | `VITE_GOOGLE_MAPS_KEY` が無効、または未設定 | Google Cloud Console で Maps JavaScript API を有効化。ローカルビルド（Cloudflare Pages等）には `frontend/.env` にも直接設定が必要（GitHub Secretsとは別管理） |
| スポットが表示されない | 初期データ未投入 | 手順4の `seed_data.py` を再実行 |
| Lambda がエラー | Gemini API キーが未設定・無効 | 手順1の SSM パラメータを確認 |
| 「新スポットを探す」を押しても増えない | Google Places API キー未登録、または請求先アカウント未紐付け | 手順1の `fishing-ai/google-places-api-key` を確認。CloudWatch Logs の `discoverSpotsBatch` で `Places API` のエラーが出ていないか確認 |
| 写真アップロードが失敗する | S3バケットのCORS設定漏れ、または署名付きURLの有効期限切れ（5分） | `UploadsBucket` の CORS 設定を確認。アップロードは選択直後に行うため通常は期限切れにならない |
| 投稿が反映されない | `POST /posts` の失敗、または一覧の再取得漏れ | ブラウザの開発者ツールでAPIレスポンスを確認。ページ再読み込みで反映されるか確認 |

---

## 7. デプロイ先（2026-07-23 時点）

フロントエンドは2系統に並行デプロイしている。バックエンド（API Gateway/Lambda/DynamoDB）はAWS側1本のみで共通。

| デプロイ先 | URL | デプロイ方法 |
|---|---|---|
| AWS（CloudFront） | https://d2ny5ej5kn6jzs.cloudfront.net/ | `main` ブランチへの push で GitHub Actions が自動デプロイ |
| Cloudflare Pages | https://ryu-chan-fish.ryuchan-aws.workers.dev/ | `frontend` で `npm run build` の後 `npx wrangler pages deploy dist --project-name ryu-chan-fish`（手動デプロイ、CI化はしていない） |

> 独自ドメイン（有料）は未取得。無料で使える見た目のURLとして Cloudflare Pages の `*.workers.dev` サブドメインを利用している。