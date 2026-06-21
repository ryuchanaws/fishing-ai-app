/**
 * @fileoverview お気に入りスポット一覧画面。
 *
 * ユーザーがハートボタンで保存したスポットを一覧表示する。
 * おすすめデータと突き合わせてスコア・AI コメント付きで表示し、
 * カードタップで詳細モーダルを開くことができる。
 */

import { useState } from "react";
import { useFavorites } from "../hooks/useFavorites";
import { useRecommendations } from "../hooks/useRecommendations";
import { RecommendationCard } from "../components/RecommendationCard";
import { DetailModal } from "../components/DetailModal";
import type { Recommendation } from "../types";
import { Heart } from "lucide-react";

/**
 * お気に入りスポット一覧ページコンポーネント。
 *
 * - お気に入り登録済みのスポットIDと recommendations を突き合わせて表示する
 * - お気に入りが0件の場合は空状態のガイドメッセージを表示する
 * - カードをタップすると DetailModal が開く
 *
 * @returns {JSX.Element} お気に入り一覧画面
 */
export const FavoritesPage = () => {
  /** useFavorites からお気に入り状態と操作関数を取得 */
  const { favorites, loading, toggleFavorite, isFavorite } = useFavorites();

  /** useRecommendations から全おすすめデータを取得 */
  const { recommendations } = useRecommendations();

  /** 詳細モーダルで表示中のおすすめデータ。null のときモーダルは非表示 */
  const [selected, setSelected] = useState<Recommendation | null>(null);

  /**
   * お気に入り登録済みスポットに絞り込んだおすすめデータ。
   * recommendations を isFavorite でフィルタリングして生成する。
   */
  const favRecs = recommendations.filter((r) => isFavorite(r.spotId));

  /** データ取得中はローディングスピナーを表示 */
  if (loading) return <div className="loading-state"><div className="loader" /><p>読み込み中...</p></div>;

  return (
    <div className="page favorites-page">
      <div className="page-header">
        <h1 className="page-title">
          {/* ハートアイコンをタイトル装飾として使用 */}
          <Heart size={22} fill="currentColor" style={{ color: "#e05c5c" }} />
          保存済みスポット
        </h1>
        {/* お気に入り件数をサブタイトルとして表示 */}
        <p className="page-sub">{favorites.length} 件</p>
      </div>

      {favRecs.length === 0 ? (
        /* お気に入りが0件のときに表示する空状態ガイド */
        <div className="empty-state">
          <Heart size={48} style={{ color: "#d1d5db", marginBottom: 12 }} />
          <p>まだ保存されたスポットがありません</p>
          <p className="empty-hint">おすすめ画面からハートをタップして保存しましょう</p>
        </div>
      ) : (
        /* お気に入りスポットのカード一覧 */
        <div className="rec-list">
          {favRecs.map((rec) => (
            <RecommendationCard
              key={rec.spotId}
              recommendation={rec}
              isFavorite={true}           /* お気に入り画面なので常に true */
              onToggleFavorite={toggleFavorite}
              onClick={setSelected}       /* タップで詳細モーダルを開く */
            />
          ))}
        </div>
      )}

      {/* 詳細モーダル: selected が null でないときのみ表示 */}
      {selected && (
        <DetailModal
          recommendation={selected}
          isFavorite={isFavorite(selected.spotId)}
          onClose={() => setSelected(null)}     /* 閉じると selected をリセット */
          onToggleFavorite={toggleFavorite}
        />
      )}
    </div>
  );
};