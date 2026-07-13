<script lang="ts">
  /**
   * Renders a single rendered page image, re-keyed on `page` so the <img> is
   * fully replaced (not just its src swapped) when the page changes — avoids
   * flashing the previous page's image while the new one loads.
   */
  let {
    src,
    page = 1,
    alt = '',
    imgClass = '',
    draggable = false,
    onLoad
  }: {
    src: string;
    page?: number;
    alt?: string;
    imgClass?: string;
    draggable?: boolean;
    onLoad?: () => void;
  } = $props();
</script>

{#key page}
  <img {src} {alt} class={imgClass} {draggable} loading="lazy" decoding="async" onload={onLoad} />
{/key}
