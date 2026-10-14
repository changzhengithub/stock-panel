<script setup lang="ts">
import { computed } from "vue";
import { ElPopover } from "element-plus";
import type { DataStatus } from "../../api";
import { date, quoteTime } from "../../utils/format";
const props = defineProps<{ status: DataStatus | null }>();
const industryFetchedAt = computed(() => {
  const value = props.status?.industry_synced_at;
  if (!value) return "尚未更新";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(parsed);
});
const stateLabel = computed(() => {
  const status = props.status;
  if (!status) return "";
  if (status.quote_error) return "行情更新异常";
  if (status.quote_mode === "live")
    return status.stale ? "行情更新延迟" : "自动更新";
  if (status.last_run?.state === "running") return "同步中";
  if (!status.available) return "待初始化";
  if (status.stale) return "旧数据";
  if (status.industry_stale) return "行业待更新";
  if (status.last_run?.state === "partial") return "历史待补齐";
  if (status.last_run?.error) return "更新异常";
  if (status.missing_quote_count || !status.history.complete)
    return "数据待补齐";
  return "";
});
</script>
<template>
  <div v-if="status" class="data-status">
    <span class="data-date"
      >行情 {{ quoteTime(status.trade_date, status.quote_time) }}</span
    >
    <span class="coverage-label"
      >有效 {{ status.stock_count - status.missing_quote_count }} /
      {{ status.stock_count }} · 行情缺失 {{ status.missing_quote_count }}</span
    >
    <span v-if="stateLabel" class="data-state" role="status">{{
      stateLabel
    }}</span>
    <el-popover
      trigger="click"
      placement="bottom-end"
      :width="360"
      popper-style="max-width: calc(100vw - 32px)"
    >
      <template #reference>
        <button class="data-details-button" type="button">数据详情</button>
      </template>
      <div class="data-details">
        <h3>数据详情</h3>
        <p>{{ status.source }}<br />{{ status.industry_source }}</p>
        <template v-if="status.quote_mode === 'live'">
          <p>
            免费行情自动更新。来源时间范围 {{ status.quote_oldest_time }}～{{
              status.quote_time
            }}，以各股票实际行情时间为准。
          </p>
          <p v-for="(coverage, market) in status.quote_coverage" :key="market">
            {{
              { SSE: "沪市", SZSE: "深市", BSE: "北交所" }[market] ?? market
            }}：{{ coverage.valid }} / {{ coverage.total }} 只有效报价
          </p>
          <p>
            历史与盘后快照截至
            {{ date(status.daily_trade_date) }}，与最新报价分别更新。
          </p>
        </template>
        <p v-if="status.quote_error" class="warning-text">
          {{ status.quote_error }}。保留上次有效行情，日期未改写。
        </p>
        <p v-if="status.industry_l2_available">
          SW2021：31 个一级、{{ status.industry_l2_count }} 个二级行业。<br />
          分类文件获取于 {{ industryFetchedAt }}；来源最近变动
          {{
            date(status.industry_source_updated_at)
          }}。这是行业归属更新日期，不是实时行情时间。
        </p>
        <p v-else class="warning-text">二级行业尚未完成同步，暂不可切换。</p>
        <p v-if="status.industry_stale" class="warning-text">
          分类文件尚未覆盖最近交易日，请运行数据同步；当前仍展示上次有效归属。
        </p>
        <p v-if="status.last_run?.state === 'running'">
          正在同步：{{ status.last_run.progress }}
        </p>
        <p v-if="status.stale" class="warning-text">
          当前展示上一份有效行情，请以标注的行情日期和时间为准。
        </p>
        <p
          v-if="status.missing_quote_count || status.missing_cap_count"
          class="warning-text"
        >
          {{ status.missing_quote_count }} 只股票暂无有效行情（不参与涨跌榜），
          {{ status.missing_cap_count }} 只缺少市值；未根据缺失推断停牌。
        </p>
        <p v-if="status.unclassified_count">
          {{ status.unclassified_count }}
          只股票暂无 SW2021 一级行业归属，可在全部股票中查看。
        </p>
        <p
          v-if="
            status.industry_l2_available &&
            status.industry_l2_unclassified_count
          "
        >
          {{ status.industry_l2_unclassified_count }}
          只股票暂无 SW2021 二级归属，归入“未细分”。
        </p>
        <p v-if="status.available && !status.history.complete">
          历史回填 {{ status.history.published_days }} /
          {{ status.history.expected_days }}
          {{
            status.history.unit === "stock" ? "只股票" : "个交易日"
          }}，尚未完整。
          <span v-if="status.history.unit === 'stock'"
            >打开股票详情可自动补取历史。</span
          >
        </p>
        <details
          v-if="status.last_run?.error || status.last_run?.warnings.length"
        >
          <summary>更新日志</summary>
          <pre
            >{{ status.last_run.error
            }}{{ status.last_run.warnings.join("\n") }}</pre>
        </details>
      </div>
    </el-popover>
  </div>
</template>
