import { test, expect } from "@playwright/test";
test("search, graph, company evidence and return from stock", async ({
  page,
}) => {
  await page.goto("/industry-chains");
  await page.getByRole("textbox", { name: "搜索产业链" }).fill("新能源");
  await page.getByRole("link", { name: /测试动力电池/ }).click();
  await expect(page).not.toHaveURL(/revision=/);
  await page
    .locator(".node-list button")
    .filter({ hasText: "电芯制造" })
    .click();
  await expect(
    page.getByRole("heading", { name: "电芯制造 · 相关公司" }),
  ).toBeVisible();
  await expect(page.locator(".stock-identity a").first()).toBeVisible();
  await page.locator(".stock-identity a").first().click();
  await expect(
    page.getByRole("link", { name: "← 返回产业链分析" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "← 上一只" })).toHaveCount(0);
  await page.getByRole("link", { name: "← 返回产业链分析" }).click();
  await expect(page).toHaveURL(/node=cell/);
  await expect(page.locator(".node-detail h2")).toHaveText("电芯制造");
});
test("same node compare, saved chain and node, sources", async ({ page }) => {
  await page.goto("/industry-chains/fixture-chain?node=cell");
  await expect(page.locator(".stock-identity a")).toHaveCount(2);
  await page.getByRole("button", { name: "☆ 收藏产业链" }).click();
  await page.getByRole("button", { name: "☆ 收藏节点" }).click();
  await expect(page.locator(".saved-bar")).toContainText("电芯制造");
  await page.getByRole("checkbox", { name: "比较测试甲银行" }).check();
  await page.getByRole("checkbox", { name: "比较测试乙银行" }).check();
  await page.getByRole("button", { name: "比较公司 (2)" }).click();
  await expect(page).toHaveURL(/\/compare/);
  await expect(page.locator(".compare-grid article")).toHaveCount(2);
  await expect(page.locator(".compare .note")).toContainText("不进行财务排名");
  await page.getByRole("link", { name: "← 返回产业链分析" }).click();
  await expect(page.locator(".saved-bar")).toContainText("测试动力电池");
  await page.reload();
  await expect(
    page.getByRole("button", { name: "★ 已收藏产业链" }),
  ).toBeVisible();
});
test("full graph, relationship explanation, empty and failed searches", async ({
  page,
}) => {
  await page.goto("/industry-chains/fixture-chain");
  await page.getByRole("button", { name: "展开完整图" }).click();
  await expect(page.locator(".node-list")).toContainText("电池回收");
  await page.locator(".relations summary").click();
  await page.locator(".relations button").first().click();
  await expect(
    page.getByRole("heading", { name: "影响如何传导" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "返回节点" }).click();
  await page.getByRole("textbox", { name: "搜索产业链" }).fill("不存在的行业");
  await expect(page.locator(".chain-search")).toContainText("该行业尚未收录");
});
test("narrow layout, keyboard nodes, quote refresh and saved state", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/industry-chains/fixture-chain?node=cell&view=full");
  await expect(
    page.locator(".node-list button").filter({ hasText: "电芯制造" }),
  ).toBeVisible();
  await page
    .locator(".node-list button")
    .filter({ hasText: "电芯制造" })
    .focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".node-detail h2")).toHaveText("电芯制造");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "/private/tmp/industry-chain-mobile.png",
    fullPage: true,
  });
});
test("late response cannot overwrite another node and failures stay readable", async ({
  page,
}) => {
  await page.goto("/industry-chains/fixture-chain?node=cell");
  await expect(page.locator(".stock-identity a")).toHaveCount(2);
  await page.route("**/api/industry-chains/fixture-chain/stocks*", (route) =>
    route.fulfill({ status: 503, json: { detail: "测试来源读取失败" } }),
  );
  await page
    .locator(".node-list button")
    .filter({ hasText: "正极材料" })
    .click();
  await expect(page.locator(".stock-section")).toContainText(
    "测试来源读取失败",
  );
  await expect(page.locator(".stock-identity a")).toHaveCount(0);
  await expect(page.locator(".node-detail h2")).toHaveText("正极材料");
});
test("node selection and stock return retain page scroll", async ({ page }) => {
  await page.goto("/industry-chains/fixture-chain?node=cell");
  await expect(page.locator(".stock-identity a")).toHaveCount(2);
  await page.evaluate(() => window.scrollTo(0, 500));
  await page
    .locator(".node-list button")
    .filter({ hasText: "电池系统集成" })
    .click();
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(100);
  await page
    .locator(".node-list button")
    .filter({ hasText: "电芯制造" })
    .click();
  await expect(page.locator(".stock-identity a")).toHaveCount(2);
  await page.locator(".stock-identity a").first().click();
  await page.getByRole("link", { name: "← 返回产业链分析" }).click();
  await expect(page.locator(".stock-identity a")).toHaveCount(2);
  await expect
    .poll(() => page.evaluate(() => window.scrollY))
    .toBeGreaterThan(100);
});

test("industry baseline exposes candidate status, coverage directory and review filter", async ({
  page,
}) => {
  await page.goto("/industry-chains?search=医疗器械");
  await expect(page.locator(".chain-choices")).toContainText("测试医疗器械");
  await expect(page.locator(".chain-choices")).toContainText("行业基线");
  await page
    .locator(".chain-choices a")
    .filter({ hasText: "测试医疗器械" })
    .click();
  await expect(page.locator(".chain-overview")).toContainText("行业经营逻辑");
  await expect(page.getByLabel("经营阶段")).toHaveValue("全部");
  await expect(page.locator(".stock-identity a")).toHaveCount(2);
  await expect(page.locator(".business").first()).toContainText("业务词匹配");
  await page.getByLabel("业务关联状态").selectOption("资料核验");
  await expect(page.locator(".stock-identity a")).toHaveCount(0);
  await page.getByLabel("业务关联状态").selectOption("业务词匹配");
  await expect(page.locator(".stock-identity a")).toHaveCount(2);
  await page.locator(".directory > summary").click();
  await expect(page.locator(".coverage-groups")).toContainText("电子");
});

test("search for another industry hides the previous analysis and baseline works on narrow screens", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/industry-chains/fixture-chain?search=医疗器械");
  await expect(page.locator(".chain-choices")).toContainText("测试医疗器械");
  await expect(page.locator(".analysis-body")).toHaveCount(0);
  await expect(page.locator(".message")).toContainText(
    "搜索结果与当前正文范围不同",
  );
  await page
    .locator(".chain-choices a")
    .filter({ hasText: "测试医疗器械" })
    .click();
  await expect(page.locator(".node-list")).toContainText("诊断产品");
  await expect(page.locator(".analysis-body")).toBeVisible();
  const sizes = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    width: window.innerWidth,
  }));
  expect(sizes.content).toBeLessThanOrEqual(sizes.width);
});

test("company analysis explains the association and avoids confusing financial ratios", async ({
  page,
}) => {
  await page.goto("/industry-chains/fixture-medical");
  await expect(page.locator(".stock-identity a")).toHaveCount(2);
  await page.locator(".company-analysis summary").first().click();
  await expect(page.locator(".company-analysis").first()).toContainText(
    "需核对实际产品",
  );
  await expect(page.locator(".company-analysis").first()).toContainText(
    "不能把收入占比当成市场份额",
  );
});

test("automatic latest analysis switches consistently and preserves view state", async ({
  page,
}) => {
  const original = await (
    await page.request.get("/api/industry-chains/fixture-chain")
  ).json();
  const updated = {
    ...original,
    revision_id: "auto-update-fixture",
    current_revision_id: "auto-update-fixture",
    summary: "自动更新后的行业分析",
  };
  let switched = false;
  const stockRevisions: string[] = [];
  await page.route("**/api/industry-chains/fixture-chain/version", (route) =>
    route.fulfill({
      json: {
        revision_id: switched ? updated.revision_id : original.revision_id,
      },
    }),
  );
  await page.route(/\/api\/industry-chains\/fixture-chain(?:\?|$)/, (route) => {
    const revision = new URL(route.request().url()).searchParams.get(
      "revision",
    );
    return route.fulfill({ json: switched && !revision ? updated : original });
  });
  await page.route(
    "**/api/industry-chains/fixture-chain/stocks*",
    async (route) => {
      const url = new URL(route.request().url());
      const revision = url.searchParams.get("revision")!;
      stockRevisions.push(revision);
      url.searchParams.set("revision", original.revision_id);
      const response = await route.fetch({ url: url.toString() });
      return route.fulfill({
        json: { ...(await response.json()), revision_id: revision },
      });
    },
  );
  await page.goto(
    "/industry-chains/fixture-chain?node=cell&view=full&sort=market_cap_desc&page_size=50&page=1",
  );
  await expect(page.locator(".stock-identity a")).toHaveCount(2);
  await expect(page.getByText("自动跟随最新分析。")).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 450));
  const top = await page.evaluate(() => window.scrollY);
  switched = true;
  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  await expect(page.locator(".chain-overview .summary")).toHaveText(
    updated.summary,
  );
  await expect.poll(() => stockRevisions.at(-1)).toBe(updated.revision_id);
  await expect(page).not.toHaveURL(/revision=/);
  for (const param of [
    "node=cell",
    "view=full",
    "sort=market_cap_desc",
    "page_size=50",
    "page=1",
  ])
    expect(page.url()).toContain(param);
  expect(await page.evaluate(() => window.scrollY)).toBe(top);
});

test("explicit history stays fixed until following latest is selected", async ({
  page,
}) => {
  const original = await (
    await page.request.get("/api/industry-chains/fixture-chain")
  ).json();
  const updated = {
    ...original,
    revision_id: "history-new-fixture",
    current_revision_id: "history-new-fixture",
    summary: "新版正文",
  };
  let switched = false;
  await page.route("**/api/industry-chains/fixture-chain/version", (route) =>
    route.fulfill({
      json: {
        revision_id: switched ? updated.revision_id : original.revision_id,
      },
    }),
  );
  await page.route(/\/api\/industry-chains\/fixture-chain(?:\?|$)/, (route) => {
    const pinned = new URL(route.request().url()).searchParams.has("revision");
    return route.fulfill({ json: switched && !pinned ? updated : original });
  });
  await page.goto(
    "/industry-chains/fixture-chain?node=cell&revision=" + original.revision_id,
  );
  await expect(page.getByText("当前分析版本已固定。")).toBeVisible();
  switched = true;
  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  await expect(page.getByText("当前正在阅读旧版本。")).toBeVisible();
  await expect(page.locator(".chain-overview .summary")).toHaveText(
    original.summary,
  );
  await expect(page).toHaveURL(/revision=/);
  await page.getByRole("button", { name: "跟随最新分析" }).click();
  await expect(page.locator(".chain-overview .summary")).toHaveText(
    updated.summary,
  );
  await expect(page).not.toHaveURL(/revision=/);
});

test("update failure is visible without hiding usable analysis on narrow screen", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/industry-chains/update-status", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        interval_hours: 24,
        state: "failed",
        phase: "collecting",
        error: "测试：数据源暂不可用",
        last_success_at: "2026-10-13T08:00:00Z",
        next_check_at: "2026-10-14T08:00:00Z",
        logic_reviewed_on: "2026-10-14",
        logic_review_due_on: "2027-01-12",
        logic_review_overdue: false,
        maintenance: { leader_review_count: 12, source_review_count: 3 },
      },
    }),
  );
  await page.goto("/industry-chains/fixture-chain?node=cell");
  await expect(page.locator(".update-status")).toContainText(
    "更新失败，保留上一份可用分析",
  );
  await page.locator(".update-status summary").click();
  await expect(page.locator(".update-status")).toContainText("数据源暂不可用");
  await expect(page.locator(".stock-identity a")).toHaveCount(2);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
