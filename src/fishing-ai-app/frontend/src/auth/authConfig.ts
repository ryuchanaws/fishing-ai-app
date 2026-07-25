/**
 * @fileoverview Cognito Hosted UI（Google認証）向けのOIDC設定。
 *
 * Cognito User Pool + Google IdPで発行されるOAuth 2.0 Authorization Code + PKCE
 * フローを、react-oidc-context / oidc-client-ts に任せるための設定値をまとめる。
 * User Pool ID・Client ID・Hosted UIドメインはCognitoデプロイ後にしか確定しない値のため、
 * 環境変数（VITE_COGNITO_*）から読み込む。SAMデプロイの Outputs にそれぞれ対応する値がある
 * （UserPoolId / UserPoolClientId / CognitoHostedUiDomain）。
 */

import type { AuthProviderProps } from "react-oidc-context";

const REGION = import.meta.env.VITE_AWS_REGION || "ap-northeast-1";
const USER_POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID || "";
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID || "";

/** Cognito Hosted UIのドメイン（例: https://fishing-ai-app-123456789012.auth.ap-northeast-1.amazoncognito.com） */
export const COGNITO_DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN || "";

/**
 * react-oidc-context の AuthProvider に渡す設定。
 *
 * - authority: Cognito User PoolのOIDCディスカバリエンドポイントのベースURL
 * - redirect_uri: ログイン後に戻ってくるURL（トップページに固定。CallbackURLsに登録済み）
 * - onSigninCallback: ログイン直後、URLに残る ?code=&state= をブラウザ履歴から消す
 *   （付いたままだと再読み込み時に再度コード交換を試みてエラーになるため）
 */
export const oidcConfig: AuthProviderProps = {
  authority: `https://cognito-idp.${REGION}.amazonaws.com/${USER_POOL_ID}`,
  client_id: CLIENT_ID,
  redirect_uri: typeof window !== "undefined" ? window.location.origin + "/" : "/",
  response_type: "code",
  scope: "email openid profile",
  automaticSilentRenew: true,
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

/**
 * Cognito Hosted UIのログアウトエンドポイントへ遷移する。
 *
 * CognitoはOIDC標準のend_session_endpointをディスカバリドキュメントに含めないため、
 * react-oidc-contextの標準的なsignoutRedirect()は使えない。Hosted UI独自の
 * `/logout`エンドポイントへ直接遷移する（AWS公式ドキュメントに記載の方式）。
 * 呼び出し側で先に auth.removeUser() を呼び、ローカルのセッション情報を消してから使うこと。
 */
export const cognitoSignOut = (): void => {
  const logoutUri = window.location.origin + "/";
  window.location.href = `${COGNITO_DOMAIN}/logout?client_id=${CLIENT_ID}&logout_uri=${encodeURIComponent(logoutUri)}`;
};
