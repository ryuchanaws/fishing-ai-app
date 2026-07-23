/**
 * 現在地取得用のカスタムフック。
 *
 * ブラウザの Geolocation API をラップし、「現在地からのおすすめ」機能で
 * 現在地の緯度経度と取得状態を提供する。
 *
 * @module useGeolocation
 */
import { useState, useCallback } from "react";

/** 現在地の緯度経度 */
export interface GeoPosition {
  lat: number;
  lng: number;
}

/**
 * 現在地取得の状態。
 * - `idle`     : 未リクエスト（初期状態）
 * - `loading`  : 取得中
 * - `granted`  : 取得成功
 * - `denied`   : ユーザーが位置情報の利用を拒否した
 * - `error`    : 拒否以外の理由で取得に失敗した（タイムアウト等）
 */
export type GeoStatus = "idle" | "loading" | "granted" | "denied" | "error";

/**
 * 現在地を取得するカスタムフック。
 *
 * @returns {object} 現在地取得に必要な状態と操作関数
 * @returns {GeoPosition | null} position - 取得した現在地（未取得時は null）
 * @returns {GeoStatus}          status   - 取得状態
 * @returns {Function}           request  - 現在地取得をリクエストする関数
 */
export const useGeolocation = () => {
  const [position, setPosition] = useState<GeoPosition | null>(null);
  const [status, setStatus] = useState<GeoStatus>("idle");

  /**
   * ブラウザに現在地取得を要求する。
   * 許可ダイアログの結果に応じて status を更新する。
   */
  const request = useCallback(() => {
    if (!navigator.geolocation) {
      setStatus("error");
      return;
    }

    setStatus("loading");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setPosition({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setStatus("granted");
      },
      (err) => {
        setStatus(err.code === err.PERMISSION_DENIED ? "denied" : "error");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
    );
  }, []);

  return { position, status, request };
};
