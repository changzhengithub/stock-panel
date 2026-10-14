<script setup lang="ts">
import { computed } from "vue";
import type { ChainUpdateStatus } from "../../api/industryChains";
const props = defineProps<{
  status: ChainUpdateStatus | null;
  error: string;
}>();
const stateLabel = computed(() => {
  if (!props.status?.enabled) return "自动更新已关闭";
  return (
    (
      {
        running: "正在更新",
        failed: "更新失败，保留上一份可用分析",
        interrupted: "上一轮中断，等待重试",
        published: "更新完成",
        unchanged: "检查完成，资料无变化",
        pending: "等待首次更新",
      } as Record<string, string>
    )[props.status.state] ?? "等待检查"
  );
});
function time(value: string | null) {
  return value
    ? new Date(value).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        hour12: false,
      })
    : "尚无成功记录";
}
</script>
<template>
  <section class="update-status" aria-label="产业分析更新状态">
    <p v-if="error" role="alert">{{ error }}</p>
    <template v-if="status">
      <div class="status-line">
        <strong>{{ stateLabel }}</strong>
        <span v-if="status.enabled"
          >每 {{ status.interval_hours }} 小时检查</span
        >
        <span>最近成功检查：{{ time(status.last_success_at) }}</span>
      </div>
      <details>
        <summary>更新与证据维护</summary>
        <p v-if="status.next_check_at && status.state !== 'running'">
          下次检查：{{ time(status.next_check_at) }}
        </p>
        <p v-if="status.error" role="alert">{{ status.error }}</p>
        <p>
          行业规则维护日期 {{ status.logic_reviewed_on }}，下次复核
          {{ status.logic_review_due_on
          }}{{ status.logic_review_overdue ? "（已到期）" : "" }}。
        </p>
        <p v-if="status.maintenance">
          龙头依据待复核
          {{ status.maintenance.leader_review_count }} 项，来源待复核
          {{ status.maintenance.source_review_count }} 项。
        </p>
        <p>
          业务与分部资料自动采集，校验通过后切换最新分析。行业逻辑与龙头事实保留来源和适用报告期；来源检查不等于事实核验。
        </p>
      </details>
    </template>
  </section>
</template>
<style scoped>
.update-status {
  padding: 12px 16px;
  margin: 16px 0;
  background: var(--subtle);
  border-left: 3px solid var(--accent);
  font-size: 12px;
  color: var(--muted);
}
.status-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
}
.status-line strong {
  color: var(--text);
}
.update-status details {
  margin-top: 8px;
}
.update-status summary {
  cursor: pointer;
}
.update-status p {
  line-height: 1.8;
  overflow-wrap: anywhere;
}
</style>
