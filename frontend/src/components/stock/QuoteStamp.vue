<script setup lang="ts">
import type { Stock } from "../../api";
import { quoteTime } from "../../utils/format";
defineProps<{ stock: Stock }>();
</script>

<template>
  <span :title="stock.quote_source ?? undefined">
    {{ stock.quote_mode === "live" ? "最新价" : "收盘价" }} ·
    {{
      stock.quote_date
        ? quoteTime(stock.quote_date, stock.quote_time)
        : "暂无当日行情"
    }}
    <template v-if="stock.quote_stale"> · 更新延迟或异常</template>
  </span>
</template>
