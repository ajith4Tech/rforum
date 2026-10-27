<script lang="ts">
  import { getPageImageUrl } from '$lib/api';
  import PageImageViewer from '$lib/components/PageImageViewer.svelte';
  import { getFitTitleStyle } from '$lib/fitTitle';
  import { sanitizeRichHtml } from '$lib/sanitizeHtml';
  import { Video, Tv } from 'lucide-svelte';

  let {
    slide,
    sessionId,
    sessionCode = '',
    variant = 'screen',
    // Deck variant: called when the moderator performs a playback action.
    onVideoControl = undefined,
    // Screen/guest variant: incoming video command object to mirror.
    videoCommand = undefined,
  }: {
    slide: any;
    sessionId?: string;
    sessionCode?: string;
    variant?: 'screen' | 'deck' | 'guest';
    onVideoControl?: (payload: VideoControlPayload) => void;
    videoCommand?: VideoControlPayload | null;
  } = $props();

  export type VideoControlPayload = {
    /** ID of the slide this command belongs to — screen must ignore foreign slide IDs. */
    slide_id: string;
    action: 'play' | 'pause' | 'seek' | 'volume';
    /** Playback position in seconds (for seek / play-from-position). */
    position?: number;
    /** Volume 0‒1 (for volume). */
    volume?: number;
    /** Whether audio is muted (sent alongside volume). */
    muted?: boolean;
  };

  const layout = $derived(slide?.content_json?.layout || 'title_content');
  const title = $derived(slide?.content_json?.title || '');
  const subtitle = $derived(slide?.content_json?.subtitle || '');
  // Rich text is rendered as HTML on guest phones and the projector — only
  // ever through the allowlist sanitizer (see $lib/sanitizeHtml).
  const body = $derived(sanitizeRichHtml(slide?.content_json?.body));
  const body2 = $derived(sanitizeRichHtml(slide?.content_json?.body2));
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

  // ─── Embed type detection ───────────────────────────────────────────────────
  type EmbedResult = { type: 'iframe'; url: string; provider: 'youtube' | 'vimeo' } | { type: 'video'; url: string; provider: 'native' };

  function getEmbedUrl(rawUrl: string): EmbedResult {
    if (!rawUrl) return { type: 'video', url: '', provider: 'native' };
    const u = rawUrl.trim();
    const controlsParam = variant === 'deck' ? '1' : '0';
    // YouTube
    const ytMatch = u.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|v\/)|youtu\.be\/)([\w-]{11})/i);
    if (ytMatch) {
      // enablejsapi=1 is required so the YT IFrame API can control / observe this player.
      return {
        type: 'iframe',
        provider: 'youtube',
        url: `https://www.youtube.com/embed/${ytMatch[1]}?autoplay=0&rel=0&controls=${controlsParam}&disablekb=${variant === 'deck' ? '0' : '1'}&enablejsapi=1`,
      };
    }
    // Vimeo
    const vimeoMatch = u.match(/vimeo\.com\/(?:video\/)?(\d+)/i);
    if (vimeoMatch) {
      return {
        type: 'iframe',
        provider: 'vimeo',
        url: `https://player.vimeo.com/video/${vimeoMatch[1]}?controls=${controlsParam}`,
      };
    }
    return { type: 'video', url: u, provider: 'native' };
  }
  const embed = $derived(getEmbedUrl(videoUrl));

  // ─── Native <video> element refs ────────────────────────────────────────────
  let nativeVideoEl: HTMLVideoElement | null = $state(null);

  // ─── iframe ref (shared for YouTube & Vimeo) ────────────────────────────────
  let iframeEl: HTMLIFrameElement | null = $state(null);

  // ─── YouTube IFrame API player instance ─────────────────────────────────────
  // ytReady / vimeoPlayer are reactive so the videoCommand $effect below re-runs
  // once the player becomes usable: the API script + player init take a moment
  // after the slide appears, and a play pressed by the moderator in that window
  // would otherwise be dropped for good on the screen.
  let ytPlayer: any = null;
  let ytReady = $state(false);

  // ─── Vimeo Player instance ──────────────────────────────────────────────────
  let vimeoPlayer: any = $state.raw(null);

  // ─── Throttle / dedupe helpers ───────────────────────────────────────────────
  /** True while we are programmatically applying an incoming command so we
   *  don't echo it back out as a new event. */
  let applyingCommand = false;

  function sendVideoControl(payload: Omit<VideoControlPayload, 'slide_id'>) {
    if (applyingCommand) return;
    if (!onVideoControl || !slide?.id) return;
    onVideoControl({ slide_id: slide.id, ...payload });
  }

  // ─── Blocked playback (screen variant) ───────────────────────────────────────
  // Browsers refuse to start playback with sound until the page has had a user
  // gesture (autoplay policy) — a freshly opened projector tab usually has
  // none. Instead of failing silently (or forcing mute, which would change the
  // room's audio), show a one-click prompt that resumes at the moderator's
  // current position. `currentPlayAttempt` identifies the latest play attempt
  // so a rejection that arrives after a newer command is ignored.
  let playbackBlocked = $state(false);
  let currentPlayAttempt: VideoControlPayload | null = null;
  let blockedPlay: { cmd: VideoControlPayload; at: number } | null = null;

  function markPlaybackBlocked(cmd: VideoControlPayload) {
    if (cmd !== currentPlayAttempt) return;
    blockedPlay = { cmd, at: performance.now() };
    playbackBlocked = true;
  }

  function isAutoplayRejection(err: any): boolean {
    return err?.name === 'NotAllowedError';
  }

  function resumeBlockedPlayback() {
    const pending = blockedPlay;
    playbackBlocked = false;
    blockedPlay = null;
    if (!pending || pending.cmd !== currentPlayAttempt) return;
    // The moderator's player kept running since the refused attempt.
    const elapsed = (performance.now() - pending.at) / 1000;
    const cmd: VideoControlPayload = { ...pending.cmd, position: (pending.cmd.position ?? 0) + elapsed };
    currentPlayAttempt = cmd;
    // Applied synchronously inside this click so it counts as user-initiated.
    if (embed.provider === 'native') applyCommandToNative(cmd);
    else if (embed.provider === 'youtube') applyCommandToYt(cmd);
    else if (embed.provider === 'vimeo') applyCommandToVimeo(cmd);
  }

  // ─── Native video event handlers ─────────────────────────────────────────────
  function onNativePlay() {
    sendVideoControl({ action: 'play', position: nativeVideoEl?.currentTime ?? 0 });
  }
  function onNativePause() {
    sendVideoControl({ action: 'pause', position: nativeVideoEl?.currentTime ?? 0 });
  }
  function onNativeSeeked() {
    sendVideoControl({ action: 'seek', position: nativeVideoEl?.currentTime ?? 0 });
  }
  function onNativeVolumeChange() {
    sendVideoControl({
      action: 'volume',
      volume: nativeVideoEl?.volume ?? 1,
      muted: nativeVideoEl?.muted ?? false,
    });
  }

  function attachNativeListeners(el: HTMLVideoElement) {
    el.addEventListener('play', onNativePlay);
    el.addEventListener('pause', onNativePause);
    el.addEventListener('seeked', onNativeSeeked);
    el.addEventListener('volumechange', onNativeVolumeChange);
  }

  function detachNativeListeners(el: HTMLVideoElement) {
    el.removeEventListener('play', onNativePlay);
    el.removeEventListener('pause', onNativePause);
    el.removeEventListener('seeked', onNativeSeeked);
    el.removeEventListener('volumechange', onNativeVolumeChange);
  }

  // ─── YouTube IFrame API setup ────────────────────────────────────────────────
  // We load the API script once globally and store pending ready-callbacks.
  declare global {
    interface Window {
      YT: any;
      onYouTubeIframeAPIReady: (() => void) | undefined;
      _ytApiLoading: boolean;
      _ytReadyCallbacks: (() => void)[];
      Vimeo: any;
    }
  }

  function ensureYtApi(cb: () => void) {
    if (typeof window === 'undefined') return;
    if (window.YT?.Player) { cb(); return; }
    if (!window._ytReadyCallbacks) window._ytReadyCallbacks = [];
    window._ytReadyCallbacks.push(cb);
    if (!window._ytApiLoading) {
      window._ytApiLoading = true;
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        prev?.();
        (window._ytReadyCallbacks || []).forEach((fn) => fn());
        window._ytReadyCallbacks = [];
      };
      const s = document.createElement('script');
      s.src = 'https://www.youtube.com/iframe_api';
      document.head.appendChild(s);
    }
  }

  // The YouTube IFrame API has no seek event, and scrubbing while paused
  // fires no state change — so on the moderator's deck, poll the position
  // while paused/cued and report jumps as seeks. (Seeks while playing already
  // arrive as BUFFERING → PLAYING with the new position.)
  let ytSeekPoll: ReturnType<typeof setInterval> | null = null;
  function startYtSeekPoll() {
    stopYtSeekPoll();
    let lastTime = ytPlayer?.getCurrentTime?.() ?? 0;
    ytSeekPoll = setInterval(() => {
      if (!ytPlayer) return;
      const time = ytPlayer.getCurrentTime?.() ?? 0;
      const state = ytPlayer.getPlayerState?.();
      const states = window.YT?.PlayerState;
      if (states && (state === states.PAUSED || state === states.CUED) && Math.abs(time - lastTime) > 1) {
        sendVideoControl({ action: 'seek', position: time });
      }
      lastTime = time;
    }, 500);
  }
  function stopYtSeekPoll() {
    if (ytSeekPoll) clearInterval(ytSeekPoll);
    ytSeekPoll = null;
  }

  function initYtPlayer(iframe: HTMLIFrameElement) {
    ensureYtApi(() => {
      if (!iframe.isConnected) return;
      ytPlayer = new window.YT.Player(iframe, {
        events: {
          onReady: () => {
            ytReady = true;
            if (variant === 'deck' && onVideoControl) startYtSeekPoll();
          },
          onStateChange: (e: any) => {
            if (variant !== 'deck' || !onVideoControl) return;
            const YT_STATES = window.YT.PlayerState;
            if (e.data === YT_STATES.PLAYING) {
              sendVideoControl({ action: 'play', position: ytPlayer.getCurrentTime?.() ?? 0 });
            } else if (e.data === YT_STATES.PAUSED) {
              sendVideoControl({ action: 'pause', position: ytPlayer.getCurrentTime?.() ?? 0 });
            } else if (e.data === YT_STATES.ENDED) {
              sendVideoControl({ action: 'pause', position: 0 });
            }
          },
        },
      });
    });
  }

  // ─── Vimeo Player API setup ──────────────────────────────────────────────────
  function ensureVimeoApi(cb: () => void) {
    if (typeof window === 'undefined') return;
    if (window.Vimeo?.Player) { cb(); return; }
    const existing = document.getElementById('vimeo-player-api');
    if (!existing) {
      const s = document.createElement('script');
      s.id = 'vimeo-player-api';
      s.src = 'https://player.vimeo.com/api/player.js';
      s.onload = cb;
      document.head.appendChild(s);
    } else {
      // Script tag exists but not yet loaded — poll briefly
      const poll = setInterval(() => {
        if (window.Vimeo?.Player) { clearInterval(poll); cb(); }
      }, 100);
    }
  }

  function initVimeoPlayer(iframe: HTMLIFrameElement) {
    ensureVimeoApi(() => {
      if (!iframe.isConnected) return;
      vimeoPlayer = new window.Vimeo.Player(iframe);
      if (variant === 'deck' && onVideoControl) {
        vimeoPlayer.on('play', (data: any) => {
          sendVideoControl({ action: 'play', position: data.seconds ?? 0 });
        });
        vimeoPlayer.on('pause', (data: any) => {
          sendVideoControl({ action: 'pause', position: data.seconds ?? 0 });
        });
        vimeoPlayer.on('seeked', (data: any) => {
          sendVideoControl({ action: 'seek', position: data.seconds ?? 0 });
        });
        vimeoPlayer.on('volumechange', (data: any) => {
          sendVideoControl({ action: 'volume', volume: data.volume, muted: data.muted });
        });
      }
    });
  }

  // ─── Apply incoming command to native video (screen variant) ─────────────────
  function applyCommandToNative(cmd: VideoControlPayload): boolean {
    if (!nativeVideoEl) return false;
    applyingCommand = true;
    try {
      if (cmd.action === 'play') {
        if (cmd.position !== undefined) nativeVideoEl.currentTime = cmd.position;
        nativeVideoEl.play().catch((err) => {
          if (isAutoplayRejection(err)) markPlaybackBlocked(cmd);
          // AbortError = interrupted by a newer pause/load — expected.
          else if (err?.name !== 'AbortError') console.warn('[video] native playback failed', err);
        });
      } else if (cmd.action === 'pause') {
        if (cmd.position !== undefined) nativeVideoEl.currentTime = cmd.position;
        nativeVideoEl.pause();
      } else if (cmd.action === 'seek') {
        if (cmd.position !== undefined) nativeVideoEl.currentTime = cmd.position;
      } else if (cmd.action === 'volume') {
        if (cmd.volume !== undefined) nativeVideoEl.volume = cmd.volume;
        if (cmd.muted !== undefined) nativeVideoEl.muted = cmd.muted;
      }
    } finally {
      // Release the guard after a tick so the resulting media events don't
      // echo back as a new outbound control.
      setTimeout(() => { applyingCommand = false; }, 0);
    }
    return true;
  }

  // ─── Apply incoming command to YouTube player (screen variant) ───────────────
  function applyCommandToYt(cmd: VideoControlPayload): boolean {
    // Read ytReady first so the calling $effect always tracks it.
    if (!ytReady || !ytPlayer) return false;
    applyingCommand = true;
    try {
      if (cmd.action === 'play') {
        if (cmd.position !== undefined) ytPlayer.seekTo?.(cmd.position, true);
        ytPlayer.playVideo?.();
        // playVideo() has no result; a refused autoplay just never reaches
        // PLAYING/BUFFERING. Check once the player has had time to start.
        const player = ytPlayer;
        setTimeout(() => {
          if (player !== ytPlayer || cmd !== currentPlayAttempt) return;
          const state = player.getPlayerState?.();
          const states = window.YT?.PlayerState;
          if (states && state !== states.PLAYING && state !== states.BUFFERING && state !== states.ENDED) {
            markPlaybackBlocked(cmd);
          }
        }, 2500);
      } else if (cmd.action === 'pause') {
        if (cmd.position !== undefined) ytPlayer.seekTo?.(cmd.position, true);
        ytPlayer.pauseVideo?.();
      } else if (cmd.action === 'seek') {
        if (cmd.position !== undefined) ytPlayer.seekTo?.(cmd.position, true);
      } else if (cmd.action === 'volume') {
        if (cmd.muted !== undefined) {
          cmd.muted ? ytPlayer.mute?.() : ytPlayer.unMute?.();
        }
        if (cmd.volume !== undefined) ytPlayer.setVolume?.(Math.round(cmd.volume * 100));
      }
    } finally {
      setTimeout(() => { applyingCommand = false; }, 0);
    }
    return true;
  }

  // ─── Apply incoming command to Vimeo player (screen variant) ─────────────────
  function applyCommandToVimeo(cmd: VideoControlPayload): boolean {
    if (!vimeoPlayer) return false;
    applyingCommand = true;
    const finish = () => { setTimeout(() => { applyingCommand = false; }, 0); };
    if (cmd.action === 'play') {
      const p = cmd.position !== undefined
        ? vimeoPlayer.setCurrentTime(cmd.position).then(() => vimeoPlayer.play())
        : vimeoPlayer.play();
      p.catch((err: any) => {
        if (isAutoplayRejection(err)) markPlaybackBlocked(cmd);
        else console.warn('[video] Vimeo playback failed', err);
      }).finally(finish);
    } else if (cmd.action === 'pause') {
      const p = cmd.position !== undefined
        ? vimeoPlayer.setCurrentTime(cmd.position).then(() => vimeoPlayer.pause())
        : vimeoPlayer.pause();
      p.catch(() => {}).finally(finish);
    } else if (cmd.action === 'seek') {
      if (cmd.position !== undefined) {
        vimeoPlayer.setCurrentTime(cmd.position).catch(() => {}).finally(finish);
      } else { finish(); }
    } else if (cmd.action === 'volume') {
      const tasks = [];
      if (cmd.volume !== undefined) tasks.push(vimeoPlayer.setVolume(cmd.volume));
      if (cmd.muted !== undefined) tasks.push(vimeoPlayer.setMuted(cmd.muted));
      Promise.allSettled(tasks).finally(finish);
    } else {
      finish();
    }
    return true;
  }

  // ─── Reactive: apply incoming videoCommand ────────────────────────────────────
  // Each command is applied exactly once. The effect also re-runs when the
  // `slide` object is replaced (e.g. a live content edit) — re-applying the
  // last play/seek then would jump the projector back to a stale position.
  let lastAppliedCommand: VideoControlPayload | null = null;
  $effect(() => {
    const cmd = videoCommand;
    if (!cmd || variant === 'deck') return;
    // Ignore commands for a different slide.
    if (cmd.slide_id !== slide?.id) return;
    if (cmd === lastAppliedCommand) return;

    // Any newer command supersedes a pending "click to play" prompt; a new
    // play may raise it again if the browser still refuses.
    currentPlayAttempt = cmd.action === 'play' ? cmd : null;
    blockedPlay = null;
    playbackBlocked = false;

    let applied = false;
    if (embed.provider === 'native') {
      applied = applyCommandToNative(cmd);
    } else if (embed.provider === 'youtube') {
      applied = applyCommandToYt(cmd);
    } else if (embed.provider === 'vimeo') {
      applied = applyCommandToVimeo(cmd);
    }
    // Not applied = player not ready yet; the effect re-runs when it is.
    if (applied) lastAppliedCommand = cmd;
  });

  // ─── Reactive: (re)attach native video listeners ──────────────────────────────
  $effect(() => {
    const el = nativeVideoEl;
    if (!el || variant !== 'deck') return;
    attachNativeListeners(el);
    return () => detachNativeListeners(el);
  });

  // ─── Reactive: (re)initialize iframe player when iframe mounts ───────────────
  $effect(() => {
    const iframe = iframeEl;
    if (!iframe) return;
    if (embed.provider === 'youtube' && (variant === 'deck' || variant === 'screen')) {
      initYtPlayer(iframe);
    } else if (embed.provider === 'vimeo' && (variant === 'deck' || variant === 'screen')) {
      initVimeoPlayer(iframe);
    }
    return () => {
      stopYtSeekPoll();
      ytPlayer = null;
      ytReady = false;
      vimeoPlayer = null;
    };
  });
</script>

{#snippet playbackBlockedPrompt()}
  {#if variant === 'screen' && playbackBlocked}
    <button
      type="button"
      onclick={resumeBlockedPlayback}
      class="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-black/70 text-white"
    >
      <Video class="h-10 w-10" />
      <span class="text-lg font-semibold">The presenter started the video</span>
      <span class="text-sm text-white/80">This browser blocked playback — click to play here</span>
    </button>
  {/if}
{/snippet}

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
              bind:this={iframeEl}
              src={embed.url}
              title={title || 'Video player'}
              class="w-full h-full border-0 rounded-2xl"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowfullscreen
            ></iframe>
            {@render playbackBlockedPrompt()}
          </div>
        {:else}
          <div class="relative w-full h-full max-w-4xl mx-auto rounded-2xl overflow-hidden shadow-2xl bg-black flex items-center justify-center">
            <video
              bind:this={nativeVideoEl}
              src={embed.url}
              controls={variant === 'deck'}
              class="w-full h-full object-contain rounded-2xl max-h-full {variant === 'deck' ? '' : 'pointer-events-none'}"
              preload="metadata"
            >
              <track kind="captions" />
              Your browser does not support the video tag.
            </video>
            {@render playbackBlockedPrompt()}
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