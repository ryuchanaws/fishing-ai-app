// vite.config.ts
// Vite のビルド・開発サーバー設定。
// React プラグインを有効化し、本番ビルドの出力先を指定する。

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // JSX/TSX の変換と Fast Refresh を有効化する公式 React プラグイン
  plugins: [react()],
  build: {
    // ビルド成果物の出力先ディレクトリ（S3/CloudFront・Cloudflare Pages にデプロイされる）
    outDir: "dist",
    // ソースマップは本番では生成しない（バンドルサイズ削減・ソース非公開のため）
    sourcemap: false,
  },
});