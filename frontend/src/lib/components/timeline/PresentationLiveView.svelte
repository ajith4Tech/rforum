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
  import InteractionView from './InteractionView.svelte';

  let {
    activeItem,
    presentationId,
    sessionCode = '',
    responses = [],
    variant = 'guest',
    guestId = '',
    readOnly = false
  }: {
    activeItem: any;
    presentationId: string;
    /** The session's join code — proves to the unauthenticated page-image endpoint that this guest/screen belongs to a live session this presentation is attached to. */
    sessionCode?: string;
    responses?: any[];
    variant?: 'guest' | 'screen';
    guestId?: string;
    /** Moderator Preview mode: render exactly as guests/screens would, but never submit. */
    readOnly?: boolean;
  } = $props();

  const pageImgClass = variant === 'guest'
    ? 'w-full mt-6 rounded-xl border border-slate-200 dark:border-slate-800 select-none pointer-events-none'
    : 'max-w-full max-h-[65vh] w-auto rounded-2xl border border-white/10 object-contain shadow-2xl mx-auto';
</script>

{#key activeItem?.id}
  <div in:fade={{ duration: 180 }}>
    {#if activeItem?.item_type === 'PAGE' && activeItem.page}
      <div class={variant === 'guest' ? '' : 'w-full flex flex-col items-center gap-4 max-h-[70vh]'} style={variant === 'guest' ? '-webkit-touch-callout: none; -webkit-user-select: none;' : ''}>
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
    {:else if activeItem?.slide}
      <InteractionView slide={activeItem.slide} {responses} {variant} {guestId} {readOnly} />
    {/if}
  </div>
{/key}
