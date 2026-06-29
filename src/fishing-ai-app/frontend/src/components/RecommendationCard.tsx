/**
 * @fileoverview おすすめスポットカードコンポーネント。
 *
 * TOP3・その他一覧・お気に入り一覧で共通利用するカード UI。
 * スコア・魚種・AI コメント・天気/潮汐・距離・費用を表示し、
 * ナビボタンとお気に入りトグルボタンを提供する。
 */

import { Heart, Navigation2, Fish } from "lucide-react";
import type { Recommendation } from "../types";
import { getScoreColor, getScoreLabel, formatScore, getWeatherIcon, getTideIcon } from "../utils/score";

/**
 * RecommendationCard コンポーネントの Props。
 */
interface RecommendationCardProps {
  /** 表示するおすすめデータ */
  recommendation: Recommendation;
  /** ランク番号（TOP3 表示時のみ渡す。省略時はバッジ非表示） */
  rank?: number;
  /** 現在のお気に入り登録状態 */
  isFavorite: boolean;
  /** お気に入りトグル関数 */
  onToggleFavorite: (spotId: string) => void;
  /** カードクリック時に呼び出す関数（詳細モーダルを開く） */
  onClick: (rec: Recommendation) => void;
}

/**
 * おすすめスポットカードコンポーネント。
 *
 * - rank が渡されたときのみランクバッジ（#1〜#3）を表示する
 * - スコアに応じた色でスコアサークルのボーダーを表示する
 * - ナビボタンクリックで Google Maps のルート案内を新しいタブで開く
 * - お気に入りボタンは登録状態に応じてハートの塗りつぶしを切り替える
 * - カード全体がクリッカブルで onClick で詳細モーダルを開く
 *
 * @param {RecommendationCardProps} props
 * @returns {JSX.Element} おすすめスポットカード
 */
export const RecommendationCard = ({
  recommendation: rec,
  rank,
  isFavorite,
  onToggleFavorite,
  onClick,
}: RecommendationCardProps) => {
  /** スコアに応じたアクセントカラー */
  const scoreColor = getScoreColor(rec.score);

  /**
   * Google Maps のルート案内を新しいタブで開く。
   * カード全体のクリックイベントが伝播しないよう stopPropagation する。
   *
   * @param {React.MouseEvent} e - マウスイベント
   */
  const openNav = (e: React.MouseEvent) => {
    e.stopPropagation();
    const url = `https://www.google.com/maps/dir/?api=1&destination=${rec.spot?.lat ?? 0},${rec.spot?.lng ?? 0}`;
    window.open(url, "_blank");
  };

  return (
    <div className="rec-card" onClick={() => onClick(rec)} role="button" tabIndex={0}>
      {/* ランクバッジ: rank が渡されたときのみ表示（1位: 金・2位: 銀・3位: 銅） */}
      {rank && (
        <div className="rank-badge" style={{ background: rank === 1 ? "#f5a623" : rank === 2 ? "#aaa" : "#cd7f32" }}>
          #{rank}
        </div>
      )}

      {/* カードヘッダー: スポット名・魚種タグ・スコアサークル */}
      <div className="card-header">
        <div>
          <h3 className="spot-name">{rec.spot?.name ?? rec.spotId}</h3>
          {/* 魚種タグ一覧 */}
          <div className="fish-tags">
            {rec.fishTypes.map((f) => (
              <span key={f} className="fish-tag">
                <Fish size={11} />
                {f}
              </span>
            ))}
          </div>
        </div>

        {/* スコアサークル: スコアに応じた色のボーダーで囲む */}
        <div className="score-circle" style={{ borderColor: scoreColor, color: scoreColor }}>
          <span className="score-num">{formatScore(rec.score)}</span>
          <span className="score-label">{getScoreLabel(rec.score)}</span>
        </div>
      </div>

      {/* AI コメント: 2行で切り捨て表示 */}
      <p className="reason-text">{rec.reason}</p>

      {/* メタ情報: 天気・潮汐・距離・費用 */}
      <div className="card-meta">
        <span>{getWeatherIcon(rec.weatherScore)} 天気 {Math.round(rec.weatherScore)}</span>
        <span>{getTideIcon(rec.tideScore)} 潮汐 {Math.round(rec.tideScore)}</span>
        <span>📍 {(rec.distance ?? 0).toFixed(1)}km</span>
        <span>💰 {rec.cost === 0 ? "無料" : `¥${(rec.cost ?? 0).toLocaleString()}`}</span>
      </div>

      {/* アクションボタン: クリックイベントがカード全体に伝播しないよう stopPropagation */}
      <div className="card-actions" onClick={(e) => e.stopPropagation()}>
        {/* Google Maps ナビゲーションボタン */}
        <button className="nav-btn" onClick={openNav}>
          <Navigation2 size={15} />
          ナビ開始
        </button>

        {/* お気に入りトグルボタン: 登録済みかどうかでハートの塗りつぶしを切り替え */}
        <button
          className={`fav-btn ${isFavorite ? "active" : ""}`}
          onClick={() => onToggleFavorite(rec.spotId)}
          aria-label={isFavorite ? "お気に入りから削除" : "お気に入りに追加"}
        >
          <Heart size={15} fill={isFavorite ? "currentColor" : "none"} />
          {isFavorite ? "保存済み" : "保存"}
        </button>
      </div>
    </div>
  );
};