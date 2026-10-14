<script setup lang="ts">
import type { Evidence, ChainSource } from "../../api/industryChains";
function snapshotHref(source: ChainSource) {
  const code = /^company-(\d{6})-(sh|sz|bj)$/.exec(source.id);
  return code && source.snapshot_hash
    ? "/api/industry-chains/business/" +
        code[1] +
        "." +
        code[2]!.toUpperCase() +
        "?snapshot=" +
        source.snapshot_hash
    : "";
}
defineProps<{ evidence: Evidence[]; sources: ChainSource[] }>();
</script>
<template>
  <details class="evidence">
    <summary>资料依据 · {{ evidence.length }} 项</summary>
    <div v-for="(e, i) in evidence" :key="i" class="citation">
      <a
        v-if="sources.find((s) => s.id === e.source_id)"
        :href="sources.find((s) => s.id === e.source_id)!.url"
        target="_blank"
        rel="noopener noreferrer"
        >{{ sources.find((s) => s.id === e.source_id)!.title }} ↗</a
      >
      <p>{{ e.locator }} · {{ e.summary }}</p>
      <template
        v-for="src in sources.filter(
          (s) => s.id === e.source_id && s.snapshot_hash,
        )"
        :key="src.id"
        ><small>快照 SHA256 {{ src.snapshot_hash?.slice(0, 16) }}…</small>
        <a
          v-if="src.category === 'vendor' && snapshotHref(src)"
          :href="snapshotHref(src)"
          target="_blank"
          rel="noopener noreferrer"
          >查看取得时的业务与财务快照 ↗</a
        ></template
      >
      <small
        >发布
        {{
          sources.find((s) => s.id === e.source_id)?.published_on ??
          "来源未注明"
        }}
        · 取得 {{ sources.find((s) => s.id === e.source_id)?.retrieved_on }} ·
        {{
          sources.find((s) => s.id === e.source_id)?.category === "vendor"
            ? "数据商汇总快照，原始公告待核验"
            : sources.find((s) => s.id === e.source_id)?.category ===
                "framework"
              ? "经营活动范围依据；节点关系为分析整理"
              : sources.find((s) => s.id === e.source_id)?.access_status ===
                  "search_verified"
                ? "官方来源检索核对，全文访问受限"
                : "来源已访问核对"
        }}</small
      >
    </div>
  </details>
</template>
<style scoped>
.evidence {
  margin-top: 12px;
  font-size: 12px;
  color: var(--muted);
}
summary {
  cursor: pointer;
  color: var(--accent);
}
.citation {
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
}
.citation a {
  color: var(--accent);
  overflow-wrap: anywhere;
}
.citation p {
  line-height: 1.6;
  margin: 6px 0;
}
.citation small {
  line-height: 1.7;
}
</style>
