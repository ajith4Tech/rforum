<script lang="ts">
  import { getPageImageUrl } from '$lib/api';
  import PageImageViewer from '$lib/components/PageImageViewer.svelte';
  import { getFitTitleStyle } from '$lib/fitTitle';
  import { Video, Tv, Play } from 'lucide-svelte';

  let {
    slide,
    sessionId,
    sessionCode = '',
    variant = 'screen'
  }: {
    slide: any;
    sessionId?: string;
    sessionCode?: string;
    variant?: 'screen' | 'deck' | 'guest';
  } = $props();

  const layout = $derived(slide?.content_json?.layout || 'title_content');
  const title = $derived(slide?.content_json?.title || '');
  const subtitle = $derived(slide?.content_json?.subtitle || '');
  const body = $derived(slide?.content_json?.body || '');
  const body2 = $derived(slide?.content_json?.body2 || '');
  const videoUrl = $derived(slide?.content_json?.video_url || slide?.content_json?.url || '');
  const playOnDevices = $derived(Boolean(slide?.content_json?.settings?.play_on_participant_devices));
  const resolvedSessionId = $derived(sessionId || slide?.session_id || '');
  const filePage = $derived(slide?.content_json?.file_page || 1);
  const hasImage = $derived(Boolean(slide?.content_json?.file_url || slide?.content_json?.has_file));
  const pageImageSrc = $derived(
    hasImage && resolvedSessionId && slide?.id
      ? getPageImageUrl(resolvedSessionId, slide.id, filePage, sessionCode)
      : ''
  );

  function getEmbedUrl(rawUrl: string): { type: 'iframe' | 'video'; url: string } {
    if (!rawUrl) return { type: 'video', url: '' };
    const u = rawUrl.trim();
    // YouTube
    const ytMatch = u.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|v\/)|youtu\.be\/)([\w-]{11})/i);
    if (ytMatch) {
      return { type: 'iframe', url: `https://www.youtube.com/embed/${ytMatch[1]}?autoplay=0&rel=0` };
    }
    // Vimeo
    const vimeoMatch = u.match(/vimeo\.com\/(?:video\/)?(\d+)/i);
    if (vimeoMatch) {
      return { type: 'iframe', url: `https://player.vimeo.com/video/${vimeoMatch[1]}` };
    }
    return { type: 'video', url: u };
  }
  const embed = $derived(getEmbedUrl(videoUrl));
</script>

{#if layout === 'video'}
  {#if variant === 'guest' && !playOnDevices}
    <!-- Guest view: No auto-play, directed to main screen -->
    <div class="mx-auto flex h-full max-w-lg flex-col items-center justify-center p-6 text-center animate-fade-in my-auto">
      <div class="relative mb-6">
        <div class="absolute -inset-2 rounded-full bg-purple-500/20 blur-lg"></div>
        <div class="relative flex h-20 w-20 items-center justify-center rounded-2xl border border-purple-500/30 bg-purple-500/10 text-purple-600 dark:text-purple-400">
          <Tv class="h-10 w-10" />
        </div>
      </div>
      <span class="inline-flex items-center gap-1.5 rounded-full border border-purple-500/20 bg-purple-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-purple-600 dark:text-purple-400 mb-3">
        <Video class="w-3.5 h-3.5" /> Video Presentation
      </span>
      {#if title}
        <h1 class="font-heading text-xl sm:text-2xl font-bold text-slate-900 dark:text-white leading-tight mb-2" style={getFitTitleStyle(title, 'title')}>
          {title}
        </h1>
      {/if}
      <p class="text-base font-semibold text-slate-800 dark:text-slate-200 mt-2">
        Watch the video on the main screen
      </p>
      {#if subtitle}
        <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">{subtitle}</p>
      {/if}
    </div>
  {:else}
    <!-- Screen / Projector / Moderator Preview -->
    <div class="flex h-full w-full flex-col gap-3 overflow-hidden">
      {#if title}
        <div class="flex-shrink-0 text-center">
          <h1 class="font-heading font-extrabold text-slate-900 dark:text-slate-100 leading-tight text-xl sm:text-2xl" style={getFitTitleStyle(title, 'title')}>
            {title}
          </h1>
          {#if subtitle}
            <p class="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{subtitle}</p>
          {/if}
        </div>
      {/if}
      <div class="flex-1 min-h-0 flex items-center justify-center w-full">
        {#if !videoUrl}
          <div class="flex flex-col items-center justify-center p-8 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 text-center">
            <Video class="w-10 h-10 text-slate-400 mb-2" />
            <p class="text-sm text-slate-500">No video URL configured</p>
          </div>
        {:else if embed.type === 'iframe'}
          <div class="relative w-full h-full max-w-4xl mx-auto rounded-2xl overflow-hidden shadow-2xl bg-black flex items-center justify-center aspect-video">
            <iframe
              src={embed.url}
              title={title || 'Video player'}
              class="w-full h-full border-0 rounded-2xl"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowfullscreen
            ></iframe>
          </div>
        {:else}
          <div class="relative w-full h-full max-w-4xl mx-auto rounded-2xl overflow-hidden shadow-2xl bg-black flex items-center justify-center">
            <video
              src={embed.url}
              controls
              class="w-full h-full object-contain rounded-2xl max-h-full"
              preload="metadata"
            >
              <track kind="captions" />
              Your browser does not support the video tag.
            </video>
          </div>
        {/if}
      </div>
    </div>
  {/if}
{:else if layout === 'image_text'}
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