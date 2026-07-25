/**
 * @fileoverview グローバルナビゲーションバーコンポーネント。
 *
 * 全ページ共通の固定ヘッダーとして表示される。
 * アプリロゴと各ページへのナビゲーションリンクを提供する。
 * アクティブなリンクは react-router-dom の NavLink が自動で検出する。
 */

import { NavLink, Link } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import { Home, Map, Heart, LayoutGrid, Camera, MessageCircle, HelpCircle, LogIn, LogOut } from "lucide-react";
import { cognitoSignOut } from "../auth/authConfig";

/**
 * グローバルナビゲーションバーコンポーネント。
 *
 * - 画面上部に固定表示（CSS: position: fixed）
 * - NavLink の isActive を使ってアクティブなリンクにクラスを付与する
 * - モバイルではアプリ名・各リンクのラベル文字を非表示にしてアイコンのみ表示する
 *   （2026-07-25: リンク数が増えて折り返し表示になり見づらかったため）
 * - ロゴ（アイコン+アプリ名）クリックでトップページ（おすすめ）に戻れる
 * - 右端にログイン状態を表示する（2026-07-26追加）。閲覧は未ログインでも可能だが、
 *   お気に入り・投稿・AI相談・AI分析実行にはログインが必要なため、常時ログイン導線を出す
 *
 * @returns {JSX.Element} ナビゲーションバー
 */
export const NavBar = () => {
  const auth = useAuth();

  /**
   * ログアウト処理。react-oidc-context側のローカルセッションを消してから、
   * Cognito Hosted UI自体のセッションも切るため /logout エンドポイントへ遷移する。
   */
  const handleLogout = async () => {
    await auth.removeUser();
    cognitoSignOut();
  };

  return (
  <nav className="navbar">
    {/* ブランドロゴ: アプリ名とアイコン。クリックでトップページに戻る */}
    <Link to="/" className="nav-brand">
      <span className="nav-logo">🎣</span>
      <span className="nav-title">つり羅針盤</span>
    </Link>

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

      {/* AIチャットページ */}
      <NavLink to="/chat" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
        <MessageCircle size={18} />
        <span>AI相談</span>
      </NavLink>

      {/* 使い方ガイドページ */}
      <NavLink to="/guide" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
        <HelpCircle size={18} />
        <span>使い方</span>
      </NavLink>
    </div>

    {/* ログイン状態表示: ログイン中はメールアドレス+ログアウトボタン、未ログイン時はログインボタン */}
    <div className="nav-auth">
      {auth.isAuthenticated ? (
        <>
          <span className="nav-auth-email">{auth.user?.profile.email}</span>
          <button className="icon-btn" onClick={handleLogout} title="ログアウト" aria-label="ログアウト">
            <LogOut size={18} />
          </button>
        </>
      ) : (
        <button className="icon-btn" onClick={() => auth.signinRedirect()} title="ログイン" aria-label="ログイン">
          <LogIn size={18} />
          <span className="nav-auth-label">ログイン</span>
        </button>
      )}
    </div>
  </nav>
  );
};