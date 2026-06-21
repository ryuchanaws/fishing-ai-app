import { useState } from "react";
import { useFavorites } from "../hooks/useFavorites";
import { useRecommendations } from "../hooks/useRecommendations";
import { RecommendationCard } from "../components/RecommendationCard";
import { DetailModal } from "../components/DetailModal";
import type { Recommendation } from "../types";
import { Heart } from "lucide-react";

export const FavoritesPage = () => {
  const { favorites, loading, toggleFavorite, isFavorite } = useFavorites();
  const { recommendations } = useRecommendations();
  const [selected, setSelected] = useState<Recommendation | null>(null);

  const favRecs = recommendations.filter((r) => isFavorite(r.spotId));

  if (loading) return <div className="loading-state"><div className="loader" /><p>読み込み中...</p></div>;

  return (
    <div className="page favorites-page">
      <div className="page-header">
        <h1 className="page-title">
          <Heart size={22} fill="currentColor" style={{ color: "#e05c5c" }} />
          保存済みスポット
        </h1>
        <p className="page-sub">{favorites.length} 件</p>
      </div>

      {favRecs.length === 0 ? (
        <div className="empty-state">
          <Heart size={48} style={{ color: "#d1d5db", marginBottom: 12 }} />
          <p>まだ保存されたスポットがありません</p>
          <p className="empty-hint">おすすめ画面からハートをタップして保存しましょう</p>
        </div>
      ) : (
        <div className="rec-list">
          {favRecs.map((rec) => (
            <RecommendationCard
              key={rec.spotId}
              recommendation={rec}
              isFavorite={true}
              onToggleFavorite={toggleFavorite}
              onClick={setSelected}
            />
          ))}
        </div>
      )}

      {selected && (
        <DetailModal
          recommendation={selected}
          isFavorite={isFavorite(selected.spotId)}
          onClose={() => setSelected(null)}
          onToggleFavorite={toggleFavorite}
        />
      )}
    </div>
  );
};