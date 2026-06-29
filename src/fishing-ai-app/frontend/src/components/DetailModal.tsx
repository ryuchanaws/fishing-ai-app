/**
 * @fileoverview スポット詳細モーダルコンポーネント。
 *
 * おすすめカードをタップしたときに表示されるモーダル。
 * AI コメント・魚種・各種スコア・距離・費用を表示し、
 * Google Maps ナビとお気に入りトグルボタンを提供する。
 */

import { X, Navigation2, Heart, Fish, Cloud, Waves, MapPin, Banknote } from "lucide-react";
import type { Recommendation } from "../types";
import { getScoreColor, getScoreLabel } from "../utils/score";

/**
 * DetailModal コンポーネントの Props。
 */
interface DetailModalProps {
  /** 詳細表示するおすすめデータ */
  recommendation: Recommendation;
  /** 現在のお気に入り登録状態 */
  isFavorite: boolean;
  /** モーダルを閉じる関数 */
  onClose: () => void;
  /** お気に入りトグル関数 */
  onToggleFavorite: (spotId: string) => void;
}

/**
 * スポット詳細モーダルコンポーネント。
 *
 * - バックドロップ（背景）クリックでモーダルを閉じる
 * - スコアに応じた色でヒーローセクションのボーダーを表示する
 * - お気に入りボタンは登録済みかどうかで表示を切り替える
 *
 * @param {DetailModalProps} props
 * @returns {JSX.Element} スポット詳細モーダル
 */
export const DetailModal = ({ recommendation: rec, isFavorite, onClose, onToggleFavorite }: DetailModalProps) => {
  /** スコアに応じたアクセントカラー */
  const scoreColor = getScoreColor(rec.score);

  /**
   * Google Maps のルート案内を新しいタブで開く。
   */
  const openNav = () => {
    const url = `https://www.google.com/maps/dir/?api=1&destination=${rec.spot?.lat ?? 0},${rec.spot?.lng ?? 0}`;
    window.open(url, "_blank");
  };

  return (
    /* バックドロップ: クリックでモーダルを閉じる */
    <div className="modal-backdrop" onClick={onClose}>
      {/* モーダル本体: クリックイベントの伝播を止めてバックドロップと区別する */}
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        {/* 閉じるボタン */}
        <button className="modal-close" onClick={onClose} aria-label="閉じる">
          <X size={20} />
        </button>

        {/* ヒーローセクション: スポット名とスコアを大きく表示 */}
        <div className="modal-hero" style={{ borderBottom: `3px solid ${scoreColor}` }}>
          <h2 className="modal-spot-name">{rec.spot?.name ?? rec.spotId}</h2>
          <div className="modal-score" style={{ color: scoreColor }}>
            <span className="modal-score-num">{Math.round(rec.score)}</span>
            <span className="modal-score-label">/ 100 — {getScoreLabel(rec.score)}</span>
          </div>
        </div>

        {/* AI コメントセクション: Claude API が生成した推薦理由 */}
        <div className="modal-section">
          <h3 className="modal-section-title">🤖 AI分析コメント</h3>
          <p className="modal-reason">{rec.reason}</p>
        </div>

        {/* 魚種セクション */}
        <div className="modal-section">
          <h3 className="modal-section-title">釣れる魚</h3>
          <div className="modal-fish-tags">
            {rec.fishTypes.map((f) => (
              <span key={f} className="fish-tag large">
                <Fish size={14} />
                {f}
              </span>
            ))}
          </div>
        </div>

        {/* 詳細スタッツグリッド: 天気・潮汐・距離・費用 */}
        <div className="modal-stats">
          <div className="stat-item">
            <Cloud size={18} />
            <span className="stat-label">天気スコア</span>
            <span className="stat-value">{Math.round(rec.weatherScore)}</span>
          </div>
          <div className="stat-item">
            <Waves size={18} />
            <span className="stat-label">潮汐スコア</span>
            <span className="stat-value">{Math.round(rec.tideScore)}</span>
          </div>
          <div className="stat-item">
            <MapPin size={18} />
            <span className="stat-label">距離</span>
            <span className="stat-value">{rec.distance.toFixed(1)}km</span>
          </div>
          <div className="stat-item">
            <Banknote size={18} />
            <span className="stat-label">費用</span>
            <span className="stat-value">{!rec.cost || rec.cost === 0 ? "無料" : `¥${rec.cost.toLocaleString()}`}</span>
          </div>
        </div>

        {/* アクションボタン: ナビ・お気に入り */}
        <div className="modal-actions">
          {/* Google Maps ナビゲーションボタン */}
          <button className="btn-nav" onClick={openNav}>
            <Navigation2 size={16} />
            Google Mapsでナビ
          </button>

          {/* お気に入りトグルボタン: 登録済みかどうかで表示を切り替え */}
          <button
            className={`btn-fav ${isFavorite ? "active" : ""}`}
            onClick={() => onToggleFavorite(rec.spotId)}
          >
            <Heart size={16} fill={isFavorite ? "currentColor" : "none"} />
            {isFavorite ? "保存済み" : "お気に入りに追加"}
          </button>
        </div>
      </div>
    </div>
  );
};