/**
 * @fileoverview グローバルナビゲーションバーコンポーネント。
 *
 * 全ページ共通の固定ヘッダーとして表示される。
 * アプリロゴと各ページへのナビゲーションリンクを提供する。
 * アクティブなリンクは react-router-dom の NavLink が自動で検出する。
 */

import { NavLink } from "react-router-dom";
import { Home, Map, Heart, LayoutGrid, Camera } from "lucide-react";

/**
 * グローバルナビゲーションバーコンポーネント。
 *
 * - 画面上部に固定表示（CSS: position: fixed）
 * - NavLink の isActive を使ってアクティブなリンクにクラスを付与する
 * - モバイルではアプリ名を非表示にしてアイコンのみ表示する
 *
 * @returns {JSX.Element} ナビゲーションバー
 */
export const NavBar = () => (
  <nav className="navbar">
    {/* ブランドロゴ: アプリ名とアイコン */}
    <div className="nav-brand">
      <span className="nav-logo">🎣</span>
      <span className="nav-title">つり羅針盤</span>
    </div>

    {/* ナビゲーションリンク一覧 */}
    <div className="nav-links">
      {/* トップページ: end を指定して / と /map を区別する */}
      <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
        <Home size={18} />
        <span>おすすめ</span>
      </NavLink>

      {/* 地図ページ */}
      <NavLink to="/map" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
        <Map size={18} />
        <span>地図</span>
      </NavLink>

      {/* スポット一覧ページ */}
      <NavLink to="/spots" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
        <LayoutGrid size={18} />
        <span>スポット</span>
      </NavLink>

      {/* お気に入りページ */}
      <NavLink to="/favorites" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
        <Heart size={18} />
        <span>保存済み</span>
      </NavLink>

      {/* 釣果投稿ページ */}
      <NavLink to="/posts" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
        <Camera size={18} />
        <span>釣果</span>
      </NavLink>
    </div>
  </nav>
);