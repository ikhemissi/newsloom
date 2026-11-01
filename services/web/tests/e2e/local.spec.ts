import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("authored browser journey renders hostile text inertly with usable citations", async ({ page }) => {
  await page.goto("/tests/harness.html");
  await expect(page.getByRole("heading", { name: "Latest news" })).toBeVisible();
  await page.getByRole("button", { name: "Ask about this: Authored news headline" }).click();
  await page.getByLabel("What would you like to understand?").fill("Authored fixture question");
  await page.getByRole("button", { name: "Ask Newsloom" }).click();
  await expect(page.getByLabel("Research answer")).toBeVisible();
  expect(await page.locator("img").count()).toBe(0);
  await page.getByRole("button", { name: "Focus citation 1" }).focus();
  await page.keyboard.press("Enter");
  expect(await page.locator(".citations li").evaluate((element) => element === document.activeElement)).toBe(true);
  const link = page.getByLabel("Research answer").getByRole("link", { name: /publisher.test/ });
  expect(await link.getAttribute("href")).toBe("https://publisher.test/article");
  const results = await new AxeBuilder({ page }).analyze();
  if (results.violations.length)
    throw new Error(`ui_accessibility:${results.violations.map((item) => item.id).join(",")}`);
});

test("real MSAL SDK accepts the production redirect cache and constructs PKCE without network sign-in", async ({ page }) => {
  await page.route("https://login.microsoftonline.com/**", (route) => route.abort());
  await page.goto("/tests/auth-harness.html");
  await page.getByRole("button", { name: "Test redirect preflight" }).click();
  await expect(page.getByRole("status")).toHaveText("Redirect preflight passed");
});

test("default feed and top search keep the right-side agent optional", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/tests/harness.html");
  await expect(page.getByRole("heading", { name: "Authored news headline" })).toBeVisible();
  expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
  await page.getByLabel("Search stored news").fill("fixture query");
  expect(await page.locator("html").getAttribute("data-search-calls")).toBe("0");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Authored search result" })).toBeVisible();
  expect(await page.locator("html").getAttribute("data-search-calls")).toBe("1");
  expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
  await page.getByRole("button", { name: "Agent", exact: true }).click();
  const panel = page.getByRole("complementary", { name: "Agent interactions" });
  await expect(panel).toBeVisible();
  const newsBox = await page.locator(".news-column").boundingBox();
  const panelBox = await panel.boundingBox();
  expect(newsBox && panelBox && panelBox.x > newsBox.x + newsBox.width).toBeTruthy();
  expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
  await page.getByRole("button", { name: "Close agent panel" }).click();
  await expect(panel).toBeHidden();
  await expect(page.getByRole("button", { name: "Agent", exact: true })).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Agent", exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const results = await new AxeBuilder({ page }).analyze();
  if (results.violations.length)
    throw new Error(`ui_accessibility:${results.violations.map((item) => item.id).join(",")}`);
});

test("long agent replies scroll independently of the page", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/tests/harness.html?long");
  await page.getByRole("button", { name: "Agent", exact: true }).click();
  await page.getByLabel("What would you like to understand?").fill("Authored scroll fixture");
  await page.getByRole("button", { name: "Ask Newsloom" }).click();
  const panel = page.getByRole("complementary", { name: "Agent interactions" });
  await expect(page.getByLabel("Research answer")).toBeVisible();
  const bounds = await panel.boundingBox();
  expect(bounds && bounds.y + bounds.height <= 900).toBeTruthy();
  const pageScroll = await page.evaluate(() => window.scrollY);
  await panel.hover();
  await page.mouse.wheel(0, 600);
  await expect.poll(() => panel.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(pageScroll);
  await panel.focus();
  const before = await panel.evaluate((element) => element.scrollTop);
  await page.keyboard.press("PageDown");
  await expect.poll(() => panel.evaluate((element) => element.scrollTop)).toBeGreaterThan(before);
});
