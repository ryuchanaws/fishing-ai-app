import { test, expect } from "@playwright/test";
import { mockApi, MOCK_RECOMMENDATIONS } from "./fixtures";

test.describe("TopPage", () => {
  test("shows TOP3 recommendations from the API", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");

    await expect(page.getByText("おすすめTOP3")).toBeVisible();
    for (const rec of MOCK_RECOMMENDATIONS) {
      await expect(page.getByText(rec.spot.name)).toBeVisible();
    }
  });
});
