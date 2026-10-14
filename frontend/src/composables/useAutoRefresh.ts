import { onUnmounted } from "vue";

export function useAutoRefresh(refresh: () => void, interval = 30000) {
  const tick = () => {
    if (document.visibilityState === "visible") refresh();
  };
  const timer = setInterval(tick, interval);
  document.addEventListener("visibilitychange", tick);
  onUnmounted(() => {
    clearInterval(timer);
    document.removeEventListener("visibilitychange", tick);
  });
}
