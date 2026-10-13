import { computed, onUnmounted, shallowRef, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  get,
  type Filters,
  type Industry,
  type Concept,
  type StockResult,
  type DataStatus,
} from "../api";
import {
  isBoardInExchange,
  boardsForExchange,
  MARKET_OPTIONS,
  type Exchange,
} from "../marketOptions";
import { useLibrary } from "./useLibrary";
export function useMarket() {
  const { favorites } = useLibrary();
  const route = useRoute(),
    router = useRouter();
  const result = shallowRef<StockResult | null>(null),
    level1Industries = shallowRef<Industry[]>([]),
    level2Industries = shallowRef<Industry[]>([]),
    concepts = shallowRef<Concept[]>([]),
    status = shallowRef<DataStatus | null>(null);
  const loading = shallowRef(false),
    error = shallowRef(""),
    revision = shallowRef(0);
  const filters = computed<Filters>(() => {
    const q = route.query;
    const industry_level = q.industry_level === "2" ? 2 : 1;
    const scope = q.scope === "representatives" ? "representatives" : "all";
    const sort = (
      [
        "default",
        "pct_desc",
        "pct_asc",
        "market_cap_desc",
        "market_cap_asc",
        "close_desc",
        "close_asc",
        "amount_desc",
        "amount_asc",
        "turnover_desc",
        "turnover_asc",
      ].includes(String(q.sort))
        ? q.sort
        : "default"
    ) as Filters["sort"];
    let exchange = MARKET_OPTIONS.some((item) => item.value === q.exchange)
      ? (q.exchange as Exchange)
      : "";
    let board = isBoardInExchange(exchange, String(q.board ?? ""))
      ? String(q.board ?? "")
      : "";
    if (!exchange && board) {
      exchange =
        board === "北交所"
          ? "BSE"
          : (MARKET_OPTIONS.find(
              (option) =>
                option.value && boardsForExchange(option.value).includes(board),
            )?.value ?? "");
    }
    if (exchange === "BSE") board = "";
    return {
      view: q.view === "concept" || q.concept_id ? "concept" : "industry",
      keyword: String(q.keyword ?? ""),
      industry_id: String(q.industry_id ?? ""),
      concept_id: String(q.concept_id ?? ""),
      industry_level,
      exchange,
      board,
      scope: q.view === "concept" || q.concept_id ? "all" : scope,
      collection: q.collection === "favorites" ? "favorites" : "all",
      sort,
      page: Number.isFinite(Number(q.page))
        ? Math.max(1, Math.floor(Number(q.page)) || 1)
        : 1,
      page_size: [20, 50, 100].includes(Number(q.page_size))
        ? Number(q.page_size)
        : 50,
    };
  });
  const industries = computed(() =>
    filters.value.industry_level === 2
      ? level2Industries.value
      : level1Industries.value,
  );
  async function change(patch: Partial<Filters>) {
    const next = { ...filters.value, ...patch, page: patch.page ?? 1 };
    if (patch.view && patch.view !== filters.value.view) {
      next.industry_id = "";
      next.concept_id = "";
      next.scope = "all";
    }
    if (patch.concept_id !== undefined) {
      next.view = "concept";
      next.industry_id = "";
      next.scope = "all";
    }
    if (patch.industry_id !== undefined) {
      next.view = "industry";
      next.concept_id = "";
    }
    if (
      patch.exchange !== undefined &&
      patch.exchange !== filters.value.exchange &&
      patch.board === undefined
    ) {
      next.board = "";
    }
    if (!isBoardInExchange(next.exchange, next.board)) next.board = "";
    if (
      patch.industry_level !== undefined &&
      patch.industry_level !== filters.value.industry_level
    ) {
      if (patch.industry_id === undefined) next.industry_id = "";
    }
    next.page_size = [20, 50, 100].includes(next.page_size)
      ? next.page_size
      : 50;
    await router.replace({
      path: "/market",
      query: Object.fromEntries(
        Object.entries(next).filter(([, v]) => v !== ""),
      ),
    });
  }
  watch(
    [() => route.fullPath, revision, favorites],
    async (_v, _old, cleanup) => {
      if (route.query.collection === "recent") {
        await router.replace({
          path: "/market",
          query: { ...route.query, collection: undefined },
        });
        return;
      }
      if (
        String(route.query.exchange ?? "") !== filters.value.exchange ||
        String(route.query.board ?? "") !== filters.value.board
      ) {
        await router.replace({
          path: "/market",
          query: {
            ...route.query,
            exchange: filters.value.exchange || undefined,
            board: filters.value.board || undefined,
          },
        });
        return;
      }
      const controller = new AbortController();
      cleanup(() => controller.abort());
      loading.value = true;
      error.value = "";
      const params = new URLSearchParams();
      Object.entries(filters.value).forEach(([k, v]) => {
        if (v !== "") params.set(k, String(v));
      });
      if (filters.value.collection === "favorites")
        params.set("codes", favorites.value.map((s) => s.ts_code).join(","));
      const industryParams = new URLSearchParams();
      if (filters.value.exchange) {
        industryParams.set("exchange", filters.value.exchange);
      }
      if (filters.value.board) {
        industryParams.set("board", filters.value.board);
      }
      try {
        const [firstLevel, secondLevel, conceptRows, health] =
          await Promise.all([
            get<Industry[]>(
              `/industries?level=1&${industryParams}`,
              controller.signal,
            ),
            get<Industry[]>(
              `/industries?level=2&${industryParams}`,
              controller.signal,
            ),
            get<Concept[]>(`/concepts?${industryParams}`, controller.signal),
            get<DataStatus>("/data-status", controller.signal),
          ]);
        if (controller.signal.aborted) return;
        level1Industries.value = firstLevel;
        level2Industries.value = secondLevel;
        concepts.value = conceptRows;
        status.value = health;
        result.value = await get<StockResult>(
          "/stocks?" + params,
          controller.signal,
        );
      } catch (e) {
        if (!controller.signal.aborted)
          error.value = e instanceof Error ? e.message : "加载失败";
      } finally {
        if (!controller.signal.aborted) loading.value = false;
      }
    },
    { immediate: true },
  );
  const timer = setInterval(() => revision.value++, 30000);
  onUnmounted(() => clearInterval(timer));
  function open(stockId: number) {
    router.push({
      path: `/stocks/${stockId}`,
      query: { from: route.fullPath },
    });
  }
  function reset() {
    router.replace({
      path: "/market",
      query: {
        scope: "all",
        collection: "all",
        keyword: filters.value.keyword,
        industry_level: filters.value.industry_level,
      },
    });
  }
  return {
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
    retry: () => revision.value++,
  };
}
