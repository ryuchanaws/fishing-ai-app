/**
 * @fileoverview アプリケーションのエントリーポイント。
 *
 * React DOM を初期化し、index.html の #root 要素に
 * App コンポーネントをマウントする。
 * StrictMode を有効化して開発時の潜在的な問題を検出する。
 */

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

/**
 * React DOM のルートを作成して App をレンダリングする。
 *
 * - document.getElementById("root")! の ! は
 *   index.html に #root が必ず存在することを TypeScript に伝える Non-null アサーション
 * - StrictMode により開発環境でのみ副作用の二重実行・非推奨 API の検出が行われる
 */
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);