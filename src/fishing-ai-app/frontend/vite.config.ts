// vite.config.ts
// Vite のビルド・開発サーバー設定。
// React プラグインを有効化し、本番ビルドの出力先を指定する。

// defineConfig は vitest/config から読み込む（vite本来のdefineConfigの型を
// 拡張し、下記の test ブロックの型付けを可能にするだけで、Vite本体の挙動は変わらない）
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  // JSX/TSX の変換と Fast Refresh を有効化する公式 React プラグイン
  // VitePWA: manifest.webmanifest とService Workerを自動生成しPWA化する（2026-07-25追加）
  // 要件定義に明記されている「PWA（スマホ・PC対応）」が未実装だったための対応
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      // public/ 直下のアイコンをビルド成果物にそのままコピーする
      includeAssets: ["apple-touch-icon.png"],
      manifest: {
        name: "釣行AIアプリ - つり羅針盤",
        short_name: "つり羅針盤",
        description: "AIが釣行の意思決定をサポートするアプリ",
        lang: "ja",
        theme_color: "#00c896",
        background_color: "#0f1117",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
          {
            src: "pwa-maskable-512x512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // SPAルーティング（/map, /spots等）のオフライン時フォールバック先
        navigateFallback: "index.html",
      },
    }),
  ],
  build: {
    // ビルド成果物の出力先ディレクトリ（S3/CloudFront・Cloudflare Pages にデプロイされる）
    outDir: "dist",
    // ソースマップは本番では生成しない（バンドルサイズ削減・ソース非公開のため）
    sourcemap: false,
  },
  test: {
    // ユニットテスト（Vitest）設定。2026-07-25追加。
    // DOM操作を伴うコンポーネントテストのため jsdom 環境を使用する
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // e2e/（Playwright）配下はVitestの対象から除外する（実行方法が異なるため）
    exclude: ["e2e/**", "node_modules/**"],
  },
});