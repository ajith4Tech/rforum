<script lang="ts">
  import { getPageImageUrl } from '$lib/api';
  import PageImageViewer from '$lib/components/PageImageViewer.svelte';
  import { getFitTitleStyle } from '$lib/fitTitle';

  let {
    slide,
    sessionId,
    sessionCode = '',
    variant = 'screen'
  }: {
    slide: any;
    sessionId?: string;
    sessionCode?: string;
    variant?: 'screen' | 'deck';
  } = $props();

  const layout = $derived(slide?.content_json?.layout || 'title_content');
  const title = $derived(slide?.content_json?.title || '');
  const subtitle = $derived(slide?.content_json?.subtitle || '');
  const body = $derived(slide?.content_json?.body || '');
  const body2 = $derived(slide?.content_json?.body2 || '');
  const resolvedSessionId = $derived(sessionId || slide?.session_id || '');
  const filePage = $derived(slide?.content_json?.file_page || 1);
  const hasImage = $derived(Boolean(slide?.content_json?.file_url || slide?.content_json?.has_file));
  const pageImageSrc = $derived(
    hasImage && resolvedSessionId && slide?.id
      ? getPageImageUrl(resolvedSessionId, slide.id, filePage, sessionCode)
      : ''
  );
</script>

{#if layout === 'image_text'}
  <div class={`grid h-full grid-cols-1 gap-5 overflow-hidden lg:grid-cols-12 ${variant === 'deck' ? 'p-0' : ''}`}>
    <div class="flex h-full items-center justify-center overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950/40 lg:col-span-5">
      {#if hasImage && pageImageSrc}
        <PageImageViewer
          src={pageImageSrc}
          page={filePage}
          alt={title || `Slide page ${filePage}`}
          imgClass="max-h-full max-w-full rounded-xl object-contain"
        />
      {:else}
        <div class="text-center text-sm text-slate-400 dark:text-slate-500">No image attached</div>
      {/if}
    </div>
    <div class="flex h-full min-w-0 flex-col justify-center gap-4 overflow-hidden lg:col-span-7">
      {#if title}
        <h1 class="font-heading font-extrabold text-slate-900 dark:text-slate-100 leading-tight" style={getFitTitleStyle(title, 'title')}>
          {title}
        </h1>
      {/if}
      {#if subtitle}
        <p class="text-lg font-medium leading-normal text-slate-600 dark:text-slate-300 sm:text-xl">{subtitle}</p>
      {/if}
      {#if body}
        <div class="prose max-w-none overflow-y-auto text-lg leading-relaxed text-slate-700 dark:prose-invert dark:text-slate-200">
          {@html body}
        </div>
      {/if}
    </div>
  </div>
{:else if layout === 'two_column'}
  <div class="flex h-full flex-col gap-4 overflow-hidden">
    {#if title}
      <h1 class="font-heading font-extrabold text-slate-900 dark:text-slate-100 leading-tight" style={getFitTitleStyle(title, 'title')}>
        {title}
      </h1>
    {/if}
    {#if subtitle}
      <p class="text-lg font-medium leading-normal text-slate-600 dark:text-slate-300 sm:text-xl">{subtitle}</p>
    {/if}
    <div class="grid flex-1 grid-cols-1 gap-4 overflow-hidden lg:grid-cols-2">
      <div class="prose max-w-none overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50 p-4 text-base leading-relaxed text-slate-700 dark:prose-invert dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
        {@html body}
      </div>
      <div class="prose max-w-none overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50 p-4 text-base leading-relaxed text-slate-700 dark:prose-invert dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
        {@html body2}
      </div>
    </div>
  </div>
{:else if layout === 'section'}
  <div class="mx-auto flex h-full max-w-4xl flex-col items-center justify-center rounded-3xl border border-purple-500/20 bg-purple-500/10 p-8 text-center">
    {#if title}
      <h1 class="font-heading font-black tracking-tight text-purple-600 dark:text-purple-400 leading-tight" style={getFitTitleStyle(title, 'title')}>
        {title}
      </h1>
    {/if}
    {#if subtitle}
      <p class="mt-4 text-lg font-medium leading-normal text-slate-600 dark:text-slate-300 sm:text-2xl">{subtitle}</p>
    {/if}
  </div>
{:else if layout === 'title'}
  <div class="mx-auto flex h-full max-w-4xl flex-col items-center justify-center gap-4 text-center">
    {#if title}
      <h1 class="font-heading font-extrabold text-slate-900 dark:text-slate-100 leading-tight" style={getFitTitleStyle(title, 'title')}>
        {title}
      </h1>
    {/if}
    {#if subtitle}
      <p class="text-xl font-medium leading-normal text-slate-600 dark:text-slate-300 sm:text-2xl">{subtitle}</p>
    {/if}
  </div>
{:else if hasImage && pageImageSrc}
  <div class="mx-auto flex h-full max-w-4xl flex-col items-center justify-center gap-4 text-center">
    {#if title}
      <h1 class="font-heading text-2xl font-bold text-slate-900 dark:text-slate-100 sm:text-3xl" style={getFitTitleStyle(title, 'title')}>
        {title}
      </h1>
    {/if}
    {#if subtitle}
      <p class="text-lg font-medium leading-normal text-slate-600 dark:text-slate-300 sm:text-xl">{subtitle}</p>
    {/if}
    <PageImageViewer
      src={pageImageSrc}
      page={filePage}
      alt={title || `Slide page ${filePage}`}
      imgClass="max-h-[75%] w-auto rounded-xl border border-slate-200 object-contain shadow-lg dark:border-slate-800"
    />
  </div>
{:else}
  <div class="mx-auto flex h-full max-w-5xl flex-col justify-center gap-4">
    {#if title}
      <h1 class="font-heading font-extrabold text-slate-900 dark:text-slate-100 leading-tight" style={getFitTitleStyle(title, 'title')}>
        {title}
      </h1>
    {/if}
    {#if subtitle}
      <p class="text-xl font-medium leading-normal text-slate-600 dark:text-slate-300 sm:text-2xl">{subtitle}</p>
    {/if}
    {#if body}
      <div class="prose max-w-none overflow-y-auto text-lg leading-relaxed text-slate-700 dark:prose-invert dark:text-slate-200 sm:text-2xl">
        {@html body}
      </div>
    {/if}
  </div>
{/if}