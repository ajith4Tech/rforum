<script lang="ts">
  /**
   * Wraps PageImageViewer with zoom in/out, fit-to-screen, and a scrollable
   * viewport for panning while zoomed in. Fullscreen is handled one level up
   * (the containing workspace goes fullscreen, not the image itself) so this
   * stays a plain zoom widget usable in both the presentation-timeline canvas
   * and the legacy content-slide viewer.
   */
  import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-svelte';
  import PageImageViewer from './PageImageViewer.svelte';

  let {
    src,
    page = 1,
    alt = '',
    imgClass = 'rounded-xl border border-surface-200 dark:border-surface-800',
    onLoad,
    onError
  }: {
    src: string;
    page?: number;
    alt?: string;
    imgClass?: string;
    onLoad?: () => void;
    onError?: () => void;
  } = $props();

  const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3] as const;
  const FIT_INDEX = 2; // 1.0x — used as the baseline when leaving fit mode

  let zoomIndex = $state(FIT_INDEX);
  let fit = $state(true);
  const zoom = $derived(fit ? 1 : ZOOM_STEPS[zoomIndex]);
  const canZoomOut = $derived(fit || zoomIndex > 0);
  const canZoomIn = $derived(fit || zoomIndex < ZOOM_STEPS.length - 1);

  function zoomIn() {
    fit = false;
    zoomIndex = Math.min(zoomIndex + 1, ZOOM_STEPS.length - 1);
  }
  function zoomOut() {
    fit = false;
    zoomIndex = Math.max(zoomIndex - 1, 0);
  }
  function resetFit() {
    fit = true;
    zoomIndex = FIT_INDEX;
  }
</script>

<div>
  <div class="flex items-center justify-center gap-1 mb-2" role="group" aria-label="Zoom controls">
    <button
      type="button"
      onclick={zoomOut}
      disabled={!canZoomOut}
      class="p-1.5 rounded-lg text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800 transition disabled:opacity-30 disabled:pointer-events-none"
      aria-label="Zoom out"
      title="Zoom out"
    >
      <ZoomOut class="w-4 h-4" />
    </button>
    <button
      type="button"
      onclick={resetFit}
      aria-pressed={fit}
      class="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition {fit
        ? 'bg-brand-500 text-white'
        : 'text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800'}"
      aria-label="Fit to screen"
      title="Fit to screen"
    >
      <Maximize2 class="w-3.5 h-3.5" /> Fit
    </button>
    <span class="text-xs text-surface-400 tabular-nums w-10 text-center" aria-live="polite">{Math.round(zoom * 100)}%</span>
    <button
      type="button"
      onclick={zoomIn}
      disabled={!canZoomIn}
      class="p-1.5 rounded-lg text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800 transition disabled:opacity-30 disabled:pointer-events-none"
      aria-label="Zoom in"
      title="Zoom in"
    >
      <ZoomIn class="w-4 h-4" />
    </button>
  </div>
  <div class="overflow-auto max-h-[70vh] rounded-xl">
    <div class="flex justify-center py-1" style={fit ? undefined : `transform: scale(${zoom}); transform-origin: top center;`}>
      <PageImageViewer {src} {page} {alt} imgClass={fit ? `max-h-[70vh] max-w-full ${imgClass}` : imgClass} {onLoad} {onError} />
    </div>
  </div>
</div>
