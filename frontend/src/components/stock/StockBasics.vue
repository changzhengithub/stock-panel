<script setup lang="ts">
import type { Stock } from "../../api";
import { date, money } from "../../utils/format";

defineProps<{ stock: Stock; compact?: boolean }>();

function percentage(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(2)}%`;
}

function multiple(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(2)} 倍`;
}

function shares(value: number | null): string {
  return value === null ? "—" : `${money(value)}股`;
}
</script>

<template>
  <section class="stock-basics" :class="{ compact }" aria-label="股票基础数据">
    <header class="basics-heading">
      <h2>交易与估值</h2>
      <span>{{ date(stock.quote_date) }}</span>
    </header>
    <dl class="basics-grid">
      <div>
        <dt>流通市值</dt>
        <dd>{{ money(stock.float_market_cap) }}</dd>
      </div>
      <div>
        <dt>换手率</dt>
        <dd>{{ percentage(stock.turnover_rate) }}</dd>
      </div>
      <div>
        <dt>
          市盈率<small v-if="stock.pe_ratio !== null && stock.pe_basis">{{
            stock.pe_basis
          }}</small>
        </dt>
        <dd>{{ multiple(stock.pe_ratio) }}</dd>
      </div>
      <div>
        <dt>市净率</dt>
        <dd>{{ multiple(stock.pb_ratio) }}</dd>
      </div>
      <div v-if="!compact">
        <dt>总股本</dt>
        <dd>{{ shares(stock.total_shares) }}</dd>
      </div>
      <div v-if="!compact">
        <dt>流通股本</dt>
        <dd>{{ shares(stock.float_shares) }}</dd>
      </div>
    </dl>
    <p v-if="!compact" class="basics-note">
      均为行情日期的快照数据；缺失字段显示“—”。不同数据源的市盈率口径以标签为准。
    </p>
  </section>
</template>

<style scoped>
.stock-basics {
  padding: 21px 23px;
  margin-bottom: 16px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
}
.basics-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 19px;
}
.basics-heading h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
.basics-heading span {
  color: var(--muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.basics-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 21px 14px;
  margin: 0;
}
.basics-grid div {
  min-width: 0;
}
.basics-grid dt {
  margin-bottom: 7px;
  color: var(--muted);
  font-size: 11px;
}
.basics-grid dt small {
  margin-left: 4px;
  font-size: 10px;
}
.basics-grid dd {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.basics-note {
  color: var(--muted);
  font-size: 11px;
  margin: 18px 0 0;
  line-height: 1.6;
}
.stock-basics.compact {
  padding: 15px 0 20px;
  margin: 0 0 21px;
  border: 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
}
.compact .basics-heading {
  margin-bottom: 15px;
}
.compact .basics-heading h2 {
  font-size: 12px;
}
.compact .basics-heading span {
  font-size: 10px;
}
.compact .basics-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 17px 8px;
}
.compact .basics-grid dd {
  font-size: 13px;
}
@media (max-width: 640px) {
  .basics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
