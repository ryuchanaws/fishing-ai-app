/**
 * @fileoverview スポット詳細モーダルコンポーネント。
 *
 * おすすめカードをタップしたときに表示されるモーダル。
 * AI コメント・魚種・各種スコア・距離・費用を表示し、
 * Google Maps ナビとお気に入りトグルボタンを提供する。
 */

import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { X, Navigation2, Heart, Fish, Cloud, Waves, MapPin, Banknote, Camera, MessageSquare } from "lucide-react";
import type { Recommendation } from "../types";
import { getScoreColor, getScoreLabel } from "../utils/score";
import { getPresignedUploadUrl, uploadImageToS3, updateSpotImage } from "../api/client";
import { ImagePreviewPopover } from "./ImagePreviewPopover";

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

  /** アップロード済みのスポット写真URL（アップロード直後の即時反映用にローカルで保持） */
  const [imageUrl, setImageUrl] = useState(rec.spot?.imageUrl);
  /** アップロード中フラグ */
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /**
   * Google Maps のルート案内を新しいタブで開く。
   */
  const openNav = () => {
    const url = `https://www.google.com/maps/dir/?api=1&destination=${rec.spot?.lat ?? 0},${rec.spot?.lng ?? 0}`;
    window.open(url, "_blank");
  };

  /**
   * 選択された画像ファイルをS3へアップロードし、スポットの写真として設定する。
   * 署名付きURL発行 → S3へ直接PUT → Spotsテーブルのimageurlを更新、の順に行う。
   *
   * @param {React.ChangeEvent<HTMLInputElement>} e - ファイル選択イベント
   */
  const handlePhotoSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const { uploadUrl, publicUrl } = await getPresignedUploadUrl(file.type);
      await uploadImageToS3(uploadUrl, file);
      await updateSpotImage(rec.spotId, publicUrl);
      setImageUrl(publicUrl);
    } catch {
      // アップロード失敗時は静かに諦める（UI上の写真は変更しない）
    } finally {
      setUploading(false);
      e.target.value = "";
    }
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
          {/* スポット名: hover(PC)/長押し(スマホ)でスポット写真をプレビュー表示 */}
          <ImagePreviewPopover imageUrl={imageUrl}>
            <h2 className="modal-spot-name">{rec.spot?.name ?? rec.spotId}</h2>
          </ImagePreviewPopover>
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
              <ImagePreviewPopover key={f} fishName={f}>
                <span className="fish-tag large">
                  <Fish size={14} />
                  {f}
                </span>
              </ImagePreviewPopover>
            ))}
          </div>
        </div>

        {/* 詳細スタッツグリッド: 天気・潮汐・距離・費用 */}
        <div className="modal-stats">
          <div className="stat-item">
            <Cloud size={18} />
            <span className="stat-label">天気スコア</span>
            <span className="stat-value">{Math.round(rec.weatherScore ?? 0)}</span>
          </div>
          <div className="stat-item">
            <Waves size={18} />
            <span className="stat-label">潮汐スコア</span>
            <span className="stat-value">{Math.round(rec.tideScore ?? 0)}</span>
          </div>
          <div className="stat-item">
            <MapPin size={18} />
            <span className="stat-label">距離</span>
            <span className="stat-value">{rec.distance != null ? rec.distance.toFixed(1) : "0.0"}km</span>
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

          {/* スポット写真の設定: 選択したファイルをS3へアップロードしてスポットに紐付ける */}
          <button className="btn-nav" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
            <Camera size={16} />
            {uploading ? "アップロード中..." : imageUrl ? "写真を変更" : "スポット写真を設定"}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            style={{ display: "none" }}
            onChange={handlePhotoSelect}
          />

          {/* このスポットの投稿一覧へ */}
          <Link to={`/posts?spotId=${rec.spotId}`} className="btn-nav">
            <MessageSquare size={16} />
            このスポットの投稿を見る
          </Link>
        </div>
      </div>
    </div>
  );
};