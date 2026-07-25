// e2e/fixtures.ts
// E2Eテストで使うAPIモックのヘルパー。実AWSには一切接続せず、
// page.route() でバックエンドのレスポンスをスタブする。

import type { Page, Route } from "@playwright/test";

export const MOCK_SPOTS = [
  { spotId: "spot-001", name: "三浦半島・城ヶ島", lat: 35.1397, lng: 139.6177 },
  { spotId: "spot-002", name: "江ノ島", lat: 35.2991, lng: 139.4804 },
];

export const MOCK_RECOMMENDATIONS = [
  {
    spotId: "spot-001",
    score: 85,
    fishTypes: ["アジ", "イサキ"],
    reason: "潮の動きが良く、期待できます。",
    distance: 65,
    cost: 0,
    weatherScore: 90,
    tideScore: 80,
    spot: MOCK_SPOTS[0],
  },
  {
    spotId: "spot-002",
    score: 72,
    fishTypes: ["クロダイ", "シーバス"],
    reason: "天気は良好ですが、やや遠めです。",
    distance: 50,
    cost: 0,
    weatherScore: 85,
    tideScore: 60,
    spot: MOCK_SPOTS[1],
  },
];

/**
 * TopPage/SpotsPage等が呼ぶ基本的なGETエンドポイントを、
 * ワイルドカードパターン（実際のホスト・VITE_API_BASE_URLの値に依存しない）でモックする。
 *
 * 注意: "**\/spots" のようなパターンは、Reactの/spotsページ自体への
 * ブラウザナビゲーション（http://localhost:4173/spots）にもマッチしてしまい、
 * ページ遷移そのものをJSONレスポンスで乗っ取ってしまう事故が起きたため、
 * resourceType が "document"（＝ページ本体のナビゲーション）のリクエストは
 * 素通しし、fetch/xhr（＝実際のAPI呼び出し）だけをモックする。
 *
 * @param {Page} page - Playwrightのページオブジェクト
 */
export const mockApi = async (page: Page): Promise<void> => {
  const fulfillJson = (body: unknown) => (route: Route) => {
    if (route.request().resourceType() === "document") {
      return route.continue();
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  };

  await page.route("**/recommendations", fulfillJson({ items: MOCK_RECOMMENDATIONS }));
  await page.route("**/spots", fulfillJson({ items: MOCK_SPOTS }));
  await page.route("**/favorites*", fulfillJson({ items: [] }));
};
