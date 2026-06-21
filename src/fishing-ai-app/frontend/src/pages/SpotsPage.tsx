/**
 * @fileoverview 釣りスポット一覧画面。
 *
 * 全スポットをリスト形式で表示する。
 * 各行にスコアカラーバー・魚種タグ・スコアラベル・ナビリンクを表示し、
 * おすすめデータがないスポットはグレーで表示する。
 */

import { useState, useEffect } from "react";
import { getSpots } from "../api/client";
import { getRecommendations } from "../api/client";
import type { Spot, Recommendation } from "../types";
import { Navigation2, Fish } from "lucide-react";
import { getScoreColor, getScoreLabel } from "../utils/score";

/**
 * スポット一覧ページコンポーネント。
 *
 * - マウント時に spots・recommendations を並列取得してリスト表示する
 * - 各スポット行の左端にスコアに応じた色のバーを表示する
 * - おすすめデータがないスポットはグレーのバーで表示する
 * - ナビアイコンから Google Maps のルート案内を新しいタブで開ける
 *
 * @returns {JSX.Element} スポット一覧画面
 */
export const SpotsPage = () => {
  /** 全釣りスポット一覧 */
  const [spots, setSpots] = useState<Spot[]>([]);

  /** spotId をキーにしたおすすめデータの辞書（スコア・魚種表示に使用） */
  const [recMap, setRecMap] = useState<Record<string, Recommendation>>({});

  /** データ取得中フラグ */
  const [loading, setLoading] = useState(true);

  /**
   * マウント時にスポットとおすすめデータを並列取得する。
   * recommendations は spotId をキーとした辞書に変換して保持する。
   */
  useEffect(() => {
    Promise.all([getSpots(), getRecommendations()]).then(([s, r]) => {
      setSpots(s);
      const m: Record<string, Recommendation> = {};
      r.forEach((rec) => (m[rec.spotId] = rec));
      setRecMap(m);
      setLoading(false);
    });
  }, []);

  /** データ取得中はローディングスピナーを表示 */
  if (loading) return <div className="loading-state"><div className="loader" /><p>読み込み中...</p></div>;

  return (
    <div className="page spots-page">
      <div className="page-header">
        <h1 className="page-title">スポット一覧</h1>
        {/* 取得したスポットの総件数を表示 */}
        <p className="page-sub">全 {spots.length} スポット</p>
      </div>

      <div className="spots-list">
        {spots.map((spot) => {
          const rec = recMap[spot.spotId];
          /** スコアがあればスコアに応じた色、なければグレーを使用 */
          const color = rec ? getScoreColor(rec.score) : "#9ca3af";
          return (
            <div key={spot.spotId} className="spot-row">
              <div className="spot-row-left">
                {/* スコアに応じた色の左端バー */}
                <div className="spot-score-bar" style={{ background: color }} />
                <div>
                  <p className="spot-row-name">{spot.name}</p>
                  {/* おすすめデータがある場合のみ魚種タグを表示 */}
                  {rec && (
                    <div className="spot-row-fish">
                      {rec.fishTypes.map((f) => (
                        <span key={f} className="fish-tag sm">
                          <Fish size={10} />{f}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <div className="spot-row-right">
                {/* おすすめデータがある場合のみスコアとラベルを表示 */}
                {rec && (
                  <span className="spot-row-score" style={{ color }}>
                    {Math.round(rec.score)} <small>{getScoreLabel(rec.score)}</small>
                  </span>
                )}
                {/* Google Maps ナビゲーションリンク（新しいタブで開く） */}
                <a
                  href={`https://www.google.com/maps/dir/?api=1&destination=${spot.lat},${spot.lng}`}
                  target="_blank"
                  rel="noreferrer"
                  className="icon-btn"
                  title="ナビ"
                >
                  <Navigation2 size={16} />
                </a>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};