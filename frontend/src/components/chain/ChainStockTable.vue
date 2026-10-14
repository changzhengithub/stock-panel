<script setup lang="ts">
import type {
  ChainStock,
  ChainStocks,
  ChainSource,
} from "../../api/industryChains";
import { money, price, percent, tone } from "../../utils/format";
import { useLibrary } from "../../composables/useLibrary";
import ChainCompanyAnalysis from "./ChainCompanyAnalysis.vue";
import ChainEvidence from "./ChainEvidence.vue";
import QuoteStamp from "../stock/QuoteStamp.vue";
defineProps<{
  result: ChainStocks | null;
  error: string;
  scope: string;
  nodeName: string;
  from: string;
  selectedIds: number[];
  filters: {
    q: string;
    participation: string;
    stage: string;
    leader: string;
    mapping_status: string;
    sort: string;
  };
  sources: ChainSource[];
}>();
const emit = defineEmits<{
  change: [values: Record<string, string | number>];
  select: [row: ChainStock];
  compare: [];
  retry: [];
}>();
const { toggle, isFavorite, storageError } = useLibrary();
function value(e: Event) {
  return (e.target as HTMLSelectElement).value;
}
</script>
<template>
  <section class="stock-section">
    <header>
      <div>
        <span class="eyebrow">从环节找到公司</span>
        <h2>
          {{ scope === "chain" ? "全产业链公司" : nodeName + " · 相关公司" }}
        </h2>
      </div>
      <div class="actions">
        <el-button
          size="small"
          @click="
            emit('change', { scope: scope === 'chain' ? 'node' : 'chain' })
          "
          >{{ scope === "chain" ? "查看当前节点" : "查看全产业链" }}</el-button
        ><el-button
          size="small"
          type="primary"
          :disabled="scope === 'chain' || selectedIds.length < 2"
          @click="emit('compare')"
          >比较公司
          {{
            selectedIds.length ? "(" + selectedIds.length + ")" : ""
          }}</el-button
        >
      </div>
    </header>
    <div class="filters">
      <select
        :value="filters.mapping_status"
        aria-label="业务关联状态"
        @change="emit('change', { mapping_status: value($event) })"
      >
        <option
          v-for="v in ['全部', '资料核验', '业务词匹配', '分类候选']"
          :key="v"
          :value="v"
        >
          {{ v === "全部" ? "全部关联状态" : v }}
        </option>
      </select>
      <input
        :value="filters.q"
        aria-label="筛选产业链股票"
        placeholder="名称或代码"
        @input="emit('change', { q: value($event) })"
      /><select
        :value="filters.participation"
        aria-label="参与方式"
        @change="emit('change', { participation: value($event) })"
      >
        <option
          v-for="v in [
            '全部',
            '直接经营',
            '控股子公司',
            '参股',
            '其他已披露方式',
            '待核实',
          ]"
          :key="v"
        >
          {{ v }}
        </option></select
      ><select
        :value="filters.stage"
        aria-label="经营阶段"
        @change="emit('change', { stage: value($event) })"
      >
        <option
          v-for="v in [
            '经营中',
            '全部',
            '已形成收入',
            '已开展经营',
            '试产',
            '建设中',
            '研发中',
            '未知',
          ]"
          :key="v"
        >
          {{ v }}
        </option></select
      ><select
        :value="filters.leader"
        aria-label="节点龙头类型"
        @change="emit('change', { leader: value($event) })"
      >
        <option
          v-for="v in [
            '全部',
            '规模龙头',
            '份额龙头',
            '技术领先企业',
            '代表企业',
          ]"
          :key="v"
          :value="v"
        >
          {{ v === "全部" ? "全部龙头类型" : v }}
        </option></select
      ><select
        :value="filters.sort"
        aria-label="产业链股票排序"
        @change="emit('change', { sort: value($event) })"
      >
        <option value="default">资料核验优先，同状态按代码</option>
        <option value="pct_desc">涨跌幅降序</option>
        <option value="pct_asc">涨跌幅升序</option>
        <option value="market_cap_desc">市值降序</option>
        <option value="amount_desc">成交额降序</option>
        <option value="close_desc">股价降序</option>
      </select>
    </div>
    <p class="note">
      {{ result?.stock_count ?? "—" }} 家可浏览 · 已登记
      {{ result?.registered_count ?? "—" }} 家 · 未匹配
      {{ result?.unmatched_count ?? "—" }} 家 · 被过滤
      {{ result?.filtered_count ?? "—" }}
      家。公司逐条标明资料核验、业务词匹配或分类候选。阶段和主体未确认时保留待核实。
    </p>
    <p v-if="error" role="alert">
      {{ error }} <el-button text @click="emit('retry')">重试</el-button>
    </p>
    <p v-if="storageError" role="alert">{{ storageError }}</p>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>比较</th>
            <th>公司 / 行情</th>
            <th>实际业务与阶段</th>
            <th>产品分部收入 / 占比</th>
            <th>节点龙头依据</th>
            <th>自选</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in result?.items ?? []" :key="s.id">
            <td>
              <input
                type="checkbox"
                :aria-label="'比较' + s.name"
                :disabled="scope === 'chain'"
                :checked="selectedIds.includes(s.id)"
                @change="emit('select', s)"
              />
            </td>
            <td class="stock-identity">
              <RouterLink :to="{ path: '/stocks/' + s.id, query: { from } }"
                ><strong>{{ s.name }}</strong
                ><small>{{ s.ts_code }}</small></RouterLink
              >
              <div :class="tone(s.pct_chg)">
                {{ price(s.close) }} <span>{{ percent(s.pct_chg) }}</span>
              </div>
              <small><QuoteStamp :stock="s" /></small
              ><small v-if="s.quote_stale">行情可能陈旧</small>
            </td>
            <td>
              <div v-for="m in s.memberships" :key="m.key" class="business">
                <strong>{{ m.business }}</strong
                ><small
                  >{{ m.mapping_status ?? "资料核验" }} ·
                  {{ m.participation }} · {{ m.operating_stage }}</small
                ><small>{{ m.subject }}</small
                ><ChainCompanyAnalysis
                  :messages="m.company_analysis ?? []"
                /><ChainEvidence :evidence="m.evidence" :sources="sources" />
              </div>
            </td>
            <td>
              <template v-for="m in s.memberships" :key="m.key"
                ><p v-for="(v, i) in m.metrics" :key="i" class="metric">
                  {{ v.currency }} {{ money(v.revenue) }} /
                  {{ v.share == null ? "—" : v.share.toFixed(2) + "%"
                  }}<small
                    >{{ v.period }} · {{ v.basis }} ·
                    {{ v.verification ?? "原始资料核验" }}</small
                  >
                </p></template
              ><span
                v-if="!s.memberships.some((m) => m.metrics.length)"
                class="muted"
                >未取得可核验分部数据</span
              >
            </td>
            <td>
              <div v-for="m in s.memberships" :key="m.key">
                <details v-for="(l, i) in m.leaders" :key="i" class="leader">
                  <summary :class="{ leading: l.kind !== '代表企业' }">
                    {{ l.kind }}
                  </summary>
                  <p>{{ l.product }} · {{ l.geography }} · {{ l.period }}</p>
                  <p v-if="l.freshness">{{ l.freshness }}</p>
                  <p>{{ l.reason }}</p>
                  <ChainEvidence :evidence="l.evidence" :sources="sources" />
                </details>
              </div>
            </td>
            <td>
              <el-button
                text
                :aria-label="
                  (isFavorite(s.ts_code) ? '移除自选' : '加入自选') + s.name
                "
                @click="toggle(s)"
                >{{ isFavorite(s.ts_code) ? "★" : "☆" }}</el-button
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="result && !result.items.length" class="empty">
      当前条件无相关公司；可调整经营阶段或选择其他节点。
    </p>
    <p v-if="!result && !error" class="empty">正在读取相关公司…</p>
    <div v-if="result" class="pagination">
      <small>当前筛选 {{ result.total }} 家 · 选择同节点 2～4 家比较</small
      ><el-pagination
        :current-page="result.page"
        :page-size="result.page_size"
        :page-sizes="[20, 50, 100]"
        :total="result.total"
        layout="sizes, prev, pager, next"
        small
        @current-change="emit('change', { page: $event })"
        @size-change="emit('change', { page_size: $event, page: 1 })"
      />
    </div>
  </section>
</template>
<style scoped>
.stock-section {
  margin-top: 24px;
  border: 1px solid var(--line);
  border-radius: 6px;
  min-width: 0;
}
header {
  padding: 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
h2 {
  font-size: 18px;
  margin: 8px 0 0;
}
.actions {
  display: flex;
  gap: 8px;
}
.actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 20px 12px;
}
.filters input,
.filters select {
  border: 1px solid var(--line);
  border-radius: 4px;
  background: white;
  color: var(--text);
  padding: 7px 10px;
  font-size: 12px;
  max-width: 100%;
}
.filters input {
  width: 180px;
}
.note {
  font-size: 11px;
  color: var(--muted);
  margin: 0;
  padding: 0 20px 14px;
  line-height: 1.8;
}
.table-scroll {
  overflow-x: auto;
}
table {
  border-collapse: collapse;
  width: 100%;
  min-width: 880px;
  text-align: left;
  font-size: 12px;
}
th {
  background: var(--subtle);
  color: var(--muted);
  font-weight: 500;
  padding: 12px;
}
td {
  padding: 16px 12px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
td:nth-child(2) {
  min-width: 150px;
}
td:nth-child(3) {
  width: 26%;
}
td:nth-child(4) {
  width: 22%;
}
td:nth-child(5) {
  width: 22%;
}
.stock-identity strong {
  display: block;
  font-size: 14px;
}
.stock-identity a:hover {
  color: var(--accent);
}
small {
  display: block;
  font-size: 10px;
  color: var(--muted);
  line-height: 1.7;
}
.stock-identity div {
  margin: 10px 0 4px;
}
.stock-identity span {
  margin-left: 8px;
}
.business {
  margin-bottom: 10px;
}
.business strong {
  font-weight: 500;
}
.metric {
  margin: 0 0 10px;
}
.metric small {
  margin-top: 6px;
}
.leader {
  margin-bottom: 12px;
}
.leader summary {
  cursor: pointer;
  font-size: 11px;
  color: var(--muted);
}
.leader .leading {
  color: var(--accent);
}
.leader p {
  font-size: 11px;
  line-height: 1.8;
}
.pagination {
  padding: 14px 20px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.empty {
  padding: 20px;
  color: var(--muted);
  font-size: 13px;
}
@media (max-width: 700px) {
  header {
    padding: 14px;
    flex-direction: column;
    align-items: flex-start;
  }
  .filters {
    padding-inline: 14px;
  }
  .filters input {
    width: 100%;
  }
  .note {
    padding-inline: 14px;
  }
  .pagination {
    padding: 14px;
  }
  .pagination :deep(.el-pagination__sizes) {
    display: none;
  }
}
</style>
