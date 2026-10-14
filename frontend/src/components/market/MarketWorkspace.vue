<script setup lang="ts">
import { computed, shallowRef, useTemplateRef, watch } from "vue";
import { useMarket } from "../../composables/useMarket";
import { usePreviewResize } from "../../composables/usePreviewResize";
import MarketOverview from "./MarketOverview.vue";
import { useLibrary } from "../../composables/useLibrary";
import MarketFilters from "./MarketFilters.vue";
import MarketSelect from "./MarketSelect.vue";
import StockTable from "./StockTable.vue";
import MarketSidebar from "./MarketSidebar.vue";
import StockPreview from "./StockPreview.vue";
import DataStatusBar from "./DataStatusBar.vue";
import { MARKET_OPTIONS } from "../../marketOptions";
const {
  filters,
  result,
  industries,
  level1Industries,
  level2Industries,
  concepts,
  status,
  loading,
  error,
  change,
  open,
  reset,
  retry,
} = useMarket();
const { storageError, favorites } = useLibrary();
const resultScroll = useTemplateRef<HTMLDivElement>("resultScroll");
const marketContent = useTemplateRef<HTMLDivElement>("marketContent");
const {
  previewWidth,
  maxPreviewWidth,
  visibleWidth,
  resizing,
  startResize,
  moveResize,
  stopResize,
  resizeWithKeyboard,
} = usePreviewResize(marketContent);
const selectedId = shallowRef<number | null>(null);
watch(filters, () => {
  resultScroll.value?.scrollTo({ top: 0, left: 0 });
  selectedId.value = null;
});
const visibleStocks = computed(() => result.value?.items ?? []);
watch(visibleStocks, (stocks) => {
  if (selectedId.value === null && stocks[0]) selectedId.value = stocks[0].id;
});
const selectedStock = computed(
  () =>
    visibleStocks.value.find((stock) => stock.id === selectedId.value) ??
    visibleStocks.value[0],
);
const marketStockCount = computed(() =>
  level1Industries.value.reduce(
    (count, industry) => count + industry.stock_count,
    0,
  ),
);
const scopeTitle = computed(() => {
  const concept = concepts.value.find(
    (item) => item.id === filters.value.concept_id,
  );
  const industry = industries.value.find(
    (item) => item.id === filters.value.industry_id,
  );
  const industryName = industry
    ? [industry.parent_name, industry.name].filter(Boolean).join(" / ")
    : "";
  const marketName = MARKET_OPTIONS.find(
    (item) => item.value === filters.value.exchange,
  )?.label;
  const name =
    [
      filters.value.board || (filters.value.exchange ? marketName : ""),
      filters.value.view === "concept"
        ? concept?.name || "概念板块"
        : industryName,
    ]
      .filter(Boolean)
      .join(" / ") || "全市场";
  const scope = filters.value.scope === "all" ? "全部股票" : "龙头股";
  const collection = filters.value.collection === "favorites" ? " · 自选" : "";
  return `${name} · ${scope}${collection}`;
});
</script>
<template>
  <div class="market-layout">
    <MarketSidebar
      :filters="filters"
      :level1-industries="level1Industries"
      :level2-industries="level2Industries"
      :concepts="concepts"
      @change="change"
    />
    <div class="workspace market-workspace">
      <div class="market-heading">
        <div class="market-title">
          <h1>市场浏览</h1>
          <span v-if="result"
            >{{ marketStockCount.toLocaleString() }} 只股票</span
          >
          <MarketSelect
            class="mobile-market-select"
            :exchange="filters.exchange"
            :board="filters.board"
            @change="change"
          />
        </div>
        <DataStatusBar :status="status" />
      </div>
      <div class="collection-tabs" role="group" aria-label="浏览集合">
        <button
          :class="{ active: filters.collection === 'all' }"
          @click="change({ collection: 'all' })"
        >
          市场
        </button>
        <button
          :class="{ active: filters.collection === 'favorites' }"
          @click="change({ collection: 'favorites', scope: 'all' })"
        >
          自选 {{ favorites.length }}
        </button>
        <small>自选与最近查看记录保存在当前浏览器</small>
      </div>
      <p v-if="storageError" role="alert">{{ storageError }}</p>
      <MarketOverview
        :filters="filters"
        :revision="status?.quote_fetched_at ?? status?.trade_date"
      />
      <MarketFilters
        :filters="filters"
        :level1-industries="level1Industries"
        :level2-industries="level2Industries"
        :concepts="concepts"
        @change="change"
      />
      <div
        ref="marketContent"
        class="market-content"
        :class="{ 'is-resizing': resizing }"
        :style="
          previewWidth === null
            ? undefined
            : { '--preview-width': `${previewWidth}px` }
        "
      >
        <div class="market-results">
          <div class="results-heading">
            <h2>{{ scopeTitle }}</h2>
            <span v-if="result">{{ result.matched_stocks }} 只</span>
          </div>
          <p
            v-if="
              filters.view === 'industry' &&
              filters.industry_level === 2 &&
              filters.scope === 'representatives'
            "
            class="l2-representative-note"
          >
            按 SW2021 二级行业指数最新成分权重排序；无可用权重时不生成权重名单。
          </p>
          <el-alert
            v-if="error"
            :title="error"
            type="error"
            :closable="false"
            show-icon
            ><span v-if="result"
              >以下保留上次成功结果，可能不对应当前筛选。</span
            ><el-button text @click="retry">重试</el-button></el-alert
          >
          <section
            v-if="status && !status.available && !status.stock_count"
            class="empty-state panel"
          >
            <span class="empty-icon">▤</span>
            <h2>市场数据，等待首次同步</h2>
            <p>
              首次同步完成后，即可浏览真实的行业、股票和行情。<br />默认免费数据源，无需配置
              Tushare 凭证。
            </p>
            <span class="muted">使用项目运行说明中的初始化命令</span
            ><el-button @click="retry">检查更新</el-button>
          </section>
          <el-skeleton
            v-else-if="loading && !result"
            :rows="8"
            animated
            class="panel skeleton"
          />
          <div v-else-if="result" class="results-body" :aria-busy="loading">
            <div
              ref="resultScroll"
              class="result-scroll"
              tabindex="0"
              aria-label="股票列表"
            >
              <div v-if="result.items.length" class="panel table-panel">
                <StockTable
                  :key="filters.sort"
                  :stocks="result.items"
                  :sort="filters.sort"
                  @sort="change({ sort: $event })"
                  :selected-id="selectedStock?.id"
                  @select="selectedId = $event"
                  @open="open"
                />
              </div>
              <section v-else class="empty-state panel">
                <h2>没有匹配的股票</h2>
                <p v-if="filters.scope === 'representatives'">
                  当前条件未匹配到龙头股；该行业可能暂无可用指数权重名单，或其他筛选条件无匹配。
                </p>
                <p v-else>
                  试试其他{{
                    filters.view === "concept" ? "概念" : "行业"
                  }}，或在全部股票中搜索。
                </p>
                <el-button @click="reset">清空筛选，搜索全部股票</el-button>
              </section>
            </div>
            <div v-if="result.total" class="pagination-bar">
              <span>共 {{ result.total }} 只股票</span
              ><el-pagination
                background
                :current-page="filters.page"
                :page-size="filters.page_size"
                :page-sizes="[20, 50, 100]"
                layout="sizes, prev, pager, next"
                :total="result.total"
                @update:current-page="change({ page: $event })"
                @update:page-size="change({ page_size: $event })"
              />
            </div>
          </div>
        </div>
        <div
          v-if="selectedStock && status?.available"
          class="preview-resize-handle"
          role="separator"
          aria-label="调整个股速览宽度"
          aria-orientation="vertical"
          :aria-valuenow="visibleWidth"
          aria-valuemin="215"
          :aria-valuemax="maxPreviewWidth"
          tabindex="0"
          @pointerdown="startResize"
          @pointermove="moveResize"
          @pointerup="stopResize"
          @pointercancel="stopResize"
          @keydown="resizeWithKeyboard"
        />
        <StockPreview
          v-if="selectedStock && status?.available"
          :stock="selectedStock"
          @open="open"
        />
      </div>
    </div>
  </div>
</template>
