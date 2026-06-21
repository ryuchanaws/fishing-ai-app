/**
 * @fileoverview 釣りスポット地図画面。
 *
 * Google Maps 上に全スポットをマーカーで表示する。
 * マーカーの色はスコアに応じて変化し、タップすると
 * スポット名・スコア・魚種・ナビボタンを含む InfoWindow を表示する。
 */

import { useState, useEffect } from "react";
import { APIProvider, Map, AdvancedMarker, Pin, InfoWindow } from "@vis.gl/react-google-maps";
import { getSpots } from "../api/client";
import { getRecommendations } from "../api/client";
import type { Spot, Recommendation } from "../types";
import { getScoreColor } from "../utils/score";
import { Navigation2 } from "lucide-react";

/** Google Maps API キー（環境変数から取得。未設定の場合は空文字） */
const MAPS_KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY ?? "";

/** 地図の初期表示中心座標（東京駅付近） */
const DEFAULT_CENTER = { lat: 35.6812, lng: 139.7671 };

/**
 * スポット地図ページコンポーネント。
 *
 * - マウント時に spots・recommendations を並列取得して地図に反映する
 * - スコアに応じてマーカーの色を変える（高スコア: 緑 / 低スコア: 赤）
 * - マーカークリックで InfoWindow を表示し、ナビボタンから Google Maps に遷移できる
 *
 * @returns {JSX.Element} スポット地図画面
 */
export const MapPage = () => {
  /** 全釣りスポット一覧 */
  const [spots, setSpots] = useState<Spot[]>([]);

  /** spotId をキーにしたおすすめデータの辞書（マーカー色・InfoWindow 表示に使用） */
  const [recMap, setRecMap] = useState<Record<string, Recommendation>>({});

  /** InfoWindow で表示中のスポット。null のとき InfoWindow は非表示 */
  const [selected, setSelected] = useState<Spot | null>(null);

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
    });
  }, []);

  /**
   * 指定スポットへの Google Maps ナビゲーションを新しいタブで開く。
   *
   * @param {Spot} spot - ナビ先のスポット
   */
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
        {/* Google Maps API プロバイダー: 子コンポーネントで Maps API を使用可能にする */}
        <APIProvider apiKey={MAPS_KEY}>
          <Map
            defaultCenter={DEFAULT_CENTER}
            defaultZoom={10}
            mapId="fishing-map"
            style={{ width: "100%", height: "100%" }}
          >
            {/* 全スポットをマーカーとして描画 */}
            {spots.map((spot) => {
              const rec = recMap[spot.spotId];
              /** スコアがあればスコアに応じた色、なければグレーを使用 */
              const color = rec ? getScoreColor(rec.score) : "#6b7280";
              return (
                <AdvancedMarker
                  key={spot.spotId}
                  position={{ lat: spot.lat, lng: spot.lng }}
                  onClick={() => setSelected(spot)}  /* タップで InfoWindow を表示 */
                >
                  {/* スコアに応じた色のピンを表示 */}
                  <Pin background={color} borderColor="#fff" glyphColor="#fff" />
                </AdvancedMarker>
              );
            })}

            {/* 選択中スポットの InfoWindow（selected が null のとき非表示） */}
            {selected && (
              <InfoWindow
                position={{ lat: selected.lat, lng: selected.lng }}
                onCloseClick={() => setSelected(null)}  /* × ボタンで閉じる */
              >
                <div className="map-info">
                  <strong>{selected.name}</strong>
                  {/* おすすめデータがある場合のみスコア・魚種を表示 */}
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
                  {/* Google Maps ナビゲーションボタン */}
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