<script lang="ts">
  /**
   * Shared renderer for the currently active Presentation Timeline item, used
   * by both the guest view (submission forms) and the screen/projector view
   * (results display). Which behavior is used is purely driven by `variant`
   * — everything else (header, waiting states, WS plumbing) stays owned by
   * each route, exactly like the legacy per-slide-type chains they replace.
   */
  import { fade } from 'svelte/transition';
  import { getPresentationPageImageUrl } from '$lib/api';
  import PageImageViewer from '$lib/components/PageImageViewer.svelte';
  import ContentSlideCanvas from '$lib/components/ContentSlideCanvas.svelte';
  import InteractionView from './InteractionView.svelte';

  let {
    activeItem,
    presentationId,
    sessionId = '',
    sessionCode = '',
    responses = [],
    variant = 'guest',
    guestId = '',
    readOnly = false
  }: {
    activeItem: any;
    presentationId: string;
    sessionId?: string;
    sessionCode?: string;
    responses?: any[];
    variant?: 'guest' | 'screen';
    guestId?: string;
    readOnly?: boolean;
  } = $props();

  const isContentSlide = $derived(activeItem?.slide?.type?.toUpperCase() === 'CONTENT');

  const pageImgClass = variant === 'guest'
    ? 'w-full mt-6 rounded-xl border border-slate-200 dark:border-slate-800 select-none pointer-events-none'
    : 'max-h-full max-w-full h-full w-auto object-contain mx-auto';
</script>

{#key activeItem?.id}
  <div class="h-full w-full" in:fade={{ duration: 180 }}>
    {#if activeItem?.item_type === 'PAGE' && activeItem.page}
      <div class={variant === 'guest' ? '' : 'flex h-full w-full items-center justify-center'} style={variant === 'guest' ? '-webkit-touch-callout: none; -webkit-user-select: none;' : ''}>
        <PageImageViewer
          src={getPresentationPageImageUrl(presentationId, activeItem.page.page_number, sessionCode)}
          page={activeItem.page.page_number}
          alt={`Page ${activeItem.page.page_number}`}
          imgClass={pageImgClass}
        />
      </div>
      {#if variant === 'guest'}
        <div class="text-xs text-slate-500 mt-2">Page {activeItem.page.page_number}</div>
      {/if}
    {:else if isContentSlide}
      <ContentSlideCanvas
        slide={activeItem.slide}
        sessionId={sessionId || activeItem.slide?.session_id || ''}
        {sessionCode}
        variant="screen"
      />
    {:else if activeItem?.slide}
      <InteractionView slide={activeItem.slide} {responses} {variant} {guestId} {readOnly} />
    {/if}
  </div>
{/key}
