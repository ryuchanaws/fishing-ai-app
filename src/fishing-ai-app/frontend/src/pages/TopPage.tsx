/**
 * @fileoverview トップページ（おすすめスポット一覧画面）。
 *
 * AI分析によるおすすめスポットをスコア降順で表示する。
 * 上位3件をTOP3として強調表示し、残りはリスト形式で表示する。
 * 「AI分析を実行」ボタンでバッチ処理を手動トリガーできる。
 */

import { useState } from "react";
import { useRecommendations } from "../hooks/useRecommendations";
import { useFavorites } from "../hooks/useFavorites";
import { RecommendationCard } from "../components/RecommendationCard";
import { AiBatchButton } from "../components/AiBatchButton";
import { DetailModal } from "../components/DetailModal";
import type { Recommendation } from "../types";
import { RefreshCw } from "lucide-react";

/**
 * トップページコンポーネント。
 *
 * - おすすめスポットをスコア降順で取得して表示する
 * - 上位3件を TOP3 グリッド、残りをリスト形式で表示する
 * - 「AI分析を実行」ボタンでバッチ処理を手動トリガーし、完了後に画面を更新する
 * - カードタップで DetailModal を開く
 *
 * @returns {JSX.Element} トップページ画面
 */
export const TopPage = () => {
  /** おすすめデータ・ローディング状態・バッチ実行関数を取得 */
  const { recommendations, loading, batchStatus, error, triggerAiBatch, refetch } = useRecommendations();

  /** お気に入り状態と操作関数を取得 */
  const { isFavorite, toggleFavorite } = useFavorites();

  /** 詳細モーダルで表示中のおすすめデータ。null のときモーダルは非表示 */
  const [selected, setSelected] = useState<Recommendation | null>(null);

  /** スコア上位3件（TOP3グリッドに表示） */
  const top3 = recommendations.slice(0, 3);

  /** 4件目以降（リスト形式で表示） */
  const rest = recommendations.slice(3);

  return (
    <div className="page top-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">今日の釣りどこへ行く？</h1>
          <p className="page-sub">AIがあなたの釣行を最適化します</p>
        </div>
        {/* 手動更新ボタン: クリックでおすすめデータを再取得 */}
        <button className="icon-btn" onClick={refetch} title="更新" disabled={loading}>
          <RefreshCw size={18} className={loading ? "spin" : ""} />
        </button>
      </div>

      {/* AI実行ボタンセクション: クリックでバッチ処理を手動トリガー */}
      <div className="ai-batch-section">
        <AiBatchButton status={batchStatus} onRun={triggerAiBatch} />
      </div>

      {/* エラー発生時のエラーバナー */}
      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        /* データ取得中はローディングスピナーを表示 */
        <div className="loading-state">
          <div className="loader" />
          <p>おすすめを読み込み中...</p>
        </div>
      ) : (
        <>
          {/* TOP3セクション: スコア上位3件をグリッド表示 */}
          {top3.length > 0 && (
            <section className="top3-section">
              <h2 className="section-title">
                <span className="section-icon">🏆</span>
                おすすめTOP3
              </h2>
              <div className="top3-grid">
                {top3.map((rec, i) => (
                  <RecommendationCard
                    key={rec.spotId}
                    recommendation={rec}
                    rank={i + 1}          /* 1〜3のランク番号を渡す */
                    isFavorite={isFavorite(rec.spotId)}
                    onToggleFavorite={toggleFavorite}
                    onClick={setSelected} /* タップで詳細モーダルを開く */
                  />
                ))}
              </div>
            </section>
          )}

          {/* その他セクション: 4件目以降をリスト表示 */}
          {rest.length > 0 && (
            <section className="more-section">
              <h2 className="section-title">その他のスポット</h2>
              <div className="rec-list">
                {rest.map((rec) => (
                  <RecommendationCard
                    key={rec.spotId}
                    recommendation={rec}
                    isFavorite={isFavorite(rec.spotId)}
                    onToggleFavorite={toggleFavorite}
                    onClick={setSelected}
                  />
                ))}
              </div>
            </section>
          )}

          {/* おすすめデータが0件のときの空状態ガイド */}
          {recommendations.length === 0 && (
            <div className="empty-state">
              <p>まだおすすめデータがありません</p>
              <p className="empty-hint">「AI分析を実行」ボタンでデータを生成してください</p>
            </div>
          )}
        </>
      )}

      {/* 詳細モーダル: selected が null でないときのみ表示 */}
      {selected && (
        <DetailModal
          recommendation={selected}
          isFavorite={isFavorite(selected.spotId)}
          onClose={() => setSelected(null)}    /* 閉じると selected をリセット */
          onToggleFavorite={toggleFavorite}
        />
      )}
    </div>
  );
};