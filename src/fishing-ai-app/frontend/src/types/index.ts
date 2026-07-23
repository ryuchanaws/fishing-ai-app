/**
 * @fileoverview アプリ全体で使用する型定義。
 *
 * DynamoDB のテーブル構造・API レスポンス・UI の状態管理に使用する
 * インターフェースをまとめて定義する。
 */

/**
 * 釣りスポットのマスタデータ。
 * DynamoDB の fishing-spots テーブルのレコードに対応する。
 */
export interface Spot {
  /** スポットの一意識別子（PK） */
  spotId: string;
  /** スポット名（例: "三浦半島・城ヶ島"） */
  name: string;
  /** 緯度（Google Maps マーカー表示に使用） */
  lat: number;
  /** 経度（Google Maps マーカー表示に使用） */
  lng: number;
  /** 都道府県名（省略可） */
  prefecture?: string;
  /** スポットの説明文（省略可） */
  description?: string;
}

/**
 * AI バッチが生成したスポットのおすすめ情報。
 * DynamoDB の fishing-recommendations テーブルのレコードに対応する。
 * score はルールベースで計算し、reason のみ Claude API で生成する。
 */
export interface Recommendation {
  /** スポットの一意識別子（PK・Spots テーブルと結合キー） */
  spotId: string;
  /** 総合スコア（0〜100）。ルールベースで計算 */
  score: number;
  /** 釣れる魚種リスト（例: ["アジ", "サバ"]） */
  fishTypes: string[];
  /** AI が生成した推薦理由（自然言語・日本語） */
  reason: string;
  /** 基準地点からの距離（km） */
  distance: number;
  /** 入場・駐車場等の費用（円。0 = 無料） */
  cost: number;
  /** 天気スコア（0〜100） */
  weatherScore: number;
  /** 潮汐スコア（0〜100） */
  tideScore: number;
  /** バッチ処理の最終実行日時（ISO 8601 形式・省略可） */
  updatedAt?: string;
  /** 結合済みのスポット情報（API レスポンス時に付与・省略可） */
  spot?: Spot;
}

/**
 * ユーザーのお気に入りスポット。
 * DynamoDB の fishing-favorites テーブルのレコードに対応する。
 * userId（PK）+ spotId（SK）の複合キーで一意性を担保する。
 */
export interface Favorite {
  /** ユーザーID（PK） */
  userId: string;
  /** スポットID（SK・Spots テーブルと結合キー） */
  spotId: string;
  /** ユーザーが登録したメモ（省略可） */
  memo?: string;
  /** 結合済みのスポット情報（API レスポンス時に付与・省略可） */
  spot?: Spot;
  /** 結合済みのおすすめ情報（API レスポンス時に付与・省略可） */
  recommendation?: Recommendation;
}

/**
 * 釣果投稿。
 * DynamoDB の fishing-posts テーブルのレコードに対応する。
 * 将来の釣果共有機能拡張用として定義済み。
 */
export interface Post {
  /** 投稿の一意識別子（PK） */
  postId: string;
  /** 投稿対象のスポットID（Spots テーブルと結合キー） */
  spotId: string;
  /** 投稿者のユーザーID */
  userId: string;
  /** 投稿本文 */
  content: string;
  /** 添付画像の URL（省略可） */
  imageUrl?: string;
  /** 釣れた魚種リスト（省略可・例: ["アジ", "サバ"]） */
  fishCaught?: string[];
  /** 投稿日時（ISO 8601 形式） */
  createdAt: string;
  /** 結合済みのスポット情報（API レスポンス時に付与・省略可） */
  spot?: Spot;
}

/**
 * AI バッチ処理の実行状態。
 * フロントエンドの「AI分析を実行」ボタンの UI 制御に使用する。
 */
export interface BatchStatus {
  /**
   * バッチの実行状態。
   * - `idle`      : 未実行（初期状態）
   * - `running`   : 実行中（ボタン無効化・スピナー表示）
   * - `completed` : 完了（成功メッセージ表示）
   * - `failed`    : 失敗（エラーメッセージ表示）
   * - `timeout`   : バッチは非同期起動されたがポーリング時間内に完了を確認できなかった
   *                 （失敗ではなく、裏側では実行中/完了している可能性がある状態）
   */
  status: "running" | "completed" | "failed" | "timeout" | "idle";
  /** バッチ開始日時（ISO 8601 形式・省略可） */
  startedAt?: string;
  /** バッチ完了日時（ISO 8601 形式・省略可） */
  completedAt?: string;
  /** エラーメッセージまたは補足メッセージ（省略可） */
  message?: string;
  /** バッチで処理したスポット数（省略可） */
  processedCount?: number;
}