/**
 * @fileoverview 釣りスポット一覧画面。
 *
 * 全スポットをリスト形式で表示する。
 * 各行にスコアカラーバー・魚種タグ・スコアラベル・ナビリンクを表示し、
 * おすすめデータがないスポットはグレーで表示する。
 * スポット数が100件を超え一覧が長くなったため、キーワード検索・魚種絞り込みに対応する
 * （2026-07-26追加。全件クライアント側取得済みのため追加のAPI呼び出しは発生しない）。
 */

import { useState, useEffect, useMemo } from "react";
import { getSpots } from "../api/client";
import { getRecommendations } from "../api/client";
import type { Spot, Recommendation } from "../types";
import { Navigation2, Fish, Search } from "lucide-react";
import { getScoreColor, getScoreLabel } from "../utils/score";
import { ImagePreviewPopover } from "../components/ImagePreviewPopover";

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

  /** 検索キーワード（スポット名・説明文を対象に部分一致で絞り込む） */
  const [searchText, setSearchText] = useState("");
  /** 選択中の魚種フィルタ（いずれか1つでも合致すれば表示。空なら絞り込みなし） */
  const [selectedFish, setSelectedFish] = useState<Set<string>>(new Set());

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

  /** 出現する全魚種を頻度順に並べたフィルタ用チップ一覧 */
  const allFishTypes = useMemo(() => {
    const counts = new Map<string, number>();
    Object.values(recMap).forEach((rec) => {
      rec.fishTypes.forEach((f) => counts.set(f, (counts.get(f) ?? 0) + 1));
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([f]) => f);
  }, [recMap]);

  /** キーワード・魚種フィルタの両方を満たすスポットのみを残す */
  const filteredSpots = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    return spots.filter((spot) => {
      if (q) {
        const haystack = `${spot.name} ${spot.description ?? ""}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      if (selectedFish.size > 0) {
        const fishTypes = recMap[spot.spotId]?.fishTypes ?? [];
        if (!fishTypes.some((f) => selectedFish.has(f))) return false;
      }
      return true;
    });
  }, [spots, recMap, searchText, selectedFish]);

  /**
   * 魚種フィルタチップのON/OFFを切り替える。
   *
   * @param {string} fish - 対象の魚種
   */
  const toggleFish = (fish: string) => {
    setSelectedFish((prev) => {
      const next = new Set(prev);
      if (next.has(fish)) next.delete(fish);
      else next.add(fish);
      return next;
    });
  };

  /** データ取得中はローディングスピナーを表示 */
  if (loading) return <div className="loading-state"><div className="loader" /><p>読み込み中...</p></div>;

  const isFiltered = searchText.trim() !== "" || selectedFish.size > 0;

  return (
    <div className="page spots-page">
      <div className="page-header">
        <h1 className="page-title">スポット一覧</h1>
        {/* 絞り込み中は「全N件中M件」、そうでなければ総件数のみ表示 */}
        <p className="page-sub">
          {isFiltered ? `全${spots.length}スポット中 ${filteredSpots.length}件` : `全 ${spots.length} スポット`}
        </p>
      </div>

      <div className="spots-filter-bar">
        <div className="spots-search-row">
          <Search size={16} className="spots-search-icon" />
          <input
            className="spots-search-input"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="スポット名・住所で検索"
          />
        </div>
        {allFishTypes.length > 0 && (
          <div className="spots-fish-filter">
            {allFishTypes.map((f) => (
              <button
                key={f}
                className={`fish-tag sm fish-filter-chip ${selectedFish.has(f) ? "active" : ""}`}
                onClick={() => toggleFish(f)}
              >
                <Fish size={10} />
                {f}
              </button>
            ))}
          </div>
        )}
      </div>

      {filteredSpots.length === 0 ? (
        <div className="empty-state">
          <p>条件に合うスポットが見つかりませんでした</p>
          <p className="empty-hint">キーワードや魚種の絞り込みを変えてみてください</p>
        </div>
      ) : (
      <div className="spots-list">
        {filteredSpots.map((spot) => {
          const rec = recMap[spot.spotId];
          /** スコアがあればスコアに応じた色、なければグレーを使用 */
          const color = rec ? getScoreColor(rec.score) : "#9ca3af";
          return (
            <div key={spot.spotId} className="spot-row">
              <div className="spot-row-left">
                {/* スコアに応じた色の左端バー */}
                <div className="spot-score-bar" style={{ background: color }} />
                <div>
                  {/* スポット名: hover(PC)/長押し(スマホ)でスポット写真をプレビュー表示 */}
                  <ImagePreviewPopover imageUrl={spot.imageUrl}>
                    <p className="spot-row-name">{spot.name}</p>
                  </ImagePreviewPopover>
                  {/* おすすめデータがある場合のみ魚種タグを表示 */}
                  {rec && (
                    <div className="spot-row-fish">
                      {rec.fishTypes.map((f) => (
                        <ImagePreviewPopover key={f} fishName={f}>
                          <span className="fish-tag sm">
                            <Fish size={10} />{f}
                          </span>
                        </ImagePreviewPopover>
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
      )}
    </div>
  );
};