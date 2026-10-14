import { test, expect } from "@playwright/test";

test("fund rankings filter the whole batch, preserve overview, switch period and restore stock origin", async ({
  page,
}) => {
  const marketNavigation: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("neighbor_of")) marketNavigation.push(r.url());
  });
  await page.goto("/hot-sectors");
  await expect(
    page.getByRole("heading", { name: "热门板块", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".rank-panel tbody tr")).toHaveCount(20);
  await expect(
    page.getByRole("heading", { name: "测试热门概念0", exact: true }),
  ).toBeVisible();
  const overview = await page.locator(".fund-overview").textContent();
  await page
    .getByRole("textbox", { name: "搜索板块", exact: true })
    .fill("BK9000");
  await expect(page.locator(".rank-panel tbody tr")).toHaveCount(1);
  await expect(page.locator(".fund-overview")).toHaveText(overview || "");
  await page
    .getByRole("radio", { name: "5日", exact: true })
    .check({ force: true });
  await expect(page).toHaveURL(/period=5d/);
  await expect(page.locator(".summary-amount")).toContainText("5日主力净流入");
  await page
    .locator(".stock-fund-table")
    .getByRole("link", { name: "测试甲银行", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "← 返回热门板块" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "← 上一只" })).toHaveCount(0);
  expect(marketNavigation).toHaveLength(0);
  await page.getByRole("link", { name: "← 返回热门板块" }).click();
  await expect(
    page.getByRole("textbox", { name: "搜索板块", exact: true }),
  ).toHaveValue("BK9000");
  await expect(page.locator(".summary-amount")).toContainText("5日主力净流入");
});

test("mobile board detail has a deep link, returns to ranking and does not overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hot-sectors");
  await expect(page.locator(".rank-panel tbody tr")).toHaveCount(20);
  await page
    .getByRole("button", { name: "测试热门概念0", exact: true })
    .click();
  await expect(page).toHaveURL(/\/hot-sectors\/EM-concept-BK9000/);
  await expect(
    page.getByRole("heading", { name: "每日资金趋势" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("link", { name: "← 返回板块排行" }).click();
  await expect(page.locator(".rank-panel")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("direction shortcut shows only negative values and no-data states are explicit", async ({
  page,
}) => {
  await page.goto("/hot-sectors");
  await page.getByRole("button", { name: "资金流出", exact: true }).click();
  await expect(page.locator(".rank-panel tbody tr")).toHaveCount(20);
  const numbers = await page
    .locator(".rank-panel .net-value")
    .allTextContents();
  expect(numbers.every((n) => n.trim().startsWith("-"))).toBe(true);
  await page
    .getByRole("textbox", { name: "搜索板块", exact: true })
    .fill("不存在的板块");
  await expect(
    page.getByText("当前条件下没有板块", { exact: true }),
  ).toBeVisible();
});

test("silent refresh preserves rows, scroll and chart while failures keep existing data", async ({
  page,
}) => {
  await page.goto("/hot-sectors");
  await expect(page.locator(".rank-panel tbody tr")).toHaveCount(20);
  await expect(page.locator(".fund-plot canvas")).toBeVisible();
  await page.evaluate(() => {
    window.scrollTo(0, 300);
    const row = document.querySelector(".rank-panel tbody tr");
    if (row) row.setAttribute("data-retained", "yes");
  });
  const scroll = await page.evaluate(() => window.scrollY);
  await page.evaluate(() => {
    const button = [...document.querySelectorAll("button")].find(
      (b) => b.textContent?.trim() === "刷新",
    );
    button?.click();
  });
  await expect(
    page.locator('.rank-panel tbody tr[data-retained="yes"]'),
  ).toHaveCount(1);
  expect(await page.evaluate(() => window.scrollY)).toBe(scroll);
  await page.route("**/api/hot-sectors?*", (route) => route.abort());
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(page.locator(".el-alert").first()).toBeVisible();
  await expect(page.locator(".rank-panel tbody tr")).toHaveCount(20);
});

test("flow chart shows both directions from the full batch and selects a board", async ({
  page,
}) => {
  await page.route("**/api/hot-sectors?*", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    if (data.items[0])
      data.items[0].name = "汽车电子与工业智能机器人应用测试板块";
    await route.fulfill({ response, json: data });
  });
  await page.goto("/hot-sectors");
  const chart = page.getByRole("region", { name: "热门板块资金流入流出图表" });
  await expect(chart.locator(".inflow-row")).toHaveCount(5);
  await expect(chart.locator(".outflow-row")).toHaveCount(5);
  await page
    .getByRole("radio", { name: "各前10", exact: true })
    .check({ force: true });
  await expect(chart.locator(".inflow-row")).toHaveCount(10);
  await expect(chart.locator(".outflow-row")).toHaveCount(10);
  await chart
    .getByRole("button", {
      name: "净流出 测试热门概念34 -2.40 亿",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("heading", { name: "测试热门概念34", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "搜索板块", exact: true })
    .fill("BK9000");
  await expect(page.locator(".rank-panel tbody tr")).toHaveCount(1);
  await expect(chart.locator(".outflow-row")).toHaveCount(10);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
