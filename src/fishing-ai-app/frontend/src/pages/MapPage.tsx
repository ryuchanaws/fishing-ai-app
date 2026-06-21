import { useState, useEffect } from "react";
import { APIProvider, Map, AdvancedMarker, Pin, InfoWindow } from "@vis.gl/react-google-maps";
import { getSpots } from "../api/client";
import { getRecommendations } from "../api/client";
import type { Spot, Recommendation } from "../types";
import { getScoreColor } from "../utils/score";
import { Navigation2 } from "lucide-react";

const MAPS_KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY ?? "";
const DEFAULT_CENTER = { lat: 35.6812, lng: 139.7671 };

export const MapPage = () => {
  const [spots, setSpots] = useState<Spot[]>([]);
  const [recMap, setRecMap] = useState<Record<string, Recommendation>>({});
  const [selected, setSelected] = useState<Spot | null>(null);

  useEffect(() => {
    Promise.all([getSpots(), getRecommendations()]).then(([s, r]) => {
      setSpots(s);
      const m: Record<string, Recommendation> = {};
      r.forEach((rec) => (m[rec.spotId] = rec));
      setRecMap(m);
    });
  }, []);

  const openNav = (spot: Spot) => {
    window.open(
      `https://www.google.com/maps/dir/?api=1&destination=${spot.lat},${spot.lng}`,
      "_blank"
    );
  };

  return (
    <div className="page map-page">
      <div className="page-header">
        <h1 className="page-title">スポット地図</h1>
        <p className="page-sub">マーカーをタップして詳細を確認</p>
      </div>

      <div className="map-container">
        <APIProvider apiKey={MAPS_KEY}>
          <Map
            defaultCenter={DEFAULT_CENTER}
            defaultZoom={10}
            mapId="fishing-map"
            style={{ width: "100%", height: "100%" }}
          >
            {spots.map((spot) => {
              const rec = recMap[spot.spotId];
              const color = rec ? getScoreColor(rec.score) : "#6b7280";
              return (
                <AdvancedMarker
                  key={spot.spotId}
                  position={{ lat: spot.lat, lng: spot.lng }}
                  onClick={() => setSelected(spot)}
                >
                  <Pin background={color} borderColor="#fff" glyphColor="#fff" />
                </AdvancedMarker>
              );
            })}

            {selected && (
              <InfoWindow
                position={{ lat: selected.lat, lng: selected.lng }}
                onCloseClick={() => setSelected(null)}
              >
                <div className="map-info">
                  <strong>{selected.name}</strong>
                  {recMap[selected.spotId] && (
                    <>
                      <p className="map-info-score">
                        スコア: {Math.round(recMap[selected.spotId].score)}
                      </p>
                      <p className="map-info-fish">
                        {recMap[selected.spotId].fishTypes.join(" / ")}
                      </p>
                    </>
                  )}
                  <button className="map-nav-btn" onClick={() => openNav(selected)}>
                    <Navigation2 size={13} /> ナビ開始
                  </button>
                </div>
              </InfoWindow>
            )}
          </Map>
        </APIProvider>
      </div>
    </div>
  );
};