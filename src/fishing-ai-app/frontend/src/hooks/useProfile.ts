/**
 * ユーザー自身のプロフィール（表示名）の状態管理カスタムフック。
 *
 * /me はCognito認証必須のため、未ログイン時はAPIを呼ばない。
 * 表示名が未設定のログイン中ユーザーには needsSetup=true を返し、
 * NavBar側でプロフィール設定モーダルを自動表示するトリガーに使う。
 *
 * @module useProfile
 */
import { useState, useEffect, useCallback } from "react";
import { useAuth } from "react-oidc-context";
import type { Profile } from "../types";
import { getMyProfile, updateMyProfile } from "../api/client";

export const useProfile = () => {
  const auth = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [dismissedSetup, setDismissedSetup] = useState(false);

  const fetchProfile = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getMyProfile();
      setProfile(data);
    } catch {
      console.error("Failed to load profile");
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * ログイン済みの場合のみプロフィールを取得する（未ログイン時は空のまま）。
   * ログイン/ログアウトのたびに再評価される。
   */
  useEffect(() => {
    if (auth.isAuthenticated) {
      fetchProfile();
    } else {
      setProfile(null);
      setLoading(false);
    }
  }, [auth.isAuthenticated, fetchProfile]);

  /**
   * 表示名を保存し、ローカルのプロフィール状態にも反映する。
   *
   * @param {string} displayName - 新しい表示名
   * @returns {Promise<void>}
   */
  const updateDisplayName = useCallback(async (displayName: string) => {
    const updated = await updateMyProfile(displayName);
    setProfile((prev) => (prev ? { ...prev, displayName: updated.displayName } : prev));
  }, []);

  /** モーダルを「後で」閉じたことを記録し、このセッション中は自動表示しないようにする */
  const dismissSetup = useCallback(() => setDismissedSetup(true), []);

  const needsSetup =
    auth.isAuthenticated && !loading && profile !== null && !profile.displayName && !dismissedSetup;

  return { profile, loading, needsSetup, updateDisplayName, dismissSetup };
};
