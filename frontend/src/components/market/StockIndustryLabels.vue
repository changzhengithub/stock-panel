<script setup lang="ts">
import type { Stock } from "../../api";

defineProps<{ stock: Stock }>();
</script>

<template>
  <div class="stock-industries" aria-label="SW2021 行业归属">
    <span class="stock-industry">
      <span class="stock-industry-level">一级</span>
      <span>{{ stock.industry }}</span>
    </span>
    <span class="stock-industry" :class="{ missing: !stock.industry_l2 }">
      <span class="stock-industry-level">二级</span>
      <span>{{ stock.industry_l2 ?? "暂缺" }}</span>
    </span>
  </div>
</template>
