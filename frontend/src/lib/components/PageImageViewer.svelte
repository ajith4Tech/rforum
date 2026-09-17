<script lang="ts">
  /**
   * Renders a single rendered page image, re-keyed on `page` so the <img> is
   * fully replaced (not just its src swapped) when the page changes — avoids
   * flashing the previous page's image while the new one loads.
   *
   * Auto-retries on failure with exponential backoff (up to MAX_AUTO_RETRIES,
   * total budget ~59s) before showing a visible "couldn't load" state with a
   * manual retry button. The backend lazily renders a page on its first-ever
   * request (LibreOffice/PyMuPDF — see presentations.py's _serve_page_file),
   * which can take a good while under real load on a small host; every
   * request after that is an instant cache hit. Without this, a slow first
   * request (especially on mobile networks, far less patient than desktop)
   * permanently failed with the browser's native broken-image glyph and no
   * way to tell whether it was still trying or had given up — this owns
   * that loading/failure state internally so it works regardless of whether
   * the parent (PresentationLiveView, ContentSlideCanvas) wires onLoad/
   * onError, since neither currently does.
   * Not lazy-loaded: this is always foreground, immediately-visible
   * presentation content, never something scrolled to later, so
   * `loading="lazy"` only adds risk (a mobile browser's intersection
   * heuristics can misjudge visibility for an element freshly inserted
   * inside an animating/CSS-contained container) for no benefit.
   */
  let {
    src,
    page = 1,
    alt = '',
    imgClass = '',
    draggable = false,
    onLoad,
    onError
  }: {
    src: string;
    page?: number;
    alt?: string;
    imgClass?: string;
    draggable?: boolean;
    onLoad?: () => void;
    onError?: () => void;
  } = $props();

  const MAX_AUTO_RETRIES = 6;
  const BASE_DELAY_MS = 2000;
  const MAX_DELAY_MS = 15000;

  let attempt = $state(0);
  let failed = $state(false);
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  // Reset retry/failure state whenever the underlying image identity
  // changes — otherwise a failed/retry count from a previous page/src
  // would carry over onto the new one.
  $effect(() => {
    void src;
    void page;
    attempt = 0;
    failed = false;
    if (retryTimer) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
  });

  function handleLoad() {
    onLoad?.();
  }

  function handleError() {
    if (attempt < MAX_AUTO_RETRIES) {
      const delay = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
      retryTimer = setTimeout(() => { attempt += 1; }, delay);
    } else {
      failed = true;
      onError?.();
    }
  }

  function manualRetry() {
    attempt = 0;
    failed = false;
  }
</script>

{#if failed}
  <div class="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 p-6 text-center {imgClass}">
    <span class="text-sm text-slate-500 dark:text-slate-400">Couldn't load this slide</span>
    <button
      type="button"
      onclick={manualRetry}
      class="text-xs font-semibold text-purple-600 dark:text-purple-400 underline underline-offset-2"
    >
      Tap to retry
    </button>
  </div>
{:else}
  {#key `${src}:${page}:${attempt}`}
    <img {src} {alt} class={imgClass} {draggable} decoding="async" onload={handleLoad} onerror={handleError} />
  {/key}
{/if}