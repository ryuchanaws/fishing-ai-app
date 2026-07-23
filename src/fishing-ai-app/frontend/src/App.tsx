/**
 * @fileoverview アプリケーションのルートコンポーネント。
 *
 * ルーティング設定とレイアウト構造を定義する。
 * NavBar を固定ヘッダーとして表示し、
 * メインコンテンツエリアに各ページをルーティングする。
 */

import { BrowserRouter, Routes, Route } from "react-router-dom";
import { NavBar } from "./components/NavBar";
import { TopPage } from "./pages/TopPage";
import { MapPage } from "./pages/MapPage";
import { SpotsPage } from "./pages/SpotsPage";
import { FavoritesPage } from "./pages/FavoritesPage";
import { PostsPage } from "./pages/PostsPage";
import "./styles.css";

/**
 * ルートコンポーネント。
 *
 * - BrowserRouter で SPA ルーティングを有効化する
 * - NavBar を全ページ共通のナビゲーションバーとして表示する
 * - Routes で URL パスと各ページコンポーネントを対応づける
 *
 * @returns {JSX.Element} アプリケーション全体のレイアウト
 */
export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        {/* 全ページ共通の固定ナビゲーションバー */}
        <NavBar />
        <main className="main-content">
          <Routes>
            {/* / : おすすめTOP3・AI実行ボタン */}
            <Route path="/" element={<TopPage />} />
            {/* /map : Google Maps スポット地図 */}
            <Route path="/map" element={<MapPage />} />
            {/* /spots : スポット一覧リスト */}
            <Route path="/spots" element={<SpotsPage />} />
            {/* /favorites : お気に入りスポット一覧 */}
            <Route path="/favorites" element={<FavoritesPage />} />
            {/* /posts : 釣果投稿一覧・投稿作成 */}
            <Route path="/posts" element={<PostsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}