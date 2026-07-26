/**
 * @fileoverview グローバルナビゲーションバーコンポーネント。
 *
 * 全ページ共通の固定ヘッダーとして表示される。
 * アプリロゴと各ページへのナビゲーションリンクを提供する。
 * アクティブなリンクは react-router-dom の NavLink が自動で検出する。
 */

import { useState } from "react";
import { NavLink, Link } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import {
  Home,
  Map,
  Heart,
  LayoutGrid,
  Camera,
  MessageCircle,
  HelpCircle,
  LogIn,
  LogOut,
  Store,
  UserCircle,
} from "lucide-react";
import { cognitoSignOut } from "../auth/authConfig";
import { useProfile } from "../hooks/useProfile";
import { ProfileModal } from "./ProfileModal";

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
 * - ログイン中は表示名（未設定ならメールアドレス）を表示し、編集ボタンから変更できる。
 *   表示名が未設定のままログインした場合は初回に自動で設定モーダルを開く（2026-07-26追加）
 *
 * @returns {JSX.Element} ナビゲーションバー
 */
export const NavBar = () => {
  const auth = useAuth();
  const { profile, needsSetup, updateDisplayName, dismissSetup } = useProfile();
  const [showProfileModal, setShowProfileModal] = useState(false);

  /**
   * ログアウト処理。react-oidc-context側のローカルセッションを消してから、
   * Cognito Hosted UI自体のセッションも切るため /logout エンドポイントへ遷移する。
   */
  const handleLogout = async () => {
    await auth.removeUser();
    cognitoSignOut();
  };

  /** 表示名モーダルを閉じる。手動で開いていた場合も初回自動表示だった場合も同じ扱いでよい */
  const closeProfileModal = () => {
    setShowProfileModal(false);
    dismissSetup();
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

      {/* 釣具店検索ページ（2026-07-26追加。おすすめ・新スポット探索からは釣具店を除外し、こちらに集約） */}
      <NavLink to="/tackle-shops" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
        <Store size={18} />
        <span>釣具店</span>
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

    {/* ログイン状態表示: ログイン中は表示名（未設定ならメールアドレス）+編集+ログアウト、未ログイン時はログインボタン */}
    <div className="nav-auth">
      {auth.isAuthenticated ? (
        <>
          <span className="nav-auth-email">{profile?.displayName || auth.user?.profile.email}</span>
          <button
            className="icon-btn"
            onClick={() => setShowProfileModal(true)}
            title="表示名を編集"
            aria-label="表示名を編集"
          >
            <UserCircle size={18} />
          </button>
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

    {/* 表示名設定モーダル: 手動で開いた場合、またはログイン後に未設定だった場合に自動表示 */}
    {(showProfileModal || needsSetup) && (
      <ProfileModal
        currentName={profile?.displayName}
        onSave={updateDisplayName}
        onClose={closeProfileModal}
      />
    )}
  </nav>
  );
};