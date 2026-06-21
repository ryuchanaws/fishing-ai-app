import { useState, useEffect } from "react";
import { getSpots } from "../api/client";
import { getRecommendations } from "../api/client";
import type { Spot, Recommendation } from "../types";
import { Navigation2, Fish } from "lucide-react";
import { getScoreColor, getScoreLabel } from "../utils/score";

export const SpotsPage = () => {
  const [spots, setSpots] = useState<Spot[]>([]);
  const [recMap, setRecMap] = useState<Record<string, Recommendation>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getSpots(), getRecommendations()]).then(([s, r]) => {
      setSpots(s);
      const m: Record<string, Recommendation> = {};
      r.forEach((rec) => (m[rec.spotId] = rec));
      setRecMap(m);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="loading-state"><div className="loader" /><p>読み込み中...</p></div>;

  return (
    <div className="page spots-page">
      <div className="page-header">
        <h1 className="page-title">スポット一覧</h1>
        <p className="page-sub">全 {spots.length} スポット</p>
      </div>

      <div className="spots-list">
        {spots.map((spot) => {
          const rec = recMap[spot.spotId];
          const color = rec ? getScoreColor(rec.score) : "#9ca3af";
          return (
            <div key={spot.spotId} className="spot-row">
              <div className="spot-row-left">
                <div className="spot-score-bar" style={{ background: color }} />
                <div>
                  <p className="spot-row-name">{spot.name}</p>
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
                {rec && (
                  <span className="spot-row-score" style={{ color }}>
                    {Math.round(rec.score)} <small>{getScoreLabel(rec.score)}</small>
                  </span>
                )}
                
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