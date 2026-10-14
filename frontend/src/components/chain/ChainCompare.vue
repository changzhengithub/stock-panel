<script setup lang="ts">
import { shallowRef, watch, computed } from "vue";
import { useRoute } from "vue-router";
import {
  chainGet,
  type ChainComparison,
  type ChainDetail,
} from "../../api/industryChains";
import { browseOrigin } from "../../utils/browseOrigin";
import { money, percent, price } from "../../utils/format";
import ChainCompanyAnalysis from "./ChainCompanyAnalysis.vue";
import ChainEvidence from "./ChainEvidence.vue";
import QuoteStamp from "../stock/QuoteStamp.vue";
const route = useRoute(),
  data = shallowRef<ChainComparison | null>(null),
  chain = shallowRef<ChainDetail | null>(null),
  error = shallowRef("");
const back = computed(() =>
  browseOrigin(route.query.from ?? "/industry-chains/" + route.params.id),
);
watch(
  () => route.fullPath,
  async (_, __, cleanup) => {
    const c = new AbortController();
    cleanup(() => c.abort());
    data.value = null;
    chain.value = null;
    error.value = "";
    try {
      const d = await chainGet<ChainDetail>(
        "/" + route.params.id,
        { revision: route.query.revision },
        c.signal,
      );
      if (c.signal.aborted) return;
      const r = await chainGet<ChainComparison>(
        "/" + route.params.id + "/compare",
        {
          revision: d.revision_id,
          node_key: route.query.node,
          stock_ids: route.query.stock_ids,
          period: route.query.period,
        },
        c.signal,
      );
      if (!c.signal.aborted) {
        chain.value = d;
        data.value = r;
      }
    } catch (e) {
      if (!c.signal.aborted)
        error.value = e instanceof Error ? e.message : "比较失败";
    }
  },
  { immediate: true },
);
</script>
<template>
  <section class="compare">
    <RouterLink :to="back" class="back">← 返回产业链分析</RouterLink
    ><span class="eyebrow">同节点 / 公司比较</span>
    <h1>
      {{
        chain?.nodes.find((n) => n.key === data?.node_key)?.name ?? "公司比较"
      }}
    </h1>
    <p v-if="error" role="alert">{{ error }}</p>
    <template v-if="data && chain"
      ><p class="note">
        {{ data.reason }} · 财务报告期 {{ data.period ?? "无共同可比报告期" }} ·
        资料版本
        {{
          data.revision_id.slice(0, 8)
        }}。行情独立标注时间，不据此进行经营排名。
      </p>
      <p v-for="x in data.invalid_items" :key="x.id" role="alert">
        股票 {{ x.id }}：{{ x.reason }}
      </p>
      <div class="compare-grid">
        <article v-for="s in data.items" :key="s.id">
          <RouterLink
            :to="{ path: '/stocks/' + s.id, query: { from: route.fullPath } }"
            ><h2>{{ s.name }} ↗</h2></RouterLink
          ><small>{{ s.ts_code }}</small>
          <div class="quote">
            {{ price(s.close) }} <span>{{ percent(s.pct_chg) }}</span
            ><small><QuoteStamp :stock="s" /></small>
          </div>
          <div v-for="m in s.memberships" :key="m.key">
            <h3>实际业务 · {{ m.mapping_status ?? "资料核验" }}</h3>
            <p>{{ m.business }}</p>
            <small
              >{{ m.subject }} · {{ m.participation }} ·
              {{ m.operating_stage }}</small
            ><ChainCompanyAnalysis
              :messages="m.company_analysis ?? []"
            /><ChainEvidence :evidence="m.evidence" :sources="chain.sources" />
            <h3>财务与报告期</h3>
            <p v-if="!m.metrics.length" class="missing">
              未取得可核验分部收入与占比
            </p>
            <div v-for="(metric, i) in m.metrics" :key="i">
              <p>
                {{ metric.period }} · {{ metric.currency }}
                {{ money(metric.revenue) }} · 占比
                {{ metric.share == null ? "—" : metric.share.toFixed(2) + "%" }}
              </p>
              <small
                >{{ metric.basis }} · 披露
                {{ metric.disclosed_on ?? "未采集" }}</small
              ><ChainEvidence
                :evidence="metric.evidence"
                :sources="chain.sources"
              />
            </div>
            <h3>节点竞争地位</h3>
            <div v-for="(l, i) in m.leaders" :key="i">
              <strong>{{ l.kind }}</strong>
              <p>{{ l.reason }}</p>
              <p v-if="l.freshness">{{ l.freshness }}</p>
              <small>{{ l.product }} · {{ l.geography }} · {{ l.period }}</small
              ><ChainEvidence :evidence="l.evidence" :sources="chain.sources" />
            </div>
          </div>
        </article></div
    ></template>
    <p v-else-if="!error">正在读取同节点公司…</p>
  </section>
</template>
<style scoped>
.compare {
  padding: 24px 22px;
}
.back {
  display: block;
  color: var(--accent);
  font-size: 12px;
  margin-bottom: 26px;
}
h1 {
  font-size: 28px;
  margin: 10px 0 18px;
}
.note {
  font-size: 12px;
  line-height: 1.9;
  color: var(--muted);
  background: var(--subtle);
  padding: 14px;
}
.compare-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
  margin-top: 24px;
}
article {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 22px;
  min-width: 0;
}
h2 {
  font-size: 20px;
  margin: 0 0 8px;
}
h3 {
  font-size: 12px;
  color: var(--muted);
  font-weight: 500;
  margin-top: 24px;
}
p {
  font-size: 13px;
  line-height: 1.9;
}
small {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.8;
}
.quote {
  font-size: 20px;
  border-block: 1px solid var(--line);
  padding: 16px 0;
  margin: 20px 0;
}
.quote span {
  font-size: 13px;
  margin-left: 10px;
}
.quote small {
  display: block;
  margin-top: 7px;
}
.missing {
  color: var(--muted);
}
@media (max-width: 700px) {
  .compare {
    padding: 20px 14px;
  }
  .compare-grid {
    grid-template-columns: 1fr;
  }
  article {
    padding: 18px;
  }
}
</style>
