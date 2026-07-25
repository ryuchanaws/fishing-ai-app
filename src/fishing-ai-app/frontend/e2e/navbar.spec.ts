import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.describe("NavBar", () => {
  test("clicking the logo returns to the top page", async ({ page }) => {
    await mockApi(page);
    await page.goto("/spots");
    await expect(page).toHaveURL("/spots");

    await page.getByText("つり羅針盤").click();

    await expect(page).toHaveURL("/");
    await expect(page.getByText("おすすめTOP3")).toBeVisible();
  });
});
