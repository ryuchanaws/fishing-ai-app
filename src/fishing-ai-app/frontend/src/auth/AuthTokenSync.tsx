/**
 * @fileoverview 認証状態とAPIクライアントを同期する。
 *
 * react-oidc-contextが管理するid_tokenを、api/client.tsの共有axiosインスタンスへ
 * 反映する。ログイン/ログアウト/トークン更新のたびにここが再実行され、
 * 以降のAPIリクエストのAuthorizationヘッダーが自動で最新化される。
 * 画面には何も描画しない（AuthProviderの内側にマウントするだけの同期用コンポーネント）。
 */

import { useEffect } from "react";
import { useAuth } from "react-oidc-context";
import { setAuthToken } from "../api/client";

export const AuthTokenSync = () => {
  const auth = useAuth();

  useEffect(() => {
    setAuthToken(auth.user?.id_token ?? null);
  }, [auth.user]);

  return null;
};
