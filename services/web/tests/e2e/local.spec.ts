import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { briefingResponse } from "../fixtures";

test.describe("daily shared briefing", () => {
  test.use({ timezoneId: "Asia/Kathmandu", locale: "fr-FR" });
  for (const width of [1440, 390]) {
    test(`HTTP-backed ${width}px briefing is complete, inert, keyboard accessible and independent of research`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.clock.install({ time: new Date("2026-11-02T12:00:00Z") });
      let reads = 0;
      await page.route("https://mcp.test/api/v1/briefing", async (route) => {
        reads++;
        expect(route.request().method()).toBe("GET");
        expect(route.request().headers()["authorization"]).toBe("Bearer authored-briefing-token");
        await route.fulfill({ json: briefingResponse });
      });
      await page.goto("/tests/harness.html?http-briefing");
      expect(reads).toBe(0);
      await page.getByRole("button", { name: "Ask about this: Authored news headline" }).click();
      const panel = page.getByRole("complementary");
      const region = page.getByRole("region", { name: "Daily news briefing" });
      await expect(region.getByText(/Authored weekly overview/)).toBeVisible();
      expect(reads).toBe(1);
      const order = await panel.evaluate((element) => [...element.children].map((child) =>
        child.getAttribute("aria-label") ?? child.className));
      expect(order[0]).toBe("panel-heading");
      expect(order[1]).toBe("Daily news briefing");
      expect(order[2]).toBe("notice");
      await expect(region.locator("time[datetime='2026-11-02T05:10:00+00:00']")).toContainText("10:55:00");
      await expect(region.locator("time[datetime='2026-11-02T05:10:00+00:00']")).toContainText("UTC+5:45");
      const details = region.locator("details");
      await expect(details).not.toHaveAttribute("open");
      const question = page.getByLabel("What would you like to understand?");
      await question.fill("Keep the authored draft");
      const summary = details.locator("summary");
      await summary.focus(); await page.keyboard.press("Enter");
      await expect(details).toHaveAttribute("open", "");
      await expect(region.getByRole("heading", { name: "Authored weekly theme 10" })).toHaveCount(1);
      expect(await details.locator("section p").count()).toBe(10);
      const fullText = await details.locator("section p").allTextContents();
      expect(fullText.join(" ").replace(/\[1\]/g, "").trim().split(/\s+/).length).toBe(990);
      expect(await region.locator("img, svg, script").count()).toBe(0);
      const citationButton = region.getByRole("button", { name: "Focus briefing citation 1" }).first();
      await citationButton.focus(); await page.keyboard.press("Enter");
      await expect(details.locator("li")).toBeFocused();
      const source = details.getByRole("link");
      await expect(source).toHaveAttribute("href", "https://publisher.test/briefing");
      await expect(source).toHaveAttribute("rel", "noopener noreferrer");
      await summary.focus(); await page.keyboard.press("Space");
      await expect(details).not.toHaveAttribute("open");
      await expect(question).toHaveValue("Keep the authored draft");
      expect(reads).toBe(1);
      expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
      await summary.focus(); await page.keyboard.press("Enter");
      await panel.evaluate((element) => { element.scrollTop = 300; });
      const pageScroll = await page.evaluate(() => window.scrollY);
      const panelScroll = await panel.evaluate((element) => element.scrollTop);
      expect(panelScroll).toBeGreaterThan(0);
      await page.clock.fastForward(60_000);
      await expect.poll(() => reads).toBe(2);
      await expect(details).toHaveAttribute("open", "");
      expect(await panel.evaluate((element) => element.scrollTop)).toBe(panelScroll);
      expect(await page.evaluate(() => window.scrollY)).toBe(pageScroll);
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations.map((violation) => violation.id)).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.getByRole("button", { name: "Close agent panel" }).click();
      await page.getByRole("button", { name: "Agent", exact: true }).click();
      await expect(details).toHaveAttribute("open", "");
      await expect(question).toHaveValue("Keep the authored draft");
      expect(reads).toBe(2);
      await page.getByLabel("Category", { exact: true }).selectOption("agents-applications");
      await page.getByRole("button", { name: "Apply filters" }).click();
      await expect(page.getByRole("heading", { name: "Authored search result" })).toBeVisible();
      await expect(page.getByText("Current news: Authored news headline")).toBeAttached();
      expect(reads).toBe(2);
      expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
    });
  }

  test("version/status updates collapse only new versions and errors leave research usable", async ({ page }) => {
    await page.clock.install({ time: new Date("2026-11-02T12:00:00Z") });
    await page.goto("/tests/harness.html?briefing-version&briefing-stale");
    await page.getByRole("button", { name: "Agent", exact: true }).click();
    const region = page.getByRole("region", { name: "Daily news briefing" });
    await expect(region.getByText(/Daily refresh: running/)).toContainText("Stale");
    const details = region.locator("details");
    await details.locator("summary").click();
    await page.clock.fastForward(60_000);
    await expect(region.getByText(/Daily refresh: failed/)).toBeAttached();
    await expect(details).toHaveAttribute("open", "");
    await page.clock.fastForward(60_000);
    await expect(region.getByText("Authored updated weekly overview.")).toBeAttached();
    await expect(details).not.toHaveAttribute("open");
    expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");

    await page.goto("/tests/harness.html?briefing-error");
    await page.getByRole("button", { name: "Agent", exact: true }).click();
    await expect(region.getByRole("alert")).toContainText("Briefing read failed");
    await page.getByLabel("What would you like to understand?").fill("Independent research through a failed read");
    await page.getByRole("button", { name: "Ask Newsloom", exact: true }).click();
    await expect(page.getByLabel("Research answer")).toBeVisible();
    await region.getByRole("button", { name: "Retry briefing" }).click();
    expect(await page.locator("html").getAttribute("data-briefing-calls")).toBe("1");
    await page.clock.fastForward(60_000);
    await expect(region.getByText(/Authored weekly overview/)).toBeAttached();
    await expect(page.getByLabel("Research answer")).toBeAttached();
    expect(await page.locator("html").getAttribute("data-research-calls")).toBe("1");
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
    await page.goto("/tests/harness.html?briefing-pending");
    await page.getByRole("button", { name: "Agent", exact: true }).click();
    await expect(region.getByText(/No published briefing is available yet/)).toBeAttached();
    await expect(region.locator("details")).toHaveCount(0);
    await page.goto("/tests/harness.html?briefing-empty");
    await page.getByRole("button", { name: "Agent", exact: true }).click();
    await expect(region.getByText(/No stored news was available/)).toBeAttached();
    await expect(region.locator("details")).toHaveCount(0);
    expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
  });
});

for (const [zone, localDate, localTime, offset] of [
  ["Europe/Paris", "03/11/2026", "01:00:00", "UTC+1"],
  ["America/New_York", "02/11/2026", "19:00:00", "UTC\u22125"],
  ["Asia/Kathmandu", "03/11/2026", "05:45:00", "UTC+5:45"],
] as const) {
  test.describe(`browser-local timestamps in ${zone}`, () => {
    test.use({ timezoneId: zone, locale: "fr-FR", viewport: { width: 1440, height: 900 } });
    test("cards, details and metadata preserve instants, offsets and display-only clock updates", async ({ page }) => {
      await page.clock.install({ time: new Date("2026-11-02T23:59:30Z") });
      await page.goto("/tests/harness.html?future-date");
      const card = page.getByRole("article");
      const time = card.locator("time");
      await expect(time).toHaveAttribute("datetime", "2026-11-03T00:00:00Z");
      await expect(time).toContainText(localDate);
      await expect(time).toContainText(localTime);
      await expect(time).toContainText(offset);
      await expect(card.locator(".future-date")).toBeVisible();
      await expect(card.locator(".future-date")).toContainText("Future-dated");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const metadata = page.getByRole("region", { name: "Browse continuation" });
      await expect(metadata.locator("time")).toHaveAttribute("datetime", "2026-11-01T08:00:00Z");
      await expect(metadata.locator("time")).toContainText(offset);
      await expect(metadata.locator(".future-date")).toHaveCount(0);
      await page.setViewportSize({ width: 390, height: 844 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const results = await new AxeBuilder({ page }).analyze();
      if (results.violations.length)
        throw new Error(`ui_accessibility:${results.violations.map((item) => item.id).join(",")}`);
      await page.clock.fastForward(60_000);
      await expect(card.locator(".future-date")).toHaveCount(0);
      await expect(time).toHaveAttribute("datetime", "2026-11-03T00:00:00Z");
      for (const [name, count] of [["recentCalls", "1"], ["sourceCalls", "1"], ["searchCalls", "0"], ["researchCalls", "0"]] as const)
        expect(await page.locator("html").getAttribute(`data-${name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`)).toBe(count);
      await page.getByRole("link", { name: "Authored news headline", exact: true }).click();
      const detail = page.getByRole("region", { name: "News detail" });
      await expect(detail.locator("time")).toHaveAttribute("datetime", "2026-11-03T00:00:00Z");
      await expect(detail.locator("time")).toContainText(localDate);
      await expect(detail.locator("time")).toContainText(localTime);
      await expect(detail.locator("time")).toContainText(offset);
      await expect(detail.locator(".future-date")).toHaveCount(0);
    });
  });
}

test.describe("runtime timezone changes", () => {
  test.use({ locale: "fr-FR" });
  test("minute and focus refresh the zone without changing instants or sending requests", async ({ page, context }) => {
    const session = await context.newCDPSession(page);
    await session.send("Emulation.setTimezoneOverride", { timezoneId: "Europe/Paris" });
    await page.clock.install({ time: new Date("2026-11-02T23:59:30Z") });
    await page.goto("/tests/harness.html?future-date");
    const time = page.getByRole("article").locator("time");
    await expect(time).toContainText("03/11/2026");
    await expect(time).toContainText("UTC+1");
    await session.send("Emulation.setTimezoneOverride", { timezoneId: "" });
    await session.send("Emulation.setTimezoneOverride", { timezoneId: "America/New_York" });
    await page.clock.fastForward(60_000);
    await expect(time).toContainText("02/11/2026");
    await expect(time).toContainText("19:00:00");
    await expect(time).toContainText("UTC\u22125");
    await page.clock.setFixedTime(new Date("2026-11-03T00:02:00Z"));
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await session.send("Emulation.setTimezoneOverride", { timezoneId: "" });
    await session.send("Emulation.setTimezoneOverride", { timezoneId: "Europe/Paris" });
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(time).toContainText("03/11/2026");
    await expect(time).toContainText("UTC+1");
    await expect(time).toHaveAttribute("datetime", "2026-11-03T00:00:00Z");
    expect(await page.locator("html").getAttribute("data-recent-calls")).toBe("1");
    expect(await page.locator("html").getAttribute("data-source-calls")).toBe("1");
    expect(await page.locator("html").getAttribute("data-search-calls")).toBe("0");
    expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
  });
});

test("authored browser journey renders hostile text inertly with usable citations", async ({ page }) => {
  await page.goto("/tests/harness.html");
  await expect(page.getByRole("heading", { name: "Latest news" })).toHaveClass("sr-only");
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

test("compact toolbar removes the hero gap and aligns Refresh with filters without mobile clipping", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/tests/harness.html");
  const toolbar = page.getByRole("form", { name: "News filters" });
  const refresh = toolbar.getByRole("button", { name: "Refresh", exact: true });
  await expect(refresh).toBeEnabled();
  await expect(page.getByText("STORED NEWS. CLEARER CONTEXT.", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Stored articles, newest first. Initially showing up to 20.", { exact: true })).toHaveCount(0);
  await expect(page.locator(".news-heading")).toHaveCount(0);
  const heading = page.getByRole("heading", { name: "Latest news", exact: true });
  const headingBox = await heading.boundingBox();
  expect(headingBox).not.toBeNull();
  expect(headingBox!.height).toBeLessThanOrEqual(1);
  expect(headingBox!.width).toBeLessThanOrEqual(1);
  expect(await heading.evaluate((element) => getComputedStyle(element).position)).toBe("absolute");
  const columnBox = await page.locator(".news-column").boundingBox();
  const toolbarBox = await toolbar.boundingBox();
  expect(columnBox && toolbarBox && Math.abs(columnBox.y - toolbarBox.y) <= 1).toBeTruthy();
  const sourceBox = await toolbar.getByLabel("Source", { exact: true }).boundingBox();
  for (const name of ["Apply filters", "Reset filters", "Refresh"]) {
    const box = await toolbar.getByRole("button", { name, exact: true }).boundingBox();
    expect(box && sourceBox && Math.abs(box.y + box.height - sourceBox.y - sourceBox.height) <= 1).toBeTruthy();
  }
  await refresh.focus();
  await page.keyboard.press("Enter");
  expect(await page.locator("html").getAttribute("data-search-calls")).toBe("0");
  expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
  await page.getByLabel("Search stored news").fill("fixture query");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.locator(".news-search-context")).toHaveText('Ranked by relevance · Up to 20 results for "fixture query"');
  await expect(toolbar.getByRole("button", { name: "Clear search", exact: true })).toBeEnabled();
  await expect(refresh).toHaveCount(0);
  await toolbar.getByRole("button", { name: "Clear search", exact: true }).click();
  await expect(page.locator(".news-search-context")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await toolbar.getByLabel("Date period").selectOption("custom");
  expect(await toolbar.locator("select, input, button").evaluateAll((elements) => elements.every((element) => {
    const bounds = element.getBoundingClientRect();
    return bounds.left >= 0 && bounds.right <= window.innerWidth;
  }))).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const mobileRefresh = await refresh.boundingBox();
  const mobileSource = await toolbar.getByLabel("Source", { exact: true }).boundingBox();
  expect(mobileRefresh && mobileSource && mobileRefresh.y > mobileSource.y).toBeTruthy();
  const results = await new AxeBuilder({ page }).analyze();
  if (results.violations.length)
    throw new Error(`ui_accessibility:${results.violations.map((item) => item.id).join(",")}`);
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

test("keyboard filter/search/reset journey preserves submitted research context and responsive accessibility", async ({ page }) => {
  await page.goto("/tests/harness.html");
  await page.getByLabel("Source").selectOption("fixture-source");
  await page.getByLabel("Category").selectOption("agents-applications");
  await page.getByLabel("Date period").selectOption("custom");
  await page.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("valid, complete dates");
  await page.getByLabel("Start date").fill("2026-11-01");
  await page.getByLabel("End date").fill("2026-11-01");
  expect(await page.locator("html").getAttribute("data-search-calls")).toBe("0");
  await page.getByRole("button", { name: "Apply filters", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Filtered news" })).toHaveClass("sr-only");
  expect(await page.locator("html").getAttribute("data-queryless-calls")).toBe("1");
  expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
  await page.getByLabel("Search stored news").fill("fixture query");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Search results", exact: true })).toHaveClass("sr-only");
  expect(await page.locator("html").getAttribute("data-queryless-calls")).toBe("1");
  await page.getByRole("button", { name: "Ask about this: Authored search result" }).click();
  await page.getByLabel("What would you like to understand?").fill("Independent authored question");
  await page.getByRole("button", { name: "Ask Newsloom", exact: true }).click();
  await expect(page.getByLabel("Research answer")).toBeVisible();
  const submitted = page.getByLabel("Submitted research context");
  await expect(submitted).toContainText("Category: Agents and applications");
  await page.getByLabel("Category", { exact: true }).selectOption("models");
  await page.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect(page.getByText("No news matches this search.")).toBeVisible();
  await expect(submitted).toContainText("Category: Agents and applications");
  await expect(page.getByLabel("Next research filters")).toContainText("Category: Models");
  await page.getByRole("button", { name: "Reset filters", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Search results", exact: true })).toHaveClass("sr-only");
  await page.getByRole("button", { name: "Clear search", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Latest news", exact: true })).toHaveClass("sr-only");
  await expect(page.getByLabel("Research answer")).toBeVisible();
  expect(await page.locator("html").getAttribute("data-research-calls")).toBe("1");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const results = await new AxeBuilder({ page }).analyze();
  if (results.violations.length)
    throw new Error(`ui_accessibility:${results.violations.map((item) => item.id).join(",")}`);
});

test("catalogue failure is retryable and hostile category labels stay inert", async ({ page }) => {
  await page.goto("/tests/harness.html?catalogue-error&hostile-catalogue");
  await expect(page.getByRole("alert")).toContainText("Source/category choices unavailable");
  await expect(page.getByLabel("Source")).toBeDisabled();
  await page.getByRole("button", { name: "Retry catalogue" }).click();
  await expect(page.getByLabel("Source")).toBeEnabled();
  await page.getByLabel("Category").selectOption("agents-applications");
  await page.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect(page.getByLabel("Applied news filters")).toContainText("<svg onload=bad()>");
  expect(await page.locator("svg").count()).toBe(0);
  expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign in to read news", exact: true })).toBeVisible();
  await expect(page.getByLabel("Applied news filters")).toHaveCount(0);
});

test("explicit paging reaches its 200-item cap without research and can restart", async ({ page }) => {
  await page.goto("/tests/harness.html?paged");
  await expect(page.getByText("20 stored items displayed.")).toBeVisible();
  for (let count = 40; count <= 200; count += 20) {
    await page.getByRole("button", { name: "Load more", exact: true }).click();
    await expect(page.getByText(`${count} stored items displayed.`)).toBeVisible();
  }
  await expect(page.getByRole("button", { name: "Load more", exact: true })).toHaveCount(0);
  await expect(page.getByText("Display limit reached: 200 items. More news may exist.")).toBeVisible();
  expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
  await page.getByRole("button", { name: "Restart browsing" }).click();
  await expect(page.getByText("20 stored items displayed.")).toBeVisible();
});

test("shareable detail routes reload, support browser history and retain accessible A2A context", async ({ page }) => {
  await page.route("**/news/*", async (route) => {
    const response = await route.fetch({ url: new URL("/tests/harness.html", route.request().url()).href });
    await route.fulfill({ response });
  });
  await page.goto("/tests/harness.html");
  await page.getByRole("link", { name: "Authored news headline", exact: true }).click();
  const detail = page.getByRole("region", { name: "News detail" });
  await expect(detail.getByText("Authored publisher", { exact: true })).toBeVisible();
  await expect(detail.getByRole("heading", { name: "Authored news headline", exact: true })).toBeVisible();
  expect(new URL(page.url()).pathname).toMatch(/^\/news\/[a-f0-9-]+$/);
  expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
  await page.getByRole("button", { name: "Back to news", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Latest news", exact: true })).toHaveClass("sr-only");
  await expect(page.getByRole("link", { name: "Authored news headline", exact: true })).toBeFocused();
  await page.goForward();
  await expect(detail).toBeVisible();
  await page.reload();
  await expect(detail.getByText("Authored publisher", { exact: true })).toBeVisible();
  await detail.getByRole("button", { name: "Ask about this: Authored news headline", exact: true }).click();
  await expect(page.getByLabel("What would you like to understand?")).toBeFocused();
  expect(await page.locator("html").getAttribute("data-research-calls")).toBe("0");
  await page.getByLabel("What would you like to understand?").fill("Independent detail question");
  await page.getByRole("button", { name: "Ask Newsloom", exact: true }).click();
  await expect(page.getByLabel("Submitted research context")).toContainText("Submitted news: Authored news headline");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const results = await new AxeBuilder({ page }).analyze();
  if (results.violations.length)
    throw new Error(`ui_accessibility:${results.violations.map((item) => item.id).join(",")}`);
});
