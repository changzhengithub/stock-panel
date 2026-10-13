import { test, expect } from "@playwright/test";
let browserErrors: string[] = [];
test.beforeEach(async ({ page }) => {
  browserErrors = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
});
test.afterEach(() => {
  expect(browserErrors).toEqual([]);
});

test("概念板块沿用股票表，并在窄屏提供选择入口", async ({ page }) => {
  await page.goto("/market");
  await page.getByRole("button", { name: "概念", exact: true }).click();
  await page
    .getByRole("navigation", { name: "概念板块" })
    .getByRole("button", { name: /固态电池/ })
    .click();
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(2);
  await expect(
    page.getByRole("heading", { name: /固态电池 · 全部股票/ }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "龙头股" })).toHaveCount(0);
  await expect(page).toHaveURL(/concept_id=BK1234/);
  await page.screenshot({
    path: "test-results/concept-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".mobile-classification-switch")).toBeVisible();
  await expect(page.locator(".industry-dropdown")).toBeVisible();
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(2);
  await page.screenshot({
    path: "test-results/concept-mobile.png",
    fullPage: true,
  });
});

test("默认只展示精选概念，搜索可找到其他概念", async ({ page }) => {
  await page.goto("/market?view=concept");
  const concepts = page.getByRole("navigation", { name: "概念板块" });
  await expect(
    concepts.getByRole("button", { name: /固态电池/ }),
  ).toBeVisible();
  await expect(concepts.getByRole("button", { name: /养老概念/ })).toHaveCount(
    0,
  );
  await expect(page.getByRole("button", { name: /查看全部/ })).toHaveCount(0);

  await page.getByRole("textbox", { name: "查找概念" }).fill("养老");
  await concepts.getByRole("button", { name: /养老概念/ }).click();
  await expect(page).toHaveURL(/concept_id=BK5678/);
  await page.getByRole("textbox", { name: "查找概念" }).clear();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/market?view=concept");
  const dropdown = page.getByRole("combobox", { name: "概念" });
  await dropdown.click();
  await expect(page.getByRole("option", { name: /固态电池/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /养老概念/ })).toHaveCount(0);
  await dropdown.fill("养老");
  await expect(page.getByRole("option", { name: /养老概念/ })).toBeVisible();
});

test("权重筛选共用股票列表、详情与价格区间", async ({ page }) => {
  await page.goto("/market?scope=representatives");
  await expect(
    page.getByRole("heading", { name: "市场浏览", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(3);
  await expect(page.getByRole("button", { name: "龙头股" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.locator(".sort-options button")).toHaveText([
    "默认",
    "龙头股",
    "涨跌幅降序",
    "涨跌幅升序",
    "总市值",
  ]);
  const searchBox = await page.locator(".search-field").boundingBox();
  const defaultBox = await page
    .getByRole("button", { name: "默认", exact: true })
    .boundingBox();
  expect(searchBox!.x + searchBox!.width).toBeLessThan(defaultBox!.x);
  expect(
    Math.abs(
      searchBox!.y +
        searchBox!.height / 2 -
        (defaultBox!.y + defaultBox!.height / 2),
    ),
  ).toBeLessThan(3);
  const pagination = await page.locator(".pagination-bar").boundingBox();
  expect(pagination!.y + pagination!.height).toBeLessThanOrEqual(1100);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollHeight <= window.innerHeight,
    ),
  ).toBe(true);
  await expect(
    page.locator(".stock-table th").filter({ hasText: "收盘价" }),
  ).toHaveCount(1);

  await page.screenshot({
    path: "test-results/market-preview.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "预览测试乙银行", exact: true })
    .click();
  await expect(
    page
      .getByRole("complementary", { name: "个股速览" })
      .getByRole("heading", { name: "测试乙银行", exact: true }),
  ).toBeVisible();
  const preview = page.getByRole("complementary", { name: "个股速览" });
  await preview.getByRole("button", { name: "周 K" }).click();
  await expect(preview.getByText("近一年 · 前复权周 K")).toBeVisible();
  await preview.getByRole("button", { name: "月 K" }).click();
  await expect(preview.getByText("近五年 · 前复权月 K")).toBeVisible();
  await expect(page).toHaveURL(/market/);
  await page.getByRole("button", { name: /^测试甲银行/ }).click();
  await expect(
    page.getByRole("heading", { name: "测试甲银行", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("用于验证浏览流程的隔离数据")).toBeVisible();
  const basics = page.getByRole("region", { name: "股票基础数据" });
  await expect(basics.getByText("流通市值")).toBeVisible();
  await expect(basics.getByText("65.43 亿")).toBeVisible();
  await expect(
    basics.locator("dt").filter({ hasText: "市盈率" }),
  ).toBeVisible();
  await expect(basics.getByText("TTM")).toBeVisible();
  await expect(page.locator(".candlestick-chart canvas")).toBeVisible();
  await expect(
    page.getByRole("img", { name: /前复权历史日 K 线、价格均线和副图指标/ }),
  ).toBeVisible();
  await expect(page.getByLabel("价格均线").getByText("MA5 —")).toBeVisible();
  await expect(page.getByLabel("价格均线").getByText("MA60 —")).toBeVisible();
  await expect(page.getByText("VOL MA5 —")).toBeVisible();
  await expect(page.getByRole("button", { name: "MACD" })).toBeVisible();
  await page.getByText("周 K", { exact: true }).click();
  await expect(page.getByRole("heading", { name: /周 K 线/ })).toBeVisible();
  await expect(
    page.getByRole("img", { name: /前复权历史周 K 线/ }),
  ).toBeVisible();
  await page.getByText("月 K", { exact: true }).click();
  await expect(page.getByRole("heading", { name: /月 K 线/ })).toBeVisible();
  await expect(page.getByRole("radio", { name: "近五年" })).toBeChecked();
  await expect(page.getByText(/周 K 至少请求五年/)).toBeVisible();
  await page.getByText("日 K", { exact: true }).click();
  await expect(page.getByRole("button", { name: "RSI" })).toBeDisabled();
  await page.getByRole("button", { name: "成交量" }).click();
  await page.getByText("近一年", { exact: true }).click();
  await expect(
    page.getByRole("radio", { name: "近一年", exact: true }),
  ).toBeChecked();
  await page.getByRole("link", { name: "← 返回市场浏览" }).click();
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(3);
});

test("个股速览可拖拽调整宽度并保留最小宽度", async ({ page }) => {
  await page.goto("/market");
  const handle = page.getByRole("separator", { name: "调整个股速览宽度" });
  const preview = page.getByRole("complementary", { name: "个股速览" });
  await expect(handle).toBeVisible();
  const initialWidth = (await preview.boundingBox())!.width;
  const box = (await handle.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 80);
  await page.mouse.down();
  await page.mouse.move(box.x - 120, box.y + 80, { steps: 5 });
  await page.mouse.up();
  expect((await preview.boundingBox())!.width).toBeGreaterThan(
    initialWidth + 100,
  );

  const moved = (await handle.boundingBox())!;
  await page.mouse.move(moved.x + moved.width / 2, moved.y + 80);
  await page.mouse.down();
  await page.mouse.move(moved.x + 600, moved.y + 80, { steps: 5 });
  await page.mouse.up();
  expect((await preview.boundingBox())!.width).toBeGreaterThanOrEqual(215);
  expect((await preview.boundingBox())!.width).toBeLessThanOrEqual(216);

  await handle.focus();
  await page.keyboard.press("ArrowLeft");
  expect((await preview.boundingBox())!.width).toBeGreaterThan(215);
  await page.setViewportSize({ width: 800, height: 900 });
  await expect(handle).toBeHidden();
  await expect(preview).toBeHidden();
});

test("搜索、防抖、URL 恢复与全市场榜单分页", async ({ page }) => {
  await page.goto("/market?scope=all&sort=pct_asc&page=2&page_size=20");
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(20);
  await page.reload();
  await expect(page.locator(".el-pager .is-active")).toHaveText("2");
  await page.getByRole("textbox", { name: "股票搜索" }).fill("测试乙银行");
  await expect(page).toHaveURL(/page=1/);
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: /^测试乙银行/ }).click();
  await page.getByRole("link", { name: "← 返回市场浏览" }).click();
  await expect(page.getByRole("textbox", { name: "股票搜索" })).toHaveValue(
    "测试乙银行",
  );
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(1);
});

test("行业筛选与清空筛选", async ({ page }) => {
  await page.goto("/market?scope=all&industry_id=bank");
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(2);
  await page.getByRole("button", { name: "涨跌幅升序" }).click();
  await expect(page.locator(".stock-table tbody tr").first()).toContainText(
    "测试乙银行",
  );
  await page.getByRole("textbox", { name: "股票搜索" }).fill("不存在的公司");
  await expect(
    page.getByRole("heading", { name: "没有匹配的股票" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "清空筛选，搜索全部股票" }).click();
  await expect(page).not.toHaveURL(/industry_id/);
});

test("左侧一级展开二级、筛选及 URL 恢复", async ({ page }) => {
  await page.goto("/market?scope=all");
  const bank = page.getByRole("button", { name: "银行 2", exact: true });
  await bank.click();
  await expect(page).toHaveURL(/industry_id=bank/);
  await expect(bank).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("group", { name: "银行二级行业" })).toBeVisible();
  await bank.click();
  await expect(bank).toHaveAttribute("aria-expanded", "false");
  await expect(page).toHaveURL(/industry_id=bank/);
  await bank.click();
  await expect(bank).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(2);
  await page.getByRole("button", { name: /银行细分测试/ }).click();
  await expect(page).toHaveURL(/industry_id=bank_l2/);
  await expect(page).toHaveURL(/industry_level=2/);
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(2);
  await page.getByRole("button", { name: "龙头股" }).click();
  await expect(page).toHaveURL(/scope=representatives/);
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: /龙头股/ })).toBeVisible();
  await bank.click();
  await expect(page).toHaveURL(/industry_level=1/);
  await expect(page).toHaveURL(/scope=representatives/);
  await expect(page.getByRole("button", { name: "龙头股" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByRole("button", { name: /银行细分测试/ }).click();
  await expect(page).toHaveURL(/industry_level=2/);
  await expect(page).toHaveURL(/scope=representatives/);
  await expect(page.getByRole("button", { name: "龙头股" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByRole("button", { name: "龙头股" }).click();
  await expect(page).toHaveURL(/scope=all/);
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(2);
  await page.reload();
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: /银行细分测试/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(bank).toHaveAttribute("aria-expanded", "true");
  await bank.click();
  await expect(page).toHaveURL(/industry_id=bank/);
  await expect(page).toHaveURL(/industry_level=1/);
});

test("窄屏行业下拉切换保留权重龙头范围", async ({ page }) => {
  await page.setViewportSize({ width: 800, height: 900 });
  await page.goto(
    "/market?industry_id=bank_l2&industry_level=2&scope=representatives",
  );
  await page.getByRole("combobox", { name: "行业" }).click();
  await page.getByRole("option", { name: /电子 · 54/ }).click();
  await expect(page).toHaveURL(/industry_id=tech/);
  await expect(page).toHaveURL(/scope=representatives/);
  await expect(page.getByRole("button", { name: "龙头股" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("接口错误显示重试且恢复", async ({ page }) => {
  await page.route("**/api/stocks?**", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "测试服务暂不可用" }),
    }),
  );
  await page.goto("/market?scope=representatives");
  await expect(page.getByText("测试服务暂不可用")).toBeVisible();
  await page.unroute("**/api/stocks?**");
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(3);
});

test("直接打开详情和缺失股票", async ({ page }) => {
  await page.goto("/stocks/1");
  await expect(
    page.getByRole("heading", { name: "测试甲银行", exact: true }),
  ).toBeVisible();
  await page.goto("/stocks/99999");
  await expect(page.getByText("股票不存在").first()).toBeVisible();
});

test("无初始化数据不展示模拟行情", async ({ page }) => {
  await page.route("**/api/data-status", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        available: false,
        stock_count: 0,
        trade_date: null,
        source: "Tushare Pro",
        industry_source: "SW2021 一级行业",
        history: {
          complete: false,
          expected_days: 0,
          published_days: 0,
          missing_days: [],
        },
        last_run: null,
      }),
    }),
  );
  await page.goto("/market");
  await expect(
    page.getByRole("heading", { name: "市场数据，等待首次同步" }),
  ).toBeVisible();
  await expect(page.locator(".stock-table")).toHaveCount(0);
});

test("通过行业导航和下拉框选择上市板块", async ({ page }) => {
  await page.goto("/market?scope=all");
  await page
    .locator(".industry-nav button")
    .filter({ hasText: /^银行/ })
    .click();
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(2);
  await page.locator(".market-select:visible .el-select").click();
  await page.getByRole("option", { name: "深市主板", exact: true }).click();
  await expect(page).toHaveURL(/board=/);
  await expect(page).toHaveURL(/exchange=SZSE/);
  await expect(page.getByRole("combobox", { name: "上市板块" })).toHaveCount(0);
  await expect(page.locator(".market-select:visible")).toContainText(
    "深市主板",
  );
  await expect(
    page.getByRole("heading", { name: "深市主板 / 银行 · 全部股票" }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator(".market-select:visible")).toContainText(
    "深市主板",
  );
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(2);
  await page.screenshot({
    path: "test-results/market-unified-preview.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.locator(".market-select:visible .el-select").click();
  await expect(
    page.getByRole("option", { name: "全部沪市", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("option", { name: "创业板", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".market-select-dropdown:visible .el-select-group__title"),
  ).toHaveText(["沪市", "深市"]);
  await page.screenshot({
    path: "test-results/market-unified-dropdown.png",
    fullPage: true,
    animations: "disabled",
  });
});

test("交易所切换保留行业与龙头范围并联动上市板块", async ({ page }) => {
  await page.goto(
    "/market?industry_id=tech&scope=representatives&sort=pct_desc&board=深市主板&page=2",
  );
  const industryNavigation = page.getByRole("navigation", {
    name: "SW2021 行业分类",
  });
  await expect(industryNavigation.locator(".industry-all")).toHaveText(
    "全部行业54",
  );
  const markets = page.locator(".market-select:visible .el-select");
  await expect(page.getByRole("tablist", { name: "交易所市场" })).toHaveCount(
    0,
  );
  const selectorBox = await markets.boundingBox();
  const sidebarBox = await page.locator(".industry-sidebar").boundingBox();
  const titleBox = await page.locator(".rail-title").boundingBox();
  expect(selectorBox!.x).toBeGreaterThan(sidebarBox!.x);
  expect(selectorBox!.x + selectorBox!.width).toBeLessThanOrEqual(
    sidebarBox!.x + sidebarBox!.width,
  );
  expect(selectorBox!.y + selectorBox!.height).toBeLessThanOrEqual(titleBox!.y);
  await markets.click();
  await page.getByRole("option", { name: "全部沪市", exact: true }).click();
  await expect(page).toHaveURL(/exchange=SSE/);
  await expect(industryNavigation.locator(".industry-all")).toHaveText(
    "全部行业1",
  );
  await expect(
    industryNavigation.getByRole("button", { name: "银行 0", exact: true }),
  ).toBeVisible();
  await expect(
    industryNavigation.getByRole("button", {
      name: "电子细分测试 1",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    industryNavigation.locator(".industry-unclassified-l2"),
  ).toHaveCount(0);
  await expect(page).toHaveURL(/industry_id=tech/);
  await expect(page).toHaveURL(/scope=representatives/);
  await expect(page).toHaveURL(/sort=pct_desc/);
  await expect(page).toHaveURL(/page=1/);
  await expect(page).not.toHaveURL(/board=/);
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(1);
  await markets.click();
  await page.getByRole("option", { name: "科创板" }).click();
  await expect(page).toHaveURL(/board=/);
  await expect(markets).toContainText("科创板");
  await expect(industryNavigation.locator(".industry-all")).toHaveText(
    "全部行业1",
  );
  await expect(
    page.getByRole("heading", { name: "科创板 / 电子 · 龙头股" }),
  ).toBeVisible();
  await markets.click();
  await page.getByRole("option", { name: "全部深市", exact: true }).click();
  await expect(page).toHaveURL(/exchange=SZSE/);
  await expect(industryNavigation.locator(".industry-all")).toHaveText(
    "全部行业54",
  );
  await expect(
    industryNavigation.getByRole("button", {
      name: "电子细分测试 52",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page).not.toHaveURL(/board=/);
  await expect(page).toHaveURL(/scope=representatives/);
  await expect(
    page.getByRole("heading", { name: "没有匹配的股票" }),
  ).toBeVisible();
  await markets.click();
  await page.getByRole("option", { name: "北交所", exact: true }).click();
  await expect(page).toHaveURL(/exchange=BSE/);
  await expect(industryNavigation.locator(".industry-all")).toHaveText(
    "全部行业1",
  );
  await expect(
    industryNavigation.locator(".industry-unclassified-l2"),
  ).toHaveText("未细分1");
  await expect(
    industryNavigation.getByRole("button", {
      name: "电子细分测试 0",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole("combobox", { name: "上市板块" })).toHaveCount(0);
  await page.getByRole("button", { name: "龙头股" }).click();
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(1);
  await page.reload();
  await expect(page.locator(".sidebar-market-select .el-select")).toContainText(
    "北交所",
  );
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(1);
  await page.goto("/market?exchange=SSE&board=创业板&scope=all");
  await expect(page).toHaveURL(/exchange=SSE/);
  await expect(page).not.toHaveURL(/board=/);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(markets).toBeVisible();
  await markets.click();
  await page.getByRole("option", { name: "科创板", exact: true }).click();
  await expect(page).toHaveURL(/exchange=SSE/);
  await expect(page).toHaveURL(/board=/);
  await expect(markets).toContainText("科创板");
  await markets.click();
  await page.getByRole("option", { name: "全部 A 股", exact: true }).click();
  await expect(page).not.toHaveURL(/exchange=/);
  await expect(page.locator(".industry-all")).toHaveText("全部行业56");
  await page.screenshot({
    path: "test-results/market-select-mobile.png",
    fullPage: false,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("全部股票和权重筛选共用表格并显示两级行业", async ({ page }) => {
  await page.goto("/market?scope=all&industry_id=bank");
  const bankRow = page
    .locator(".stock-table tbody tr")
    .filter({ hasText: "测试甲银行" });
  await expect(bankRow.locator(".stock-industries")).toContainText("一级银行");
  await expect(bankRow.locator(".stock-industries")).toContainText(
    "二级银行细分测试",
  );

  await page.goto("/market?scope=representatives");
  const leaderRow = page
    .locator(".stock-table tbody tr")
    .filter({ hasText: "测试甲银行" });
  await expect(leaderRow.locator(".stock-industries")).toContainText(
    "一级银行",
  );
  await expect(leaderRow.locator(".stock-industries")).toContainText(
    "二级银行细分测试",
  );

  await page.goto("/market?scope=all&exchange=BSE");
  await expect(
    page.locator(".stock-table tbody tr .stock-industries"),
  ).toContainText("二级暂缺");
});

test("免费数据来源、缺失提示和按需历史自动刷新", async ({ page }) => {
  await page.route("**/api/data-status", async (route) => {
    const response = await route.fetch();
    const status = await response.json();
    await route.fulfill({
      json: {
        ...status,
        source: "免费公开数据 · 腾讯 / AKShare",
        missing_quote_count: 2,
        missing_cap_count: 1,
        history: {
          ...status.history,
          unit: "stock",
          expected_days: 56,
          published_days: 2,
          complete: false,
        },
      },
    });
  });
  await page.goto("/market");
  await expect(page.getByText(/免费公开数据 · 腾讯/)).not.toBeVisible();
  await page.getByRole("button", { name: "数据详情", exact: true }).click();
  await expect(page.getByText(/免费公开数据 · 腾讯/)).toBeVisible();
  await expect(page.getByText(/2 只股票暂无有效行情/)).toBeVisible();
  let calls = 0;
  await page.route("**/api/stocks/1/prices?**", (route) => {
    calls++;
    return route.fulfill({
      json: {
        basis_date: "20260105",
        adjustment: "qfq",
        missing_days: [],
        complete: calls > 1,
        pending: calls === 1,
        message:
          calls === 1 ? "正在补充该股票近一年历史，完成后自动显示。" : null,
        points:
          calls === 1
            ? []
            : [
                {
                  date: "20260102",
                  open: 8.5,
                  high: 9.5,
                  low: 8,
                  close: 9,
                  volume: 1000,
                },
                {
                  date: "20260105",
                  open: 9.5,
                  high: 10.5,
                  low: 9,
                  close: 10,
                  volume: 1500,
                },
              ],
      },
    });
  });
  await page.goto("/stocks/1");
  await expect(
    page.getByText("正在补充该股票近一年历史，完成后自动显示。"),
  ).toBeVisible();
  await expect(
    page.getByText("正在补充该股票近一年历史，完成后自动显示。"),
  ).toHaveCount(0, { timeout: 10000 });
  await expect(page.locator(".candlestick-chart canvas")).toBeVisible();
  expect(calls).toBeGreaterThanOrEqual(2);
});

test("窄屏行业筛选与详情布局", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/market?scope=all");
  await page.getByRole("combobox", { name: "行业", exact: true }).click();
  await page.getByRole("option", { name: "银行 · 2", exact: true }).click();
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(2);
  await page.getByRole("combobox", { name: "行业", exact: true }).click();
  await page.getByRole("option", { name: /银行细分测试 · 2/ }).click();
  await expect(page).toHaveURL(/industry_level=2/);
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(2);
  await expect(
    page.getByRole("complementary", { name: "行业导航" }),
  ).not.toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: /^测试甲银行/ }).click();
  await expect(page.locator(".candlestick-chart canvas")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("默认全市场、拼音直达、最近查看及自选持久化", async ({ page }) => {
  await page.goto("/market?industry_id=tech&scope=representatives");
  await page.getByRole("textbox", { name: "全市场搜索" }).fill("csjyh");
  await page.getByRole("option").filter({ hasText: "测试甲银行" }).click();
  await expect(page).toHaveURL(/stocks\/1/);
  await page.getByRole("button", { name: "☆ 加入自选", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "★ 移除自选", exact: true }),
  ).toBeVisible();
  await page.goto("/market");
  await expect(page.locator(".collection-tabs button")).toHaveText([
    "市场",
    "自选 1",
  ]);
  await expect(page.getByRole("button", { name: "龙头股" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await page.getByRole("textbox", { name: "全市场搜索" }).click();
  await expect(
    page.getByRole("option").filter({ hasText: "测试甲银行" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "自选 1", exact: true }).click();
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(1);
  await page.reload();
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(1);
  await page.goto("/market?collection=recent");
  await expect(page).not.toHaveURL(/collection=recent/);
  await expect(page.locator(".stock-table tbody tr")).toHaveCount(50);
});

test("连续查看跨分页并保留返回条件，复权与周期偏好保持", async ({ page }) => {
  await page.goto(
    "/stocks/20?from=" + encodeURIComponent("/market?scope=all&page_size=20"),
  );
  await expect(page.locator(".stock-navigation")).toContainText("20 / 56");
  await page.getByRole("button", { name: "下一只 →", exact: true }).click();
  await expect(page).toHaveURL(/stocks\/21/);
  await expect(page.locator(".stock-navigation")).toContainText("21 / 56");
  await page.locator(".chart-controls .el-select").click();
  await page.getByRole("option", { name: "不复权", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /日 K 线.*不复权/ }),
  ).toBeVisible();
  await page.getByText("月 K", { exact: true }).click();
  await expect(
    page.getByRole("radio", { name: "近五年", exact: true }),
  ).toBeChecked();
  await page.reload();
  await expect(
    page.getByRole("radio", { name: "月 K", exact: true }),
  ).toBeChecked();
  await expect(
    page.getByRole("heading", { name: /月 K 线.*不复权/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "恢复默认视图" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "← 返回市场浏览" }).click();
  await expect(page).toHaveURL(/page_size=20/);
});

test("非权重股搜索不误报权重缺失，覆盖数可见", async ({ page }) => {
  await page.goto(
    "/market?scope=representatives&keyword=" +
      encodeURIComponent("测试电子公司4"),
  );
  await expect(page.getByText(/当前条件未匹配到龙头股/).first()).toBeVisible();
  await expect(page.locator(".coverage-label")).toContainText("行情缺失");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("textbox", { name: "全市场搜索" })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("图表滚轮缩放、拖动平移与恢复默认视图", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1600 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/stocks/1");
  const chart = page.locator(".candlestick-chart");
  await expect(chart.locator("canvas")).toBeVisible();
  await chart.scrollIntoViewIfNeeded();
  const initial = await chart.screenshot();
  const box = (await chart.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.65, box.y + 180);
  await page.mouse.wheel(0, -500);
  await page.mouse.move(box.x + box.width + 10, box.y + 180);
  await expect
    .poll(async () => (await chart.screenshot()).equals(initial))
    .toBe(false);
  const zoomed = await chart.screenshot();
  await page.mouse.move(box.x + box.width * 0.6, box.y + 180);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.4, box.y + 180, { steps: 10 });
  await page.mouse.up();
  await page.mouse.move(box.x + box.width + 10, box.y + 180);
  await expect
    .poll(async () => (await chart.screenshot()).equals(zoomed))
    .toBe(false);
  await page.getByRole("button", { name: "恢复默认视图" }).click();
  await page.mouse.move(0, 0);
  await chart.evaluate((el) =>
    el.scrollIntoView({ block: "center", behavior: "instant" }),
  );
  await expect
    .poll(async () => (await chart.screenshot()).equals(initial))
    .toBe(true);
});
