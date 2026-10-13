import { computed, onMounted, onUnmounted, shallowRef, type Ref } from "vue";

const MIN_PREVIEW_WIDTH = 215;
const MIN_LIST_WIDTH = 500;
const HANDLE_WIDTH = 8;

export function usePreviewResize(content: Readonly<Ref<HTMLElement | null>>) {
  const previewWidth = shallowRef<number | null>(null);
  const maxPreviewWidth = shallowRef(MIN_PREVIEW_WIDTH);
  const resizing = shallowRef(false);
  let startX = 0;
  let startWidth = 0;
  let observer: ResizeObserver | undefined;
  onMounted(() => {
    if (!content.value) return;
    observer = new ResizeObserver(() => {
      maxPreviewWidth.value = Math.max(
        MIN_PREVIEW_WIDTH,
        content.value!.clientWidth - HANDLE_WIDTH - MIN_LIST_WIDTH,
      );
    });
    observer.observe(content.value);
  });
  onUnmounted(() => observer?.disconnect());
  const visibleWidth = computed(() =>
    Math.min(previewWidth.value ?? 246, maxPreviewWidth.value),
  );

  function currentWidth() {
    return (
      content.value
        ?.querySelector<HTMLElement>(".stock-preview")
        ?.getBoundingClientRect().width ?? MIN_PREVIEW_WIDTH
    );
  }

  function setWidth(width: number) {
    const available =
      (content.value?.clientWidth ?? 0) - HANDLE_WIDTH - MIN_LIST_WIDTH;
    previewWidth.value = Math.round(
      Math.max(MIN_PREVIEW_WIDTH, Math.min(width, available)),
    );
  }

  function startResize(event: PointerEvent) {
    if (event.button !== 0) return;
    startX = event.clientX;
    startWidth = currentWidth();
    resizing.value = true;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function moveResize(event: PointerEvent) {
    if (resizing.value) setWidth(startWidth + startX - event.clientX);
  }

  function stopResize() {
    resizing.value = false;
  }

  function resizeWithKeyboard(event: KeyboardEvent) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    setWidth(currentWidth() + (event.key === "ArrowLeft" ? 20 : -20));
    event.preventDefault();
  }

  return {
    previewWidth,
    maxPreviewWidth,
    visibleWidth,
    resizing,
    startResize,
    moveResize,
    stopResize,
    resizeWithKeyboard,
  };
}
