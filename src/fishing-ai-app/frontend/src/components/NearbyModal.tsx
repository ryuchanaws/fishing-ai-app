/**
 * @fileoverview 「現在地から探す」モーダルコンポーネント。
 *
 * ブラウザの現在地を取得し、取得済みのおすすめデータを
 * 実際の現在地からの距離で再ランキングして表示するサブ機能。
 * メインのTOP3（基準地点からのおすすめ）はそのままに、
 * こちらは現在地基準の別ランキングとして独立して提供する。
 * DBへの書き込みは行わず、クライアント側だけで完結する。
 */

import { useEffect, useMemo } from "react";
import { X, LocateFixed, Loader2 } from "lucide-react";
import type { Recommendation } from "../types";
import { useGeolocation } from "../hooks/useGeolocation";
import { haversineKm } from "../utils/distance";
import { recalcScoreForDistance } from "../utils/score";
import { RecommendationCard } from "./RecommendationCard";

/**
 * NearbyModal コンポーネントの Props。
 */
interface NearbyModalProps {
  /** 取得済みのおすすめ一覧（現在地基準に再計算する元データ） */
  recommendations: Recommendation[];
  /** お気に入り確認関数 */
  isFavorite: (spotId: string) => boolean;
  /** お気に入りトグル関数 */
  onToggleFavorite: (spotId: string) => void;
  /** カードクリック時に呼び出す関数（詳細モーダルを開く） */
  onSelect: (rec: Recommendation) => void;
  /** モーダルを閉じる関数 */
  onClose: () => void;
}

/**
 * 現在地からのおすすめモーダル。
 *
 * - マウント時に自動で位置情報の取得をリクエストする
 * - 取得できた現在地と各スポットの緯度経度からhaversine距離を算出し、
 *   recalcScoreForDistance でスコアを近似再計算して上位3件を表示する
 * - 拒否/エラー時は案内メッセージを表示する
 *
 * @param {NearbyModalProps} props
 * @returns {JSX.Element} 現在地からのおすすめモーダル
 */
export const NearbyModal = ({ recommendations, isFavorite, onToggleFavorite, onSelect, onClose }: NearbyModalProps) => {
  const { position, status, request } = useGeolocation();

  /** モーダルを開いたら自動で現在地取得をリクエストする */
  useEffect(() => {
    request();
  }, [request]);

  /**
   * 現在地からの実距離でスコアを再計算し、上位3件を並べ替える。
   * spot情報（lat/lng）が無いおすすめは対象外とする。
   */
  const nearby = useMemo(() => {
    if (!position) return [];
    return recommendations
      .filter((rec) => rec.spot?.lat != null && rec.spot?.lng != null)
      .map((rec) => {
        const distanceKm = haversineKm(position.lat, position.lng, rec.spot!.lat, rec.spot!.lng);
        return { ...rec, distance: distanceKm, score: recalcScoreForDistance(rec, distanceKm) };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, 3);
  }, [position, recommendations]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="閉じる">
          <X size={20} />
        </button>

        <div className="modal-hero">
          <h2 className="modal-spot-name">
            <LocateFixed size={20} style={{ verticalAlign: "-3px", marginRight: 6 }} />
            現在地から探す
          </h2>
        </div>

        <div className="modal-section">
          {(status === "idle" || status === "loading") && (
            <div className="loading-state">
              <Loader2 size={24} className="spin" />
              <p>現在地を取得しています...</p>
            </div>
          )}

          {status === "denied" && (
            <p className="reason-text">
              位置情報の利用が許可されていません。ブラウザの設定で位置情報を許可してから、もう一度お試しください。
            </p>
          )}

          {status === "error" && (
            <p className="reason-text">
              現在地の取得に失敗しました。電波状況の良い場所でもう一度お試しください。
            </p>
          )}

          {status === "granted" && nearby.length === 0 && (
            <p className="reason-text">近くのスポット情報が見つかりませんでした。</p>
          )}

          {status === "granted" && nearby.length > 0 && (
            <div className="rec-list">
              {nearby.map((rec, i) => (
                <RecommendationCard
                  key={rec.spotId}
                  recommendation={rec}
                  rank={i + 1}
                  isFavorite={isFavorite(rec.spotId)}
                  onToggleFavorite={onToggleFavorite}
                  onClick={onSelect}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
