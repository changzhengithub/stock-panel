import { computed, shallowRef, watch, type Ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { get } from "../api";
import type {
  FundDetail,
  FundHistory,
  FundKind,
  FundPeriod,
  FundRanking,
  FundSort,
  FundStocks,
} from "../api/fundFlow";
import { useAutoRefresh } from "./useAutoRefresh";
import { updateData } from "../utils/updateData";

export function useHotSectors() {
  const route = useRoute(),
    router = useRouter();
  const revision = shallowRef(0),
    result = shallowRef<FundRanking | null>(null),
    error = shallowRef(""),
    loading = shallowRef(false);
  const filters = computed(() => ({
    kind: (route.query.kind === "industry"
      ? "industry"
      : "concept") as FundKind,
    period: (["today", "5d", "10d"].includes(String(route.query.period))
      ? route.query.period
      : "today") as FundPeriod,
    keyword: String(route.query.keyword ?? ""),
    direction: ["in", "out"].includes(String(route.query.direction))
      ? String(route.query.direction)
      : "all",
    sort: ([
      "net_desc",
      "net_asc",
      "rate_desc",
      "rate_asc",
      "pct_desc",
      "pct_asc",
    ].includes(String(route.query.sort))
      ? route.query.sort
      : "net_desc") as FundSort,
    page: Math.max(1, Math.floor(Number(route.query.page)) || 1),
    page_size: [20, 50, 100].includes(Number(route.query.page_size))
      ? Number(route.query.page_size)
      : 20,
  }));
  const selected = computed(() =>
    String(route.params.id || route.query.selected || ""),
  );
  const detailOnly = computed(() => !!route.params.id);
  async function change(patch: Partial<typeof filters.value>) {
    const next = { ...filters.value, ...patch, page: patch.page ?? 1 };
    const selectedId =
      patch.kind !== undefined && patch.kind !== filters.value.kind
        ? undefined
        : selected.value || undefined;
    await router.push({
      path: "/hot-sectors",
      query: { ...next, selected: selectedId },
    });
  }
  function select(id: string) {
    if (window.matchMedia("(max-width: 900px)").matches) {
      return router.push({
        path: `/hot-sectors/${id}`,
        query: { ...route.query, list: route.fullPath },
      });
    }
    return router.replace({ query: { ...route.query, selected: id } });
  }
  let lastKey = "";
  watch(
    [filters, revision, detailOnly],
    async ([f], _old, cleanup) => {
      if (detailOnly.value) return;
      const controller = new AbortController();
      cleanup(() => controller.abort());
      const key = JSON.stringify(f);
      if (lastKey !== key) {
        result.value = null;
        error.value = "";
      }
      lastKey = key;
      loading.value = !result.value;
      try {
        const data = await get<FundRanking>(
          "/hot-sectors?" +
            new URLSearchParams(
              Object.entries(f).map(([k, v]) => [k, String(v)]),
            ),
          controller.signal,
        );
        if (controller.signal.aborted) return;
        updateData(result, data);
        error.value = "";
        if (
          !selected.value &&
          data.items[0] &&
          !window.matchMedia("(max-width: 900px)").matches
        )
          await router.replace({
            query: { ...route.query, selected: data.items[0].id },
          });
      } catch (e) {
        if (!controller.signal.aborted)
          error.value = e instanceof Error ? e.message : "读取失败";
      } finally {
        if (!controller.signal.aborted) loading.value = false;
      }
    },
    { immediate: true },
  );
  useAutoRefresh(() => revision.value++);
  return {
    filters,
    selected,
    detailOnly,
    result,
    loading,
    error,
    change,
    select,
    retry: () => revision.value++,
  };
}

function useFundResource<T>(url: Ref<string>) {
  const data = shallowRef<T | null>(null),
    loading = shallowRef(false),
    error = shallowRef("");
  const revision = shallowRef(0);
  let previous = "";
  watch(
    [url, revision],
    async ([path], _old, cleanup) => {
      const controller = new AbortController();
      cleanup(() => controller.abort());
      if (path !== previous) {
        data.value = null;
        error.value = "";
      }
      previous = path;
      if (!path) return;
      loading.value = !data.value;
      try {
        const next = await get<T>(path, controller.signal);
        if (!controller.signal.aborted) {
          updateData(data, next);
          error.value = "";
        }
      } catch (e) {
        if (!controller.signal.aborted)
          error.value = e instanceof Error ? e.message : "读取失败";
      } finally {
        if (!controller.signal.aborted) loading.value = false;
      }
    },
    { immediate: true },
  );
  useAutoRefresh(() => revision.value++);
  return { data, loading, error, retry: () => revision.value++ };
}
export function useFundDetail(id: Ref<string>, period: Ref<FundPeriod>) {
  const days = shallowRef<20 | 60>(20),
    stockPage = shallowRef(1),
    stockSort = shallowRef<FundSort>("net_desc");
  watch([id, period, stockSort], () => {
    stockPage.value = 1;
  });
  const base = computed(() =>
    id.value ? `/hot-sectors/${encodeURIComponent(id.value)}` : "",
  );
  const detail = useFundResource<FundDetail>(
    computed(() => (base.value ? `${base.value}?period=${period.value}` : "")),
  );
  const history = useFundResource<FundHistory>(
    computed(() =>
      base.value ? `${base.value}/history?days=${days.value}` : "",
    ),
  );
  const stocks = useFundResource<FundStocks>(
    computed(() =>
      base.value
        ? `${base.value}/stocks?period=${period.value}&page=${stockPage.value}&sort=${stockSort.value}`
        : "",
    ),
  );
  return { days, stockPage, stockSort, detail, history, stocks };
}
