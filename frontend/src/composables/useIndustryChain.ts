import { computed, shallowRef, watch, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  chainGet,
  type ChainCard,
  type ChainDetail,
  type ChainStocks,
  type ChainCatalog,
  type Coverage,
  type ChainUpdateStatus,
} from "../api/industryChains";
import { useAutoRefresh } from "./useAutoRefresh";
export function useIndustryChain() {
  const route = useRoute(),
    router = useRouter();
  const coverage = shallowRef<Coverage | null>(null),
    recommendations = shallowRef<ChainCard[]>([]),
    catalogTotal = shallowRef(0);
  const catalog = shallowRef<ChainCard[]>([]),
    detail = shallowRef<ChainDetail | null>(null),
    stocks = shallowRef<ChainStocks | null>(null);
  const updateStatus = shallowRef<ChainUpdateStatus | null>(null),
    refreshError = shallowRef("");
  const error = shallowRef(""),
    stockError = shallowRef(""),
    searchError = shallowRef(""),
    loading = shallowRef(false),
    searchLoading = shallowRef(false),
    retryVersion = shallowRef(0),
    quoteVersion = shallowRef(0);
  const id = computed(() => String(route.params.id ?? "")),
    revision = computed(() => String(route.query.revision ?? ""));
  const search = computed(() => String(route.query.search ?? ""));
  const selected = computed(
    () =>
      detail.value?.nodes.find(
        (n) =>
          n.key === String(route.query.node ?? detail.value?.nodes[0]?.key),
      ) ?? null,
  );
  const selectedEdge = computed(
    () => detail.value?.edges.find((e) => e.key === route.query.edge) ?? null,
  );
  const full = computed(() => route.query.view === "full"),
    scope = computed(() => (route.query.scope === "chain" ? "chain" : "node"));
  const page = computed(() => Math.max(1, Number(route.query.page) || 1)),
    pageSize = computed(() =>
      [20, 50, 100].includes(Number(route.query.page_size))
        ? Number(route.query.page_size)
        : 20,
    );
  let stockContext = "";
  let restoredScroll = false;
  const filters = computed(() => ({
    q: String(route.query.q ?? ""),
    participation: String(route.query.participation ?? "全部"),
    stage: String(
      route.query.stage ??
        (detail.value?.coverage_level === "baseline" ? "全部" : "经营中"),
    ),
    leader: String(route.query.leader ?? "全部"),
    mapping_status: String(route.query.mapping_status ?? "全部"),
    sort: String(route.query.sort ?? "default"),
  }));
  function change(
    values: Record<string, string | number | undefined>,
    reset = true,
  ) {
    const q = { ...route.query, ...values };
    if (reset) q.page = "1";
    return router.replace({ query: q });
  }
  watch(
    [
      search,
      id,
      () => route.query.industry_id,
      () => route.query.catalog_page,
      quoteVersion,
    ],
    async (_, __, cleanup) => {
      const c = new AbortController();
      cleanup(() => c.abort());
      searchLoading.value = true;
      try {
        const r = await chainGet<ChainCatalog>(
          "",
          {
            q: search.value,
            industry_id:
              route.query.industry_id ??
              (!search.value && /^sw-\d{6}$/.test(id.value)
                ? id.value.slice(3) + ".SI"
                : undefined),
            page: route.query.catalog_page ?? 1,
            page_size: 24,
          },
          c.signal,
        );
        if (!c.signal.aborted) {
          catalog.value = r.items;
          coverage.value = r.coverage;
          recommendations.value = r.recommendations;
          catalogTotal.value = r.total;
          searchError.value = "";
        }
      } catch (e) {
        if (!c.signal.aborted)
          searchError.value = e instanceof Error ? e.message : "行业搜索失败";
      } finally {
        if (!c.signal.aborted) searchLoading.value = false;
      }
    },
    { immediate: true },
  );
  watch(
    [id, revision, retryVersion],
    async (_, __, cleanup) => {
      const c = new AbortController();
      cleanup(() => c.abort());
      if (!id.value) {
        detail.value = null;
        stocks.value = null;
        error.value = "";
        return;
      }
      const same =
        detail.value?.id === id.value &&
        (!revision.value || detail.value?.revision_id === revision.value);
      if (!same) {
        detail.value = null;
        stocks.value = null;
        error.value = "";
      }
      loading.value = !detail.value;
      try {
        const r = await chainGet<ChainDetail>(
          "/" + id.value,
          { revision: revision.value },
          c.signal,
        );
        if (c.signal.aborted) return;
        detail.value = r;
        error.value = "";
        // An absent revision means follow latest; only explicit history links pin content.
        const patch: Record<string, string | undefined> = {};
        if (
          route.query.node &&
          !r.nodes.some((n) => n.key === route.query.node)
        )
          patch.node = r.nodes[0]?.key;
        if (
          route.query.edge &&
          !r.edges.some((e) => e.key === route.query.edge)
        )
          patch.edge = undefined;
        if (Object.keys(patch).length) await change(patch);
      } catch (e) {
        if (!c.signal.aborted)
          error.value = e instanceof Error ? e.message : "读取产业链失败";
      } finally {
        if (!c.signal.aborted) loading.value = false;
      }
    },
    { immediate: true },
  );
  watch(
    [id, quoteVersion],
    async (_, __, cleanup) => {
      const c = new AbortController();
      cleanup(() => c.abort());
      const identity = id.value;
      const results = await Promise.allSettled([
        chainGet<ChainUpdateStatus>("/update-status", {}, c.signal),
        identity
          ? chainGet<{ revision_id: string }>(
              "/" + identity + "/version",
              {},
              c.signal,
            )
          : Promise.resolve(null),
      ]);
      if (c.signal.aborted) return;
      const [state, version] = results;
      const failed = results.find((r) => r.status === "rejected");
      refreshError.value =
        failed?.status === "rejected"
          ? "更新状态读取失败，保留当前内容：" +
            String(failed.reason?.message ?? failed.reason)
          : "";
      if (state.status === "fulfilled") updateStatus.value = state.value;
      if (
        version.status === "fulfilled" &&
        version.value &&
        detail.value?.id === identity
      ) {
        const latest = version.value.revision_id;
        if (!revision.value && detail.value.revision_id !== latest)
          retryVersion.value++;
        else if (detail.value.current_revision_id !== latest)
          detail.value = { ...detail.value, current_revision_id: latest };
      }
    },
    { immediate: true },
  );
  watch(
    [detail, selected, scope, filters, page, pageSize, quoteVersion],
    async (_, __, cleanup) => {
      const c = new AbortController();
      cleanup(() => c.abort());
      if (!detail.value || (scope.value === "node" && !selected.value)) {
        stocks.value = null;
        return;
      }
      const rid = detail.value.revision_id;
      const context = JSON.stringify([
        id.value,
        rid,
        scope.value,
        selected.value?.key,
        filters.value,
        page.value,
        pageSize.value,
      ]);
      if (stockContext !== context || stocks.value?.revision_id !== rid)
        stocks.value = null;
      stockContext = context;
      try {
        const r = await chainGet<ChainStocks>(
          "/" + id.value + "/stocks",
          {
            revision: rid,
            node_key: scope.value === "node" ? selected.value?.key : undefined,
            ...filters.value,
            page: page.value,
            page_size: pageSize.value,
          },
          c.signal,
        );
        if (!c.signal.aborted) {
          stocks.value = r;
          stockError.value = "";
          if (!restoredScroll) {
            restoredScroll = true;
            await nextTick();
            try {
              const top = Number(
                sessionStorage.getItem("chain-scroll:" + route.fullPath),
              );
              if (top > 0)
                requestAnimationFrame(() => {
                  if (!c.signal.aborted) window.scrollTo({ top });
                });
            } catch {
              /* optional view restoration */
            }
          }
        }
      } catch (e) {
        if (!c.signal.aborted)
          stockError.value =
            e instanceof Error ? e.message : "股票列表读取失败";
      }
    },
    { immediate: true },
  );
  useAutoRefresh(() => {
    quoteVersion.value++;
  });
  return {
    route,
    router,
    catalog,
    coverage,
    recommendations,
    catalogTotal,
    detail,
    stocks,
    error,
    stockError,
    searchError,
    loading,
    updateStatus,
    refreshError,
    revision,
    searchLoading,
    id,
    search,
    selected,
    selectedEdge,
    full,
    scope,
    page,
    pageSize,
    filters,
    change,
    retry: () => retryVersion.value++,
  };
}
