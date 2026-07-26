"""
generate_score.py

釣りスポットのスコアを計算し、AIによる推薦理由を生成するバッチ処理 Lambda。

EventBridge スケジュール（毎日AM6:00 JST）または
POST /admin/run-ai-batch による手動実行で起動される。

処理フロー:
    0. discover_spots.run_discovery() で新規スポット候補を探索しSpotsテーブルに追加
       （2026-07-24追加。新規に見つかったスポットもこの回のスコア計算対象に含めるため、
        1のSpots取得より前に実行する。失敗してもスコア計算自体は継続する）
    1. Spots テーブルから全スポットを取得
    2. 各スポットの天気・潮汐スコアを取得（外部API or シミュレーション）
    3. ルールベースのスコア式でスコアを計算（毎回・全スポット分実行）
    4. Claude API で推薦理由（reason）を日本語生成。ただし2026-07-26追加の最適化により、
       スコアがほぼ変わっておらず（変化幅がREASON_SCORE_CHANGE_THRESHOLD未満）、かつ
       前回生成からREASON_MAX_AGE_DAYS日以内のスポットは前回の文章を使い回し、
       Claudeは呼ばない（もともとはGemini無料枠の1日20リクエスト制限を1回の実行で
       使い切ってしまう問題への対応だったが、2026-07-26にClaude Haikuへ移行した後も
       無駄なAPI呼び出し・コストを避けるためそのまま維持している。詳細設計.html参照）
    5. Recommendations テーブルに結果を保存（reasonを使い回した場合もスコア・updatedAtは
       毎回更新するため、フロントのポーリング完了判定には影響しない）

Requirements:
    - 環境変数 SPOTS_TABLE / RECOMMENDATIONS_TABLE が設定済みであること
    - Lambda 実行ロールに DynamoDB の読み書き権限があること
    - anthropic パッケージがインストール済みであること（pip install anthropic）
"""

import json
import os
import random
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any

import anthropic

from batch_common import get_table as _get_table, http_get_json as _http_get_json, get_ssm_parameter
from discover_spots import run_discovery

# 天気・海面水位（潮汐）データの取得元。
# Open-Meteo は APIキー登録不要・無料（非商用）で、
# 複数の気象・海洋機関のデータを統合して提供している信頼性の高いサービス。
# https://open-meteo.com/
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

# 環境変数からテーブル名・SSMパラメータ名を取得
SPOTS_TABLE           = os.environ.get("SPOTS_TABLE", "fishing-spots")
RECOMMENDATIONS_TABLE = os.environ.get("RECOMMENDATIONS_TABLE", "fishing-recommendations")
# ANTHROPIC_API_KEY_PARAM は変数名にAPIキーとあるが、実際に入るのは
# SSM Parameter Store 上のパラメータ「名前」（/fishing-ai/anthropic-api-key）であり、
# 実際のキー文字列自体は _get_anthropic_api_key() が実行時にSSMから取得する。
ANTHROPIC_API_KEY_PARAM = os.environ.get(
    "ANTHROPIC_API_KEY_PARAM",
    "/fishing-ai/anthropic-api-key",
)

# Claude Haiku（低コスト・高速なモデル）を使用。詳細設計.html参照
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# CORS ヘッダー（手動実行APIからのレスポンスに付与）
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}

# 2026-07-26追加（コスト削減）: スポット数が増えたことで「AI分析を実行」1回が
# スポット数と同じ回数だけAPIを呼ぶようになる。Claude Haikuは無料枠の回数制限は無いが、
# 呼び出し自体には費用がかかるため、スコアがほとんど変わっていない・最近生成済みの
# スポットは理由文（reason）を使い回し、呼び出しを本当に必要な分だけに絞る。
# スコア自体（天気・潮汐・DynamoDB保存）は毎回計算・更新するため、フロントのポーリング
# （全スポットのupdatedAtが新しくなったかで完了判定）には影響しない。
REASON_SCORE_CHANGE_THRESHOLD = 10.0  # スコアがこれ以上動いたら理由文を再生成する
REASON_MAX_AGE_DAYS = 3  # スコアが動かなくても、これだけ日数が経ったら再生成する


def _get_anthropic_api_key() -> str:
    """SSM Parameter StoreからAnthropic APIキーを取得する。"""
    return get_ssm_parameter(ANTHROPIC_API_KEY_PARAM)

# ─── Score formula ───────────────────────────────────────────────────
def calc_score(fish_prob: float, weather: float, tide: float,
               distance_km: float, cost_yen: float) -> float:
    """ルールベースのスコア式で釣りスポットの総合スコアを計算する。

    スコア式:
        score = fish_prob * 0.4
              + weather   * 0.2
              + tide      * 0.2
              - dist_norm * 0.1
              - cost_norm * 0.1

    distance と cost は 0〜100 に正規化してからマイナス方向に加算する。
    結果は 0.0〜100.0 の範囲にクランプされる。

    Args:
        fish_prob   (float): 魚が釣れる確率スコア（0〜100）
        weather     (float): 天気スコア（0〜100）
        tide        (float): 潮汐スコア（0〜100）
        distance_km (float): 基準地点からの距離（km）
        cost_yen    (float): 費用（円）

    Returns:
        float: 総合スコア（0.0〜100.0）
    """
    dist_norm = min(distance_km / 100.0, 1.0) * 100
    cost_norm = min(cost_yen / 5000.0, 1.0) * 100
    score = (
        fish_prob  * 0.4
        + weather  * 0.2
        + tide     * 0.2
        - dist_norm * 0.1
        - cost_norm * 0.1
    )
    return max(0.0, min(100.0, score))


# ─── Weather/tide via Open-Meteo（無料・APIキー不要） ──────────────────
# _http_get_json は batch_common からの import（モジュール先頭）を使用する

def fetch_weather_score(lat: float, lng: float) -> float:
    """指定座標の現在の天気スコアを Open-Meteo API から取得する。

    天気コード（WMO）・降水量・風速から釣行に適した天気かどうかを
    ヒューリスティックにスコア化する。API呼び出しに失敗した場合は
    シミュレーション値にフォールバックし、バッチ全体は継続させる。

    Args:
        lat (float): 緯度
        lng (float): 経度

    Returns:
        float: 天気スコア（0〜100。値が高いほど釣行に適した天気）
    """
    try:
        data = _http_get_json(OPEN_METEO_FORECAST_URL, {
            "latitude": str(lat),
            "longitude": str(lng),
            "current": "weather_code,precipitation,wind_speed_10m,cloud_cover",
            "timezone": "Asia%2FTokyo",
        })
        current = data["current"]
        weather_code: int = current["weather_code"]
        precipitation: float = current["precipitation"]
        wind_speed: float = current["wind_speed_10m"]  # km/h

        score = 100.0

        # WMO Weather interpretation codes による天気状態の減点
        # https://open-meteo.com/en/docs (WMO Weather interpretation codes)
        if weather_code in (0, 1, 2, 3):          # 快晴〜くもり
            pass
        elif weather_code in (45, 48):             # 霧
            score -= 15
        elif weather_code in (51, 53, 55, 56, 57):  # 霧雨
            score -= 20
        elif weather_code in (61, 63, 65, 66, 67):  # 雨
            score -= 35
        elif weather_code in (71, 73, 75, 77, 85, 86):  # 雪
            score -= 40
        elif weather_code in (80, 81, 82):          # にわか雨
            score -= 30
        elif weather_code in (95, 96, 99):          # 雷雨
            score -= 50
        else:
            score -= 10

        # 降水量（mm）による追加減点（最大30点）
        score -= min(precipitation * 10, 30)

        # 強風による減点（30km/h超で減点開始、最大25点）
        if wind_speed > 30:
            score -= min((wind_speed - 30) * 1.2, 25)

        return max(0.0, min(100.0, score))

    except Exception as e:
        print(f"Open-Meteo weather API error: {e}")
        return random.uniform(50, 95)


def fetch_tide_score(lat: float, lng: float) -> float:
    """指定座標の潮汐（潮の動き）スコアを Open-Meteo Marine API から取得する。

    「潮が動いている時間帯ほど魚の活性が上がる」という釣りの経験則に基づき、
    現在時刻前後の海面水位（sea_level_height_msl）の変化率を計算し、
    変化が大きいほど高スコアとする（満潮・干潮の停滞時は低スコア）。
    API呼び出しに失敗した場合はシミュレーション値にフォールバックする。

    Args:
        lat (float): 緯度
        lng (float): 経度

    Returns:
        float: 潮汐スコア（0〜100。値が高いほど潮がよく動いている）
    """
    try:
        data = _http_get_json(OPEN_METEO_MARINE_URL, {
            "latitude": str(lat),
            "longitude": str(lng),
            "hourly": "sea_level_height_msl",
            "forecast_days": "1",
            "timezone": "Asia%2FTokyo",
        })
        heights: list[float] = data["hourly"]["sea_level_height_msl"]
        times: list[str] = data["hourly"]["time"]

        now_hour = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:00")
        # 現在時刻に最も近い時間帯のインデックスを探す（見つからなければ中央値を使用）
        idx = next((i for i, t in enumerate(times) if t.startswith(now_hour[:13])), len(times) // 2)

        prev_idx = max(0, idx - 1)
        next_idx = min(len(heights) - 1, idx + 1)
        # 前後1時間の水位差（m/h）を潮の動きの速さとみなす
        rate_per_hour = abs(heights[next_idx] - heights[prev_idx]) / max(1, next_idx - prev_idx)

        # 経験的に0.25m/h前後が最も潮が動く時間帯の目安（大潮の最速帯）
        # 停滞時（満潮・干潮付近）でも20点は下限として与える
        score = 20 + min(80.0, (rate_per_hour / 0.25) * 80.0)
        return max(0.0, min(100.0, score))

    except Exception as e:
        print(f"Open-Meteo marine API error: {e}")
        return random.uniform(50, 95)


def estimate_fish_probability(spot_name: str, fish_types: list[str]) -> float:
    """季節ヒューリスティックに基づいて魚が釣れる確率スコアを推定する。

    春（4・5月）と秋（9・10月）はハイシーズンとしてスコアを加算し、
    冬（12・1・2月）はオフシーズンとしてスコアを減算する。
    将来的には ML モデルへの差し替えを想定している。

    Args:
        spot_name  (str): スポット名（将来の拡張用、現在は未使用）
        fish_types (list[str]): 釣れる魚種リスト（将来の拡張用、現在は未使用）

    Returns:
        float: 魚が釣れる確率スコア（20.0〜95.0）
    """
    month = datetime.now(timezone.utc).month
    base = 70
    if month in [4, 5, 9, 10]:
        base += 15
    elif month in [12, 1, 2]:
        base -= 20
    return min(95.0, max(20.0, base + random.uniform(-10, 10)))


# ─── AI reason generation via Claude ─────────────────────────────────
def generate_reason(spot_name: str, fish_types: list[str], score: float,
                    weather_score: float, tide_score: float,
                    distance_km: float) -> str:
    """Claude API を使って釣りスポットの推薦理由を日本語で生成する。

    Anthropic APIキーが未設定の場合はフォールバック文言を返す。
    API エラー時もフォールバック文言を返し、Lambda を継続させる。

    Args:
        spot_name     (str): スポット名
        fish_types    (list[str]): 期待できる魚種リスト
        score         (float): 総合スコア（0〜100）
        weather_score (float): 天気スコア（0〜100）
        tide_score    (float): 潮汐スコア（0〜100）
        distance_km   (float): 基準地点からの距離（km）

    Returns:
        str: 釣りスポットの推薦理由（2〜3文の日本語）
    """
    api_key = _get_anthropic_api_key()
    if not api_key:
        return f"{spot_name}は現在の天気・潮汐条件が良好で、{', '.join(fish_types)}の釣果が期待できます。"

    try:
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""あなたは釣りの専門家です。以下のデータを元に、釣り人向けに「なぜこのスポットが今日おすすめか」を2〜3文の自然な日本語で説明してください。専門用語を使いつつも親しみやすい文体で。

スポット名: {spot_name}
期待できる魚種: {', '.join(fish_types)}
総合スコア: {score:.0f}/100
天気スコア: {weather_score:.0f}/100
潮汐スコア: {tide_score:.0f}/100
距離: {distance_km:.1f}km

説明文のみ出力してください（前置き不要）:"""

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    except Exception as e:
        print(f"Claude API error: {e}")
        return f"{spot_name}は現在のコンディションが良好です。{', '.join(fish_types)}の釣果が見込めます。"


def _should_regenerate_reason(existing: dict[str, Any] | None, new_score: float) -> bool:
    """既存の推薦理由（reason）を使い回さず、Claudeで再生成すべきかを判定する（2026-07-26追加）。

    以下のいずれかに該当する場合は再生成が必要:
        - このスポットの推薦データがまだ無い（初回）
        - 既存データにreasonが無い
        - スコアがREASON_SCORE_CHANGE_THRESHOLD以上動いた
        - 前回の更新からREASON_MAX_AGE_DAYS日以上経過している
          （updatedAtが読めない/無い場合も安全側に倒して再生成する）

    Args:
        existing  (dict | None): RecommendationsTableの既存アイテム（無ければNone）
        new_score (float): 今回計算したスコア

    Returns:
        bool: Claudeで理由文を再生成すべきならTrue
    """
    if not existing or not existing.get("reason"):
        return True

    prev_score = float(existing.get("score", 0))
    if abs(new_score - prev_score) >= REASON_SCORE_CHANGE_THRESHOLD:
        return True

    prev_updated_at = existing.get("updatedAt")
    if not prev_updated_at:
        return True
    try:
        prev_dt = datetime.fromisoformat(prev_updated_at)
    except ValueError:
        return True
    age_days = (datetime.now(timezone.utc) - prev_dt).total_seconds() / 86400
    return age_days >= REASON_MAX_AGE_DAYS


# ─── Main batch handler ───────────────────────────────────────────────
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """全スポットのスコア計算とAI推薦理由生成を実行するメインハンドラー。

    Spots テーブルの全レコードを処理し、スコアと推薦理由を
    Recommendations テーブルに保存する。

    EventBridge スケジュールまたは admin_trigger.py 経由で呼び出される。

    Args:
        event   (dict[str, Any]): Lambda イベントオブジェクト（内容は不使用）
        context (Any): Lambda コンテキストオブジェクト

    Returns:
        dict[str, Any]:
            成功時 200:
                {
                    "status": "completed",
                    "processedCount": int,  # 処理したスポット数
                    "completedAt": str      # 完了日時（ISO 8601）
                }
            スポットなし 200:
                {
                    "message": "No spots found",
                    "processedCount": 0
                }
    """
    print("generateSpotScoreBatch started")

    # 新規スポット候補の探索を先に行い、この回のスコア計算に含める
    # （2026-07-24追加。「AI分析を実行」が新スポット探索も兼ねるようにするため）
    # 失敗してもスコア計算自体は継続させる
    try:
        discovery_result = run_discovery()
        print(f"  Discovery: {discovery_result}")
    except Exception as e:
        print(f"Spot discovery error (continuing with scoring): {e}")

    spots_table = _get_table(SPOTS_TABLE)
    rec_table   = _get_table(RECOMMENDATIONS_TABLE)

    spots: list[dict[str, Any]] = spots_table.scan()["Items"]
    if not spots:
        return {
            "statusCode": 200,
            "headers": CORS,
            "body": json.dumps({"message": "No spots found", "processedCount": 0}),
        }

    # 既存の推薦データをspotIdごとの辞書にしておく（reason使い回し判定用。2026-07-26追加）
    existing_recs: dict[str, dict[str, Any]] = {r["spotId"]: r for r in rec_table.scan()["Items"]}

    # スポットごとに直列処理する。並列化していないのは、Claude API呼び出し
    # （1件あたり数秒）が支配的でDynamoDBの負荷は問題にならないため、
    # 実装の単純さを優先している。2026-07-26のreason使い回し最適化後は、
    # 大半のスポットでClaudeを呼ばなくなるため所要時間は実行のたびに変動する
    # （スコアが大きく動いた/久しぶりのスポットが多いほど時間がかかる）。
    processed = 0
    reason_regenerated = 0
    for spot in spots:
        # DynamoDBの必須項目はspotIdのみのため、他は欠損に備えてデフォルト値を設定
        spot_id:     str       = spot["spotId"]
        spot_name:   str       = spot.get("name", spot_id)
        lat:         float     = float(spot.get("lat", 35.0))
        lng:         float     = float(spot.get("lng", 135.0))
        fish_types:  list[str] = spot.get("fishTypes", ["アジ", "サバ", "イワシ"])
        distance_km: float     = float(spot.get("distanceKm", 20.0))
        cost_yen:    float     = float(spot.get("costYen", 0))

        # 天気・潮汐は外部API、fish_probは季節ヒューリスティックで算出
        weather_score = fetch_weather_score(lat, lng)
        tide_score    = fetch_tide_score(lat, lng)
        fish_prob     = estimate_fish_probability(spot_name, fish_types)

        # スコアはルールベースで決定論的に計算し、reason文だけAIに生成させる
        score = calc_score(fish_prob, weather_score, tide_score, distance_km, cost_yen)

        # reasonはスコアが大きく動いた/一定日数経過した場合のみClaudeで再生成し、
        # そうでなければ前回の文章を使い回す（API呼び出し削減。2026-07-26追加）
        existing = existing_recs.get(spot_id)
        if _should_regenerate_reason(existing, score):
            reason = generate_reason(spot_name, fish_types, score,
                                     weather_score, tide_score, distance_km)
            reason_regenerated += 1
        else:
            reason = existing["reason"]

        # spotId をPKとして put_item するため、同じスポットの前回結果は上書きされる
        # （Recommendationsテーブルは履歴を持たず、スポットごとに最新1件のみ保持する設計）
        # DynamoDBはPythonのfloatを直接受け付けないため、Decimal(str(...))で変換している
        rec_table.put_item(Item={
            "spotId":       spot_id,
            "score":        Decimal(str(round(score, 2))),
            "fishTypes":    fish_types,
            "reason":       reason,
            "distance":     Decimal(str(distance_km)),
            "cost":         Decimal(str(cost_yen)),
            "weatherScore": Decimal(str(round(weather_score, 2))),
            "tideScore":    Decimal(str(round(tide_score, 2))),
            "updatedAt":    datetime.now(timezone.utc).isoformat(),
        })
        processed += 1
        print(f"  Processed: {spot_name} → score={score:.1f}")

    print(f"  Claude reason calls: {reason_regenerated}/{processed} (残りは前回の文章を使い回し)")

    result: dict[str, Any] = {
        "status": "completed",
        "processedCount": processed,
        "reasonRegeneratedCount": reason_regenerated,
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    return {"statusCode": 200, "headers": CORS, "body": json.dumps(result)}