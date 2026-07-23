/**
 * @fileoverview 緯度経度間の距離計算ユーティリティ。
 *
 * 「現在地からのおすすめ」機能で、ユーザーの現在地と各スポットの
 * 距離をクライアント側で算出するために使用する。
 */

/**
 * 2地点間の距離をhaversine公式でkm単位で算出する。
 *
 * backend/lambda/batch/discover_spots.py の haversine_km() と同一の計算式。
 *
 * @param {number} lat1 - 地点1の緯度
 * @param {number} lng1 - 地点1の経度
 * @param {number} lat2 - 地点2の緯度
 * @param {number} lng2 - 地点2の経度
 * @returns {number} 2地点間の距離（km）
 */
export const haversineKm = (lat1: number, lng1: number, lat2: number, lng2: number): number => {
  const R = 6371;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
};
