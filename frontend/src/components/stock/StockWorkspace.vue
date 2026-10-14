<script setup lang="ts">
import { useStock } from "../../composables/useStock";
import { money, price, percent, tone, date } from "../../utils/format";
import CandlestickChart from "./CandlestickChart.vue";
import StockNavigation from "./StockNavigation.vue";
import StockBasics from "./StockBasics.vue";
import QuoteStamp from "./QuoteStamp.vue";
const {
  stock,
  prices,
  range,
  period,
  adjustment,
  navigation,
  navigationError,
  navigate,
  error,
  chartError,
  loading,
  back,
  fromHot,
  fromChain,
  retry,
} = useStock();
</script>
<template>
  <div class="workspace stock-workspace">
    <RouterLink class="back-link" :to="back"
      >← 返回{{
        fromChain ? "产业链分析" : fromHot ? "热门板块" : "市场浏览"
      }}</RouterLink
    >
    <StockNavigation
      :stock="stock"
      :navigation="navigation"
      :error="navigationError"
      :from-hot="fromHot || fromChain"
      @navigate="navigate"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false"
      ><el-button text @click="retry">重试</el-button></el-alert
    >
    <el-skeleton v-if="loading" :rows="8" animated />
    <template v-if="stock">
      <div class="page-heading detail-heading">
        <div>
          <div class="eyebrow">{{ stock.code }} · {{ stock.board }}</div>
          <h1>
            {{ stock.name }}
            <span
              v-if="stock.is_st"
              class="tiny-tag"
              :title="
                stock.st_source === 'current_name'
                  ? '当前名称标记'
                  : '交易日 ST 状态'
              "
              >ST</span
            >
          </h1>
          <p>{{ stock.fullname ?? "暂无公司全称" }}</p>
          <div class="tags">
            <span>{{ stock.industry }}</span
            ><span v-if="stock.industry_l2">{{ stock.industry_l2 }}</span
            ><span>{{ stock.board }}</span
            ><span>上市 {{ date(stock.list_date) }}</span>
          </div>
        </div>
        <div class="detail-price">
          <strong :class="tone(stock.pct_chg)">{{ price(stock.close) }}</strong
          ><span :class="tone(stock.pct_chg)">{{ percent(stock.pct_chg) }}</span
          ><small><QuoteStamp :stock="stock" /></small>
        </div>
      </div>
      <div class="metric-grid">
        <div class="panel metric">
          <span>总市值</span><strong>{{ money(stock.market_cap) }}</strong>
        </div>
        <div class="panel metric">
          <span>当日成交额</span><strong>{{ money(stock.amount) }}</strong>
        </div>
        <div class="panel metric">
          <span>上市板块</span><strong>{{ stock.board }}</strong>
        </div>
      </div>
      <StockBasics :stock="stock" />
      <div class="detail-grid">
        <div class="detail-main">
          <section class="panel chart-panel">
            <header class="section-heading">
              <h2>
                {{ period === "day" ? "日" : period === "week" ? "周" : "月" }}
                K 线<small
                  >{{
                    adjustment === "none" ? "不复权 · 截至" : "前复权 · 基准"
                  }}
                  {{ date(prices?.basis_date) }}</small
                >
              </h2>
              <div class="chart-controls">
                <el-select
                  v-model="adjustment"
                  aria-label="复权方式"
                  style="width: 108px"
                  ><el-option value="qfq" label="前复权" /><el-option
                    value="none"
                    label="不复权"
                /></el-select>
                <el-radio-group
                  v-model="period"
                  size="small"
                  aria-label="K 线周期"
                >
                  <el-radio-button value="day">日 K</el-radio-button>
                  <el-radio-button value="week">周 K</el-radio-button>
                  <el-radio-button value="month">月 K</el-radio-button>
                </el-radio-group>
                <el-radio-group
                  v-model="range"
                  size="small"
                  aria-label="价格区间"
                  ><el-radio-button value="1m">近一个月</el-radio-button
                  ><el-radio-button value="3m">近三个月</el-radio-button
                  ><el-radio-button value="1y">近一年</el-radio-button
                  ><el-radio-button value="3y">近三年</el-radio-button
                  ><el-radio-button value="5y">近五年</el-radio-button
                  ><el-radio-button value="10y"
                    >近十年</el-radio-button
                  ></el-radio-group
                >
              </div>
            </header>
            <el-alert
              v-if="chartError"
              :title="chartError"
              type="error"
              :closable="false"
              ><el-button text @click="retry">重试走势</el-button></el-alert
            >
            <p v-if="prices?.message" class="chart-message">
              {{ prices.message }}
            </p>
            <el-button v-if="prices && !prices.complete" text @click="retry"
              >刷新历史数据</el-button
            >
            <CandlestickChart
              :prices="prices"
              :range="range"
              :period="period"
            />
            <p v-if="period !== 'day'" class="chart-period-note">
              周 K 至少请求五年、月 K
              请求十年日线作为计算历史；显示区间可独立缩放。上市时间或数据源限制导致不足时，相应指标不可用。
            </p>
          </section>
          <section class="panel company-section">
            <div>
              <h2>主营业务</h2>
              <p>{{ stock.main_business ?? "暂无主营业务资料" }}</p>
            </div>
            <div>
              <h2>公司简介</h2>
              <p>{{ stock.introduction ?? "暂无公司简介" }}</p>
            </div>
            <small class="muted"
              >资料更新时间 {{ stock.updated_at.slice(0, 10) }}</small
            >
          </section>
        </div>
        <aside class="detail-aside">
          <section v-if="stock.representative" class="representative-note">
            <div class="eyebrow">龙头股</div>
            <p>{{ stock.representative.reason }}</p>
            <small
              >权重日期 {{ stock.representative.weight_date ?? "来源未提供"
              }}<br />获取日期 {{ stock.representative.reviewed_at }} ·
              <a
                :href="stock.representative.source_url"
                target="_blank"
                rel="noopener noreferrer"
                >查看依据 ↗</a
              ></small
            >
          </section>
          <section class="panel detail-tip">
            <h2>行情口径</h2>
            <p>
              列表与摘要自动更新免费最新报价；行情时间以来源返回为准。周 K、月 K
              按自然周、自然月由所选复权口径的日线汇总，成交量为原始日成交量（手）的周期合计。MA5/10/20/60
              按所选周期的连续收盘价计算，均量线也按所选周期计算。MACD 与 RSI
              根据所选周期收盘价计算。已确认停牌日不计入有效交易记录；未知日线缺口不绘制该周期
              K 线；历史不足时均线显示为空。
            </p>
            <p>
              行情日期 {{ date(stock.quote_date) }}<br />所属行业
              {{ stock.industry }} → {{ stock.industry_l2 ?? "二级暂缺" }}
            </p>
          </section>
        </aside>
      </div>
    </template>
  </div>
</template>
<style scoped>
.chart-controls {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}
.chart-period-note {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.6;
}
</style>
