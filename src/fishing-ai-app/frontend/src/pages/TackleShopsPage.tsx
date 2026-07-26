/**
 * @fileoverview 釣具店検索ページ。
 *
 * おすすめ・新スポット探索からは釣具店を除外した（discover_spots.pyの
 * EXCLUDED_PLACE_TYPES参照）代わりに、釣具店専用の検索機能として独立させたページ。
 * スコアは付与せず、現在地からの近傍検索とキーワード（地名・県名）検索の2通りを提供する。
 * 検索結果はDBに保存されない（都度Google Places APIを検索するだけ）。
 */

import { useState, useEffect } from "react";
import axios from "axios";
import { useAuth } from "react-oidc-context";
import { LocateFixed, Loader2, AlertCircle, Search, Navigation2, Store } from "lucide-react";
import { useGeolocation } from "../hooks/useGeolocation";
import { searchTackleShops } from "../api/client";
import type { TackleShop } from "../types";

/**
 * 釣具店検索ページコンポーネント。
 *
 * - 「現在地から探す」ボタンで位置情報を取得し、取得できたら自動的に近傍検索する
 *   （useGeolocationの状態遷移はSpotDiscoveryButton.tsx等と同じidle/loading/denied/errorパターン）
 * - テキスト入力欄からは地名・県名等でのキーワード検索ができる
 * - 結果一覧はSpotsPage.tsxの`.spot-row`スタイルを流用し、スコアバーは常にグレー固定にする
 * - /tackle-shops/search はCognito認証必須（Places API呼び出しのコスト保護）なので、
 *   未ログイン時は検索を実行せずログイン画面へ誘導する（他の保護対象操作と同じパターン）
 *
 * @returns {JSX.Element} 釣具店検索ページ
 */
export const TackleShopsPage = () => {
  const auth = useAuth();
  const geo = useGeolocation();
  const [keyword, setKeyword] = useState("");
  const [results, setResults] = useState<TackleShop[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  /**
   * 検索を実行し、結果をステートに反映する。
   *
   * @param {object} params - lat/lng（現在地検索）または keyword（テキスト検索）
   */
  const runSearch = async (params: { lat?: number; lng?: number; keyword?: string }) => {
    setSearching(true);
    setError(null);
    try {
      const items = await searchTackleShops(params);
      setResults(items);
      setSearched(true);
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 429) {
        // 1日あたりの検索回数上限（コスト保護、2026-07-26追加）
        setError(err.response.data?.message ?? "本日の検索回数の上限に達しました");
      } else {
        setError("検索に失敗しました");
      }
    } finally {
      setSearching(false);
    }
  };

  /** 現在地取得に成功したら自動的に近傍検索を実行する */
  useEffect(() => {
    if (geo.status === "granted" && geo.position) {
      runSearch({ lat: geo.position.lat, lng: geo.position.lng });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geo.status, geo.position]);

  /**
   * 「現在地から探す」ボタンのクリック処理。未ログイン時はログイン画面へ誘導する。
   */
  const handleNearbyClick = () => {
    if (!auth.isAuthenticated) {
      auth.signinRedirect();
      return;
    }
    geo.request();
  };

  /**
   * テキスト検索フォームの送信処理。未ログイン時はログイン画面へ誘導する。
   *
   * @param {React.FormEvent} e - フォーム送信イベント
   */
  const handleKeywordSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyword.trim()) return;
    if (!auth.isAuthenticated) {
      auth.signinRedirect();
      return;
    }
    runSearch({ keyword: keyword.trim() });
  };

  const isBusy = geo.status === "loading" || searching;

  return (
    <div className="page tackle-shops-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">釣具店を探す</h1>
          <p className="page-sub">現在地から、またはキーワードで検索できます</p>
        </div>
      </div>

      <div className="ai-batch-section">
        <button
          className={`ai-batch-btn ${isBusy ? "running" : ""}`}
          onClick={handleNearbyClick}
          disabled={isBusy}
        >
          {geo.status === "loading" ? (
            <>
              <Loader2 size={18} className="spin" />
              <span>現在地を取得中...</span>
            </>
          ) : (
            <>
              <LocateFixed size={18} />
              <span>現在地から探す</span>
            </>
          )}
        </button>
      </div>

      {geo.status === "denied" && (
        <div className="batch-status error">
          <AlertCircle size={14} />
          <span>位置情報の利用が許可されていません</span>
        </div>
      )}

      <form className="tackle-search-form" onSubmit={handleKeywordSearch}>
        <input
          className="post-form-input"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="地名・県名で検索（例: 神奈川県三浦市）"
        />
        <button className="icon-btn" type="submit" disabled={searching || !keyword.trim()} aria-label="検索">
          <Search size={18} />
        </button>
      </form>

      {error && <div className="error-banner">{error}</div>}

      {searching ? (
        <div className="loading-state">
          <div className="loader" />
          <p>検索中...</p>
        </div>
      ) : searched && results.length === 0 ? (
        <div className="empty-state">
          <Store size={48} style={{ color: "#d1d5db", marginBottom: 12 }} />
          <p>見つかりませんでした</p>
          <p className="empty-hint">別のキーワードや現在地検索をお試しください</p>
        </div>
      ) : (
        <div className="spots-list">
          {results.map((shop, i) => (
            <div key={`${shop.lat},${shop.lng},${i}`} className="spot-row">
              <div className="spot-row-left">
                <div className="spot-score-bar" style={{ background: "#9ca3af" }} />
                <div>
                  <p className="spot-row-name">{shop.name}</p>
                  <p className="tackle-shop-address">{shop.address}</p>
                </div>
              </div>
              <div className="spot-row-right">
                {shop.distanceKm != null && <span className="spot-row-score">{shop.distanceKm}km</span>}
                <a
                  href={`https://www.google.com/maps/dir/?api=1&destination=${shop.lat},${shop.lng}`}
                  target="_blank"
                  rel="noreferrer"
                  className="icon-btn"
                  title="ナビ"
                >
                  <Navigation2 size={16} />
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
