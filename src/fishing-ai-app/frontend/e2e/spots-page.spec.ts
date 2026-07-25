import { test, expect } from "@playwright/test";
import { mockApi, MOCK_SPOTS } from "./fixtures";

test.describe("SpotsPage", () => {
  test("lists all spots from the API", async ({ page }) => {
    await mockApi(page);
    await page.goto("/spots");

    for (const spot of MOCK_SPOTS) {
      await expect(page.getByText(spot.name)).toBeVisible();
    }
  });
});
