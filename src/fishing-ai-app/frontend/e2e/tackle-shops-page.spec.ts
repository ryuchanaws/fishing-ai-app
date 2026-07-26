import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.describe("TackleShopsPage", () => {
  test("renders the page shell with nearby and keyword search controls", async ({ page }) => {
    await mockApi(page);
    await page.goto("/tackle-shops");

    await expect(page.getByText("釣具店を探す", { exact: true })).toBeVisible();
    await expect(page.getByPlaceholder("地名・県名で検索（例: 神奈川県三浦市）")).toBeVisible();
  });
});
