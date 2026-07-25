// e2e/visual.spec.ts
// VRT（Visual Regression Testing）。トップページ・スポット一覧ページのスクリーンショットを
// 既存のベースライン画像（このファイルと同じディレクトリの visual.spec.ts-snapshots/）と比較する。
//
// 注意: ベースライン画像はOS/フォントレンダリングに依存する。ローカル(Windows)で
// `npx playwright test --update-snapshots` を実行して生成したものは、CI(ubuntu-latest)の
// レンダリングと一致しない可能性が高い。初回はCI上のベースライン無し状態での失敗を許容し、
// そのCI実行のアーティファクトからベースラインを取得してコミットする運用を想定している
// （詳細はREADMEの「テスト」セクション参照）。

import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.describe("Visual regression", () => {
  test("top page layout", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    await expect(page.getByText("おすすめTOP3")).toBeVisible();
    await expect(page).toHaveScreenshot("top-page.png", { fullPage: true });
  });

  test("spots page layout", async ({ page }) => {
    await mockApi(page);
    await page.goto("/spots");
    await expect(page.getByText("スポット一覧")).toBeVisible();
    await expect(page).toHaveScreenshot("spots-page.png", { fullPage: true });
  });
});
