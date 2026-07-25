// playwright.config.ts
// E2E/VRT（Visual Regression Testing）用のPlaywright設定。
// 2026-07-25追加。実AWSには接続せず、各テストでAPIレスポンスをモックする
// （本番データを汚さない・API利用料を発生させないため）。

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // Playwrightのデフォルトレポーターはhtmlを自動生成しない（CIでは'dot'のみ）ため、
  // 明示的にhtmlレポーターを有効化する。VRT失敗時の実際のスクリーンショットを
  // CIのアーティファクトとして取得できるようにするため（README「テスト」セクション参照）
  reporter: [["list"], ["html", { open: "never" }]],
  // ビルド済みの静的ファイルをプレビューサーバーで配信し、そこに対してテストする
  webServer: {
    command: "npm run preview -- --port 4173",
    url: "http://localhost:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  use: {
    baseURL: "http://localhost:4173",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // VRT（toHaveScreenshot）のベースライン画像はOS/フォントレンダリングに依存するため、
  // ローカル(Windows)で生成したものはCI(ubuntu-latest)と一致しない可能性が高い。
  // README「テスト」セクションに運用方法を記載している
  expect: {
    toHaveScreenshot: { maxDiffPixelRatio: 0.02 },
  },
});
