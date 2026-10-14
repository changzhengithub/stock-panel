<script setup lang="ts">
import { computed } from "vue";
import type { FundMeta } from "../../api/fundFlow";
import { date } from "../../utils/format";
const props = defineProps<{ meta: FundMeta }>();
const stamp = (value: string | null) =>
  value
    ? new Date(value).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        hour12: false,
      })
    : "来源未提供";
const label = computed(() =>
  props.meta.error
    ? "更新失败，保留已有数据"
    : props.meta.pending
      ? "后台获取中"
      : props.meta.stale
        ? "显示旧日期数据"
        : props.meta.batch_id
          ? "已获取"
          : "暂无缓存",
);
</script>
<template>
  <div
    class="fund-status"
    role="status"
    :class="{ warning: meta.error || meta.stale }"
  >
    <span class="status-state">{{ label }}</span>
    <span>统计日期 {{ date(meta.trade_date) }}</span>
    <span v-if="meta.source_as_of"
      >来源时间 {{ stamp(meta.source_as_of) }}</span
    >
    <span v-else>来源未提供精确时间</span>
    <span v-if="meta.fetched_at">获取 {{ stamp(meta.fetched_at) }}</span>
    <span v-if="meta.window_note">{{ meta.window_note }}</span>
    <span>{{ meta.source }}</span>
    <span v-if="meta.missing_count">{{ meta.missing_count }} 项资金缺失</span>
    <span v-if="meta.error" class="status-error"
      >{{ meta.error }}{{ meta.retry_at ? "；系统稍后重试" : "" }}</span
    >
  </div>
</template>
<style scoped>
.fund-status {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.8;
}
.status-state {
  color: var(--accent);
  font-weight: 600;
}
.warning .status-state,
.status-error {
  color: #a56421;
}
.status-error {
  flex-basis: 100%;
}
</style>
