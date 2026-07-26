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
| `CLOUDFLARE_API_TOKEN`【2026-07-24追加】 | Cloudflare Workers へのデプロイ権限を持つ API トークン | Cloudflareダッシュボード → プロフィール → API Tokens →「Edit Cloudflare Workers」テンプレート |
| `CLOUDFLARE_ACCOUNT_ID`【2026-07-24追加】 | Cloudflare アカウントID | Cloudflareダッシュボード（トークン発行時にも表示される） |
| `VITE_COGNITO_USER_POOL_ID`【2026-07-26追加】 | Cognito User Pool ID | `sam deploy` 後の Outputs（`UserPoolId`） |
| `VITE_COGNITO_CLIENT_ID`【2026-07-26追加】 | Cognito User Pool Client ID | `sam deploy` 後の Outputs（`UserPoolClientId`） |
| `VITE_COGNITO_DOMAIN`【2026-07-26追加】 | Cognito Hosted UI のドメイン | `sam deploy` 後の Outputs（`CognitoHostedUiDomain`）。詳細は下記「9. 認証（Cognito + Google）のセットアップ」参照 |

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

7. **AI相談（チャット、2026-07-25追加）**
   - ナビの「AI相談」タブから、魚種判定・エサの適否などをテキストで質問できる
   - 入力欄の画像アイコンから「アルバムから選択」、カメラアイコンから「その場で撮影」でき、
     どちらも同じ送信フローに統合されている（撮影/選択→プレビュー→送信でGeminiに画像+テキストを渡す）
   - 会話はDynamoDB（fishing-chats）に保存される。「+」ボタンで新しい会話を開始（保存は次の送信時）、
     「履歴」ボタンで過去の会話一覧から再開できる
   - 応答は同期的に返るため他のAI機能と違いポーリングはしない。Gemini呼び出しがLambdaの25秒
     タイムアウトを超えた場合はエラーメッセージが表示される

8. **PWA化（ホーム画面への追加、2026-07-25追加）**
   - スマホのブラウザ（Chrome/Safari等）で本番URLを開き、「ホーム画面に追加」/「アプリをインストール」を実行する
   - アイコン・アプリ名（つり羅針盤）が正しく表示され、起動時にブラウザのアドレスバー無しで開けば成功
   - `vite-plugin-pwa` がビルド時に `manifest.webmanifest` と Service Worker（`sw.js`）を自動生成している

9. **アップロードサイズ上限（2026-07-25追加）**
   - スポット写真・投稿写真・チャット添付画像、いずれも8MBを超えるファイルはアップロードできない
   - 上限はS3の署名付きPOSTフォームの `content-length-range` 条件で強制されており、
     フロント側のチェック（`api/client.ts` の `MAX_UPLOAD_BYTES`）をバイパスしても拒否される
   - 大きすぎるファイルを選んだ場合、送信/アップロード時にエラーメッセージが表示される

10. **表示名（ユーザー名）の設定（2026-07-26追加）**
    - ログイン後、表示名が未設定の場合はモーダルが自動で開く（「閉じる」で後回しにもできる）
    - ナビ右上の人物アイコンからいつでも表示名を編集できる
    - 設定した表示名は釣果投稿の投稿者名として表示される

11. **釣具店を探す（2026-07-26追加）**
    - おすすめ・新スポット探索からは釣具店を除外している（Google Placesの`types`に`store`を含む候補を除外）
    - 代わりにナビ「釣具店」または TOP ページの「釣具店を探す」ボタンから専用ページへ行ける
    - 「現在地から探す」ボタン、または地名・県名でのキーワード検索ができる（スコアは付かない）

12. **AI相談での実データ検索（2026-07-26追加）**
    - AI相談で「〇〇県のおすすめの釣り場は？」「近くの釣り場を教えて」等と聞くと、
      実際に登録されているSpots/Recommendationsデータに基づいて回答する
      （存在しないデータをAIが作り出さないよう、プロンプトに実データのみを渡している）
    - 入力欄の現在地アイコンをONにすると、実際の距離を計算して「近い順」の案内ができるようになる（任意）

---

## 7. デプロイ先（2026-07-24 時点）

フロントエンドは2系統に並行デプロイしている。バックエンド（API Gateway/Lambda/DynamoDB）はAWS側1本のみで共通。

| デプロイ先 | URL | デプロイ方法 |
|---|---|---|
| AWS（CloudFront） | https://d2ny5ej5kn6jzs.cloudfront.net/ | `main` ブランチへの push で GitHub Actions が自動デプロイ |
| Cloudflare Workers | https://ryu-chan-fish.ryuchan-aws.workers.dev/ | **2026-07-24〜自動化**: `main` ブランチへの push で GitHub Actions（`deploy-frontend` ジョブ内の `Deploy to Cloudflare Workers` ステップ）が同じビルド成果物を `npx wrangler deploy` する |

> 独自ドメイン（有料）は未取得。無料で使える見た目のURLとして Cloudflare Workers の `*.workers.dev` サブドメインを利用している。
>
> Cloudflare側の自動デプロイには GitHub Secrets `CLOUDFLARE_API_TOKEN`（Cloudflareダッシュボード → プロフィール → API Tokens →
> 「Edit Cloudflare Workers」テンプレートで発行）と `CLOUDFLARE_ACCOUNT_ID` の登録が必要。

---

## 8. テスト（2026-07-25追加）

`main` へのPull Request作成/更新のたびに `.github/workflows/test.yml` が自動実行される
（デプロイ用の `deploy.yml` とは別ワークフロー。テストのみ行いAWS/Cloudflareへは一切デプロイしない）。

### バックエンド（pytest）

実AWSには接続せず、`moto` でDynamoDBをモックする。

```bash
cd src/fishing-ai-app/backend
pip install -r requirements-dev.txt -r lambda/api/requirements.txt -r lambda/batch/requirements.txt
pytest tests -v
```

> `backend/tests/` はSAMの各Lambda（CodeUri）ディレクトリの外に置いている
> （中に置くとテストコードがLambdaのデプロイパッケージに巻き込まれてしまうため）。
> `conftest.py` が `lambda/api`・`lambda/batch` を import パスに追加している。

### フロントエンド ユニットテスト（Vitest）

```bash
cd src/fishing-ai-app/frontend
npm run test
```

### フロントエンド E2E + VRT（Playwright）

実AWSには接続せず、`e2e/fixtures.ts` の `mockApi()` でAPIレスポンスをモックする
（本番データを汚さない・API利用料を発生させないため）。

```bash
cd src/fishing-ai-app/frontend
npm run build
npx playwright install --with-deps chromium   # 初回のみ
npx playwright test
```

> **VRT（Visual Regression Testing）のベースライン画像について**:
> `e2e/visual.spec.ts-snapshots/` に保存するスクリーンショットはOS・フォントレンダリングに
> 依存するため、ローカル（Windows）で `npx playwright test --update-snapshots` して生成した
> ものは、CI（ubuntu-latest）とファイル名ごと一致しない（Playwrightがスナップショット名に
> OS名を含めるため）。そのため、ベースラインは **CI上で生成** する必要がある。
> 初回はベースラインが無い状態で1回失敗するのが正常な動作。GitHub Actionsの実行結果から
> `playwright-report` アーティファクト（失敗時のみアップロードされる）内の実際のスクリーン
> ショットを取得し、`e2e/visual.spec.ts-snapshots/` に配置してコミットすることで、以降の
> CI実行で差分比較が機能するようになる。

### コードレビューについて
GitHubのPR画面上でのレビュー（コメント・Approve/Request changes）は追加設定なしで利用できる。
AIによる自動レビュー（Claude API等）は今回は見送った（PRごとに課金が発生するため）。
マージをテスト成功まで強制ブロックしたい場合は、リポジトリの Branch protection rule 設定
（GitHub管理者権限が必要）を別途行うこと。

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
| AI相談が「回答の生成に失敗しました」を返す | Gemini API呼び出しがエラー、または `PostChatFunction` の25秒Timeoutを超過 | CloudWatch Logs の `postChatHandler` で `Gemini chat error` を確認。画像添付時は特に時間がかかりやすい |
| AI相談でカメラが起動しない | ブラウザ/OSがcapture属性に対応していない、またはHTTPS配信でない | 本番URL（CloudFront/Cloudflare、どちらもHTTPS）でアクセスしているか確認。非対応環境では自動的に通常のファイル選択にフォールバックする |
| 「ホーム画面に追加」が出てこない | HTTPS配信でない、またはmanifest/Service Workerが読み込めていない | 本番URLでアクセスしているか確認。ブラウザの開発者ツール→Application タブで `manifest.webmanifest` と `sw.js` が正しく読めているか確認 |
| 画像アップロードで「画像サイズが大きすぎます」と出る | ファイルが8MB（`MAX_UPLOAD_BYTES`）を超えている | 写真を圧縮するか小さいサイズで撮り直す。上限値自体を変える場合は `handlers.py` の `MAX_UPLOAD_BYTES` と `api/client.ts` の `MAX_UPLOAD_BYTES` を両方変更すること |
| `pytest` が実AWSにアクセスしようとする（`UnrecognizedClientException`等） | `moto`のモックが有効化される前に対象モジュール（handlers.py等）がimportされ、モジュール内のboto3クライアントがモック非対応のまま生成された | `test_handlers_moto.py` の `dynamodb_tables` フィクスチャのように、`mock_aws()` を開始した後に `importlib.reload()` でモジュールを再読み込みしてからテストすること |
| Playwright の `toHaveScreenshot` が初回から失敗する | VRTのベースライン画像が未生成（想定内の初回動作） | 上記「8. テスト」のVRT節を参照。CI上でベースラインを生成してコミットする |
| ログインボタンを押してもエラーになる／リダイレクトされない | `VITE_COGNITO_USER_POOL_ID`/`VITE_COGNITO_CLIENT_ID`/`VITE_COGNITO_DOMAIN` が未設定、またはビルド後にSecrets設定した場合の再ビルド忘れ | 上記「9.3 デプロイ」参照。3つとも設定してから再ビルド（再push）する |
| Googleログイン後に `redirect_mismatch` エラーになる | Google Cloud ConsoleのOAuthクライアントの承認済みリダイレクトURIが実際のCognitoドメインと不一致 | 上記「9.1」の手順でURIを再確認（`/oauth2/idpresponse` を忘れていないか、末尾スラッシュや大文字小文字の違いがないか） |
| お気に入り・投稿・AI相談を使おうとすると常にログイン画面に飛ばされる | 想定どおりの動作（これらはログイン必須の操作） | ナビ右上の「ログイン」からGoogleアカウントでログインする |
| AI相談が「本日の利用回数の上限に達しました」を返す | Geminiコスト管理のための1日あたりレート制限（`DAILY_CHAT_LIMIT`）に達した | 想定どおりの動作。翌日には自動でリセットされる（`UsageTable`のTTLで自動削除）。上限値を変える場合は `handlers.py` の `DAILY_CHAT_LIMIT` を編集して再デプロイ |

---

## 9. 認証（Cognito + Google）のセットアップ（2026-07-26追加）

友人にアプリを共有したことで、`userId` 固定（全員のお気に入り・AI相談履歴が混ざる、
投稿削除に所有者チェックが無い）が実害になったため、Cognito + Google認証を追加した。
**閲覧**（おすすめ・地図・スポット一覧・投稿一覧）はログイン不要のまま。**操作**
（お気に入り・投稿作成/削除・AI相談・AI分析実行・新スポット探索）はログイン必須。

`template.yaml` の `UserPoolDomain` に `!Sub "fishing-ai-app-${AWS::AccountId}"` を指定しているため、
Hosted UIのドメインは `https://fishing-ai-app-<AWSアカウントID>.auth.ap-northeast-1.amazoncognito.com`
という決まった形式になる。そのため、以下の手順は**デプロイ前でも**進められる。

> **注意（2026-07-26、短縮ドメインへの変更は一旦revert）:** ログイン画面のURLとして見栄えが
> 良くないという理由で `ryu-chan-fish` という短いプレフィックスへの変更を試みたが、デプロイが
> 失敗した。原因: CloudFormationはDomainプロパティの変更を「新リソースを作成してから旧リソースを
> 削除する」置き換えとして実行しようとするが、Cognitoの実API側は1つのUserPoolに同時に2つの
> ドメインを持てないため、新ドメインの作成が `Invalid request provided` で拒否される
> （CloudFormation側は安全にロールバックし、スタックは元の状態＝アカウントID入りドメインに
> 復旧済み）。短いドメインへの変更には「①ドメインを一旦削除するデプロイ→②新ドメインを追加する
> デプロイ」の2段階が必要で、①〜②の間はログインが機能しなくなる（Google Cloud Console側の
> リダイレクトURI変更ともタイミングを合わせる必要がある）ため、改めてユーザーと調整の上で
> 別途実施する（現状は据え置き）。

### 9.1 Google Cloud Console で OAuth クライアントを作成

1. [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials) を開く
   （Maps/Places APIキーと同じプロジェクトでよい）
2. 「認証情報を作成」→「OAuth クライアント ID」
   - アプリケーションの種類: **ウェブ アプリケーション**
   - 承認済みのリダイレクト URI に以下を追加:
     ```
     https://fishing-ai-app-<AWSアカウントID>.auth.ap-northeast-1.amazoncognito.com/oauth2/idpresponse
     ```
     （`<AWSアカウントID>` は `aws sts get-caller-identity --query Account --output text` で確認できる）
3. 発行された **クライアントID** と **クライアントシークレット** を控える

### 9.2 SSM にクライアントID/シークレットを登録

`template.yaml` の `UserPoolGoogleIdP` が `{{resolve:ssm:...}}` で参照するため、デプロイ前に
登録しておく必要がある（未登録のままデプロイすると `UserPoolGoogleIdP` の作成に失敗する）。

```bash
aws ssm put-parameter \
  --name /fishing-ai/google-oauth-client-id \
  --value "xxxxxxxx.apps.googleusercontent.com" \
  --type String

aws ssm put-parameter \
  --name /fishing-ai/google-oauth-client-secret \
  --value "GOCSPX-xxxxxxxx" \
  --type String
```

> **注意（2026-07-26訂正）:** client_secretは当初SecureStringで登録する設計だったが、実デプロイで
> `SSM Secure reference is not supported in: [AWS::Cognito::UserPoolIdentityProvider/Properties/ProviderDetails/client_secret]`
> というエラーになった。CloudFormationの動的参照（`{{resolve:ssm-secure:...}}`）でSecureStringが
> 使えるリソース/プロパティは限られており、CognitoのIdentityProvider client_secretは対象外。
> そのため他のシークレット（Gemini/Places APIキー）とは異なり、client_secretのみ通常の
> String（非暗号化）パラメータとして登録する。読み取りはCloudFormationのスタック実行時のみで
> IAM権限も絞っているため、実運用上のリスクは限定的と判断している。

### 9.3 デプロイ

通常どおり `main` へ push すれば `sam deploy` が Cognito一式・API Gatewayの認証設定・
`UsageTable`・`CostBudget` をまとめて作成する。デプロイ完了後、CloudFormationスタックの
Outputsから `UserPoolId` / `UserPoolClientId` / `CognitoHostedUiDomain` を確認し、
GitHub Secretsの `VITE_COGNITO_USER_POOL_ID` / `VITE_COGNITO_CLIENT_ID` / `VITE_COGNITO_DOMAIN`
に設定してから、もう一度 push（またはフロントエンドジョブの re-run）してフロントエンドを
再ビルドすること（ビルド時に埋め込まれる値のため、Secrets設定後の再ビルドが必要）。

```bash
aws cloudformation describe-stacks \
  --stack-name fishing-ai-app \
  --query "Stacks[0].Outputs"
```

ローカル開発（`npm run dev`）の場合は `frontend/.env` に同じ3つの値を設定する
（`.env.example` 参照）。

### 9.4 Geminiコスト管理（1日あたりのAI相談回数上限）

認証で実ユーザーIDが取れるようになったことを利用し、AI相談（`POST /chat`）に
1ユーザー1日あたり30件（`handlers.py` の `DAILY_CHAT_LIMIT`）の上限を設けている。
超過時はGeminiを呼ばずに429エラーを返す（フロントには「本日の利用回数の上限に達しました」
と表示される）。カウンタは `UsageTable`（DynamoDB）にTTL付きで記録され、翌々日には自動で消える。

---

## 10. 利用料アラート（2026-07-26追加）

### AWS（自動化済み）
`template.yaml` の `CostBudget` が月額$10のAWS Budgetsアラートを作成する
（80%/100%到達時に rfunao0955@gmail.com へメール通知）。追加の手動設定は不要。
金額を変更したい場合は `CostBudget.Properties.Budget.BudgetLimit.Amount` を編集して再デプロイする。

### Google Cloud（Gemini/Places、手動設定が必要）
Gemini・Places・MapsのAPI課金はAWSの外（Google Cloud）で発生するため、AWS Budgetsでは検知できない。
以下の手順で別途設定すること（自動化不可・GCPコンソールでの手動操作のみ）。

1. [Google Cloud Console → お支払い → 予算とアラート](https://console.cloud.google.com/billing/budgets) を開く
2. 「予算を作成」→ 対象プロジェクト（Gemini/Places/Maps APIキーを発行したプロジェクト）を選択
3. 予算額を設定（例: 月$10〜20程度。Gemini API側にも別途無料枠がある）
4. しきい値（50%/90%/100%など）でメール通知を設定

> AI相談のレート制限（上記9.4）で最も課金リスクの高いGemini呼び出しは抑制済みだが、
> それでも想定外の利用があった場合に気づけるよう、このアラートは設定しておくことを推奨する。