<script setup lang="ts">
import { computed, shallowRef } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useHotSectors } from "../../composables/useHotSectors";
import { browseOrigin } from "../../utils/browseOrigin";
import { signedMoney } from "./fundFormat";
import HotFilters from "./HotFilters.vue";
import HotRanking from "./HotRanking.vue";
import HotDetail from "./HotDetail.vue";
import FundStatus from "./FundStatus.vue";
import SectorFlowChart from "./SectorFlowChart.vue";
const route = useRoute(),
  router = useRouter();
const {
  filters,
  selected,
  detailOnly,
  result,
  loading,
  error,
  change,
  select,
  retry,
} = useHotSectors();
const chartCount = shallowRef<5 | 10>(5);
const period = computed(() => filters.value.period);
const listBack = computed(() => {
  const path = browseOrigin(route.query.list);
  return path.startsWith("/hot-sectors") ? path : "/hot-sectors";
});
</script>
<template>
  <div class="hot-workspace">
    <RouterLink v-if="detailOnly" :to="listBack" class="back-link"
      >← 返回板块排行</RouterLink
    >
    <header class="hot-heading">
      <div>
        <div class="eyebrow">板块资金观察</div>
        <h1>热门板块</h1>
        <p>发现资金关注的方向，观察持续性，再查看板块内个股。</p>
      </div>
      <span class="heading-note">东方财富分类 · 延迟可接受</span>
    </header>
    <template v-if="!detailOnly">
      <HotFilters :filters="filters" @change="change" @refresh="retry" />
      <FundStatus v-if="result" :meta="result.meta" />
      <el-alert v-if="error" :title="error" type="warning" :closable="false"
        ><el-button text @click="retry">重试</el-button></el-alert
      >
      <el-skeleton v-if="loading" :rows="8" animated />
      <template v-if="result">
        <div class="fund-overview" aria-label="全部板块资金概览">
          <button
            class="overview-item inflow"
            :disabled="!result.overview.top_in"
            @click="result.overview.top_in && select(result.overview.top_in.id)"
          >
            <small>最大净流入</small
            ><strong>{{
              result.overview.top_in?.name || "暂无净流入板块"
            }}</strong
            ><span>{{ signedMoney(result.overview.top_in?.net_amount) }}</span>
          </button>
          <button
            class="overview-item outflow"
            :disabled="!result.overview.top_out"
            @click="
              result.overview.top_out && select(result.overview.top_out.id)
            "
          >
            <small>最大净流出</small
            ><strong>{{
              result.overview.top_out?.name || "暂无净流出板块"
            }}</strong
            ><span>{{ signedMoney(result.overview.top_out?.net_amount) }}</span>
          </button>
          <div class="overview-item coverage">
            <small
              >全部{{ filters.kind === "concept" ? "概念" : "行业" }} ·
              有效资金</small
            ><strong
              >{{ result.overview.valid_count }}
              <em>/ {{ result.overview.total_count }}</em></strong
            ><span>不随搜索及分页变化</span>
          </div>
        </div>
        <SectorFlowChart
          v-model:count="chartCount"
          :chart="result.chart"
          :kind="filters.kind"
          :period="period"
          :selected="selected"
          @select="select"
        />
        <div class="hot-columns">
          <HotRanking
            :result="result"
            :selected="selected"
            :period="period"
            @select="select"
            @page="change({ page: $event })"
            @page-size="change({ page_size: $event })"
          />
          <HotDetail
            v-if="selected"
            :id="selected"
            :period="period"
            :from="route.fullPath"
            class="desktop-detail"
          />
          <aside v-else class="no-selection">
            选择板块查看资金趋势和成分股
          </aside>
        </div>
      </template>
    </template>
    <template v-else>
      <el-radio-group
        :model-value="period"
        aria-label="详情资金周期"
        class="detail-period"
        @change="
          (p: string | number | boolean) =>
            router.replace({ query: { ...route.query, period: String(p) } })
        "
        ><el-radio-button value="today">今日</el-radio-button
        ><el-radio-button value="5d">5日</el-radio-button
        ><el-radio-button value="10d">10日</el-radio-button></el-radio-group
      >
      <HotDetail :id="selected" :period="period" :from="route.fullPath" />
    </template>
    <p class="fund-explanation">
      资金流向采用数据源的成交分类口径，不代表真实机构账户进出。概念之间存在成分重叠，不合计为全市场资金。行业、概念分别查看。
    </p>
  </div>
</template>
<style scoped>
.hot-workspace {
  padding: 24px 22px 32px;
  min-width: 0;
}
.hot-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.eyebrow {
  color: var(--accent);
  font-size: 10px;
  letter-spacing: 2px;
}
.hot-heading h1 {
  margin: 7px 0;
  font-size: 24px;
}
.hot-heading p {
  color: var(--muted);
  font-size: 12px;
  margin: 0;
  line-height: 1.8;
}
.heading-note {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
}
.fund-overview {
  display: grid;
  grid-template-columns: 1fr 1fr 0.8fr;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  margin: 20px 0 4px;
}
.overview-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  border: 0;
  border-right: 1px solid var(--line);
  background: transparent;
  padding: 18px 20px;
  text-align: left;
}
.overview-item:first-child {
  padding-left: 0;
}
.overview-item:last-child {
  border-right: 0;
}
.overview-item small {
  color: var(--muted);
  font-size: 11px;
}
.overview-item strong {
  margin: 8px 0;
  font-size: 17px;
}
.overview-item span {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.inflow span {
  color: var(--up);
}
.outflow span {
  color: var(--down);
}
.coverage strong {
  font-size: 24px;
}
.coverage em {
  font-size: 13px;
  font-style: normal;
  color: var(--muted);
}
.coverage span {
  font-size: 10px;
  color: var(--muted);
}
.hot-columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 24px;
  margin-top: 20px;
}
.no-selection {
  padding: 40px 20px;
  color: var(--muted);
  text-align: center;
  background: var(--subtle);
}
.fund-explanation {
  margin: 24px 0 0;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.8;
}
.detail-period {
  margin: 20px 0;
}
.back-link {
  display: inline-block;
  margin-bottom: 20px;
  font-size: 12px;
  color: var(--accent);
}
@media (max-width: 900px) {
  .hot-columns {
    grid-template-columns: minmax(0, 1fr);
  }
  .desktop-detail,
  .no-selection {
    display: none;
  }
  .heading-note {
    display: none;
  }
}
@media (max-width: 600px) {
  .hot-workspace {
    padding: 20px 14px;
  }
  .hot-heading h1 {
    font-size: 22px;
  }
  .fund-overview {
    grid-template-columns: 1fr 1fr;
  }
  .overview-item {
    padding: 16px 10px;
  }
  .overview-item strong {
    font-size: 14px;
  }
  .coverage {
    grid-column: 1/-1;
    border-top: 1px solid var(--line);
    padding: 12px 0;
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }
  .coverage strong {
    margin: 0;
    font-size: 18px;
  }
  .coverage span {
    margin-left: auto;
  }
}
</style>
