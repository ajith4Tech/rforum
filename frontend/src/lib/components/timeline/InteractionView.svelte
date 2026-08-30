<script lang="ts">
  /**
   * Renders a single interaction (Poll / Q&A / Word Cloud / Feedback / Rating)
   * for one of three contexts:
   *   - 'guest'      submission form (session/[code] style)
   *   - 'screen'     large results-only display (screen/[code] style)
   *   - 'moderator'  results + inline edit form (dashboard editor style)
   *
   * A Rating interaction is just a FEEDBACK slide with content_json.mode
   * === 'rating_only' — the star-only guest form / hidden free-text field is
   * the only thing that differs from a regular Feedback slide.
   *
   * Guest submission state (name/input/rating/submitted) is owned internally
   * so the parent only needs to remount this component (e.g. inside a
   * {#key slide.id} block) when the active item changes.
   */
  import { submitResponse, upvoteResponse } from '$lib/api';
  import { BarChart3, MessageSquare, AlignLeft, Cloud, Star, Send, ChevronUp, CheckCircle2 } from 'lucide-svelte';

  let {
    slide,
    responses = [],
    variant = 'guest',
    guestId = '',
    readOnly = false,
    editing = false,
    onToggleEdit,
    onSaveContent,
    onDirtyChange
  }: {
    slide: any;
    responses?: any[];
    variant?: 'guest' | 'screen' | 'moderator';
    guestId?: string;
    /** When true (moderator Preview mode), the guest form renders but every submit/upvote action is a no-op. */
    readOnly?: boolean;
    editing?: boolean;
    onToggleEdit?: () => void;
    onSaveContent?: (contentJson: Record<string, unknown>) => void | Promise<void>;
    onDirtyChange?: (dirty: boolean) => void;
  } = $props();

  const isRatingOnly = $derived(slide?.content_json?.mode === 'rating_only');
  const typeIcon = $derived(
    slide?.type === 'POLL' ? BarChart3
      : slide?.type === 'QNA' ? MessageSquare
      : slide?.type === 'WORD_CLOUD' ? Cloud
      : isRatingOnly ? Star
      : AlignLeft
  );
  const typeLabel = $derived(
    slide?.type === 'POLL' ? 'Poll'
      : slide?.type === 'QNA' ? 'Q&A'
      : slide?.type === 'WORD_CLOUD' ? 'Word Cloud'
      : isRatingOnly ? 'Rating'
      : 'Feedback'
  );
  const promptText = $derived(slide?.type === 'POLL' ? slide?.content_json?.question : slide?.content_json?.prompt);
  function plainText(value: string): string {
    return (value || '').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
  }
  const displayPrompt = $derived(plainText(promptText || ''));

  function getFitTitleStyle(text: string, type: 'title' | 'question' = 'title'): string {
    const len = (text || '').trim().length;
    if (!len) return '';
    if (type === 'question') {
      if (len < 30) return 'font-size: clamp(1.35rem, 3vw, 2.2rem); line-height: 1.15; word-break: break-word; overflow-wrap: anywhere;';
      if (len < 70) return 'font-size: clamp(1.1rem, 2.4vw, 1.8rem); line-height: 1.18; word-break: break-word; overflow-wrap: anywhere;';
      if (len < 120) return 'font-size: clamp(0.95rem, 1.9vw, 1.4rem); line-height: 1.24; word-break: break-word; overflow-wrap: anywhere;';
      return 'font-size: clamp(0.82rem, 1.55vw, 1.1rem); line-height: 1.28; word-break: break-word; overflow-wrap: anywhere;';
    }
    if (len < 24) return 'font-size: clamp(1.8rem, 4vw, 3rem); line-height: 1.1; word-break: break-word; overflow-wrap: anywhere;';
    if (len < 56) return 'font-size: clamp(1.35rem, 2.9vw, 2.2rem); line-height: 1.15; word-break: break-word; overflow-wrap: anywhere;';
    if (len < 110) return 'font-size: clamp(1.05rem, 2vw, 1.55rem); line-height: 1.22; word-break: break-word; overflow-wrap: anywhere;';
    return 'font-size: clamp(0.85rem, 1.55vw, 1.1rem); line-height: 1.28; word-break: break-word; overflow-wrap: anywhere;';
  }

  // ── Guest submission state ──────────────────────────
  // "Already responded" is persisted per-guest so a page refresh doesn't
  // resurface a fresh voting form for a poll/feedback item the guest already
  // answered — mirrors the existing rforum_guest_id localStorage pattern.
  function respondedStorageKey() {
    return `rforum_responded_${guestId}`;
  }
  function getRespondedMap(): Record<string, string> {
    if (!guestId || typeof localStorage === 'undefined') return {};
    try {
      return JSON.parse(localStorage.getItem(respondedStorageKey()) || '{}');
    } catch {
      return {};
    }
  }
  function markResponded(slideId: string, value: string) {
    if (!guestId || typeof localStorage === 'undefined') return;
    try {
      const map = getRespondedMap();
      map[slideId] = value;
      localStorage.setItem(respondedStorageKey(), JSON.stringify(map));
    } catch {
      // localStorage unavailable (private browsing, quota) — non-fatal, just skip persistence
    }
  }
  const priorResponse = variant === 'guest' && slide?.id ? getRespondedMap()[slide.id] : undefined;
  const alreadyResponded = (slide?.type === 'POLL' || slide?.type === 'FEEDBACK') && priorResponse !== undefined;

  let guestName = $state('');
  let inputValue = $state('');
  let starRating = $state(0);
  let selectedOption = $state(alreadyResponded && slide?.type === 'POLL' ? priorResponse! : '');
  let submitted = $state(alreadyResponded);
  let thankYou = $state(false);
  let actionError = $state('');
  let isSubmitting = $state(false);

  async function handleVote(option: string) {
    if (readOnly || submitted) return;
    selectedOption = option;
    submitted = true;
    try {
      await submitResponse(slide.id, option, guestId);
      markResponded(slide.id, option);
    } catch (err: any) {
      actionError = err?.message || 'Could not submit vote';
      submitted = false;
    }
  }

  async function handleTextSubmit() {
    if (readOnly || isSubmitting) return;
    if (slide.type !== 'QNA' && slide.type !== 'WORD_CLOUD' && !isRatingOnly && !inputValue.trim()) return;
    if (isRatingOnly && !starRating) return;
    isSubmitting = true;
    try {
      const trimmedName = guestName.trim() || 'Guest';
      await submitResponse(
        slide.id,
        isRatingOnly ? '' : inputValue.trim(),
        guestId,
        trimmedName !== 'Guest' ? trimmedName : undefined,
        slide.type === 'FEEDBACK' ? (isRatingOnly ? starRating : undefined) : undefined
      );
      inputValue = '';
      actionError = '';
      if (slide.type === 'FEEDBACK') {
        submitted = true;
        markResponded(slide.id, isRatingOnly ? String(starRating) : 'submitted');
      } else {
        guestName = trimmedName;
        thankYou = true;
        setTimeout(() => { thankYou = false; }, 2000);
      }
    } catch (err: any) {
      actionError = err?.message || 'Could not submit';
      submitted = false;
    } finally {
      isSubmitting = false;
    }
  }

  async function handleUpvote(responseId: string) {
    if (readOnly) return;
    try {
      await upvoteResponse(slide.id, responseId);
    } catch (err: any) {
      actionError = err?.message || 'Could not upvote';
    }
  }

  // ── Moderator edit state ────────────────────────────
  let editQuestion = $state(slide?.content_json?.question ?? '');
  let editOptions = $state<string[]>(slide?.content_json?.options ? [...slide.content_json.options] : []);
  let editPrompt = $state(slide?.content_json?.prompt ?? '');

  function addEditOption() { editOptions = [...editOptions, '']; }
  function updateEditOption(i: number, v: string) { editOptions = editOptions.map((o, idx) => (idx === i ? v : o)); }
  function removeEditOption(i: number) { editOptions = editOptions.filter((_, idx) => idx !== i); }

  async function saveEdit() {
    try {
      if (slide.type === 'POLL') {
        const cleaned = editOptions.map((o) => o.trim()).filter(Boolean);
        if (!editQuestion.trim() || cleaned.length < 2) {
          alert('Provide a question and at least two options.');
          return;
        }
        await onSaveContent?.({ ...slide.content_json, question: editQuestion.trim(), options: cleaned });
      } else {
        await onSaveContent?.({ ...slide.content_json, prompt: editPrompt.trim() });
      }
    } catch {
      // Save failed — keep the form open (with the attempted edits) so the
      // moderator can retry instead of losing their changes silently.
      return;
    }
    onToggleEdit?.();
  }

  // Resync the buffered edit fields from the slide's real content whenever
  // the edit form (re)opens — otherwise a Cancel followed by Edit again
  // shows the discarded draft instead of the slide's current content.
  $effect(() => {
    if (editing) {
      editQuestion = slide?.content_json?.question ?? '';
      editOptions = slide?.content_json?.options ? [...slide.content_json.options] : [];
      editPrompt = slide?.content_json?.prompt ?? '';
    }
  });

  // ── Unsaved-changes tracking for the buffered edit form above ──────────
  const isDirty = $derived.by(() => {
    if (!editing) return false;
    if (slide.type === 'POLL') {
      const cleaned = editOptions.map((o) => o.trim()).filter(Boolean);
      return editQuestion.trim() !== (slide.content_json?.question || '')
        || JSON.stringify(cleaned) !== JSON.stringify(slide.content_json?.options || []);
    }
    return editPrompt.trim() !== (slide.content_json?.prompt || '');
  });

  $effect(() => {
    onDirtyChange?.(isDirty);
  });
  $effect(() => {
    return () => onDirtyChange?.(false); // clear on unmount (item switch / navigate away)
  });

  // Ctrl/Cmd+S flushes this form's buffered edit — mirrors the legacy
  // editor's Ctrl+S handling in the route, but scoped locally since this
  // component owns its own edit buffer. Only attached for the moderator
  // variant — guest/screen viewers never have anything to flush.
  $effect(() => {
    if (variant !== 'moderator') return;
    function onKeydown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        if (editing) saveEdit();
      }
    }
    window.addEventListener('keydown', onKeydown);
    return () => window.removeEventListener('keydown', onKeydown);
  });

  // ── Moderator / screen results ──────────────────────
  function pollResults() {
    const options: string[] = slide?.content_json?.options || [];
    const counts: Record<string, number> = {};
    options.forEach((opt) => (counts[opt] = 0));
    responses.forEach((r) => { if (counts[r.value] !== undefined) counts[r.value]++; });
    const total = responses.length || 1;
    return options.map((opt) => ({ label: opt, count: counts[opt], percent: Math.round((counts[opt] / total) * 100) }));
  }

  function wordCloudData() {
    const freq: Record<string, number> = {};
    for (const r of responses) {
      const word = r.value?.trim().toLowerCase();
      if (word) freq[word] = (freq[word] || 0) + 1;
    }
    const entries = Object.entries(freq).sort((a, b) => b[1] - a[1]);
    const maxCount = entries[0]?.[1] || 1;
    return entries.map(([word, count]) => ({ word, count, size: Math.max(0.75, (count / maxCount) * 2.5) }));
  }

  function averageRating() {
    const ratings = responses.map((r) => r.rating).filter((r) => typeof r === 'number');
    if (!ratings.length) return 0;
    return ratings.reduce((a, b) => a + b, 0) / ratings.length;
  }
</script>

{#if variant === 'guest'}
  <div class="text-center mb-4">
    <svelte:component this={typeIcon} class="w-10 h-10 text-purple-600 mx-auto mb-2" />
    <h1 class="text-2xl font-bold text-slate-900 dark:text-white">{displayPrompt}</h1>
  </div>

  {#if slide.type === 'POLL'}
    {#if submitted}
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-center animate-slide-up" role="status" aria-live="polite">
        <CheckCircle2 class="w-12 h-12 text-emerald-500 mx-auto mb-3" />
        <p class="font-semibold text-slate-900 dark:text-white">Vote submitted!</p>
        <p class="text-sm text-slate-500 mt-1">You chose: {selectedOption}</p>
      </div>
    {:else}
      <div class="space-y-2">
        {#each slide.content_json?.options || [] as option}
          <button
            onclick={() => handleVote(option)}
            disabled={readOnly}
            aria-pressed={selectedOption === option}
            class="w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4
                   hover:border-purple-400 dark:hover:border-purple-500/50 hover:bg-purple-50 dark:hover:bg-purple-500/5
                   transition-all duration-200 text-left text-lg font-medium text-slate-900 dark:text-white
                   active:scale-[0.98] cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:border-slate-200 dark:disabled:hover:border-slate-800 disabled:hover:bg-transparent"
          >{option}</button>
        {/each}
      </div>
    {/if}
  {:else if slide.type === 'QNA'}
    <form onsubmit={(e) => { e.preventDefault(); handleTextSubmit(); }} class="space-y-2 mb-4">
      <input type="text" bind:value={guestName} placeholder="Your name (optional)"
        class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition" />
      <div class="flex gap-2">
        <input type="text" bind:value={inputValue} placeholder="Type your question..." disabled={readOnly}
          class="flex-1 rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition disabled:opacity-50" />
        <button type="submit" class="btn-primary p-2" disabled={readOnly || isSubmitting} aria-label="Submit question"><Send class="w-5 h-5" /></button>
      </div>
    </form>
    {#if thankYou}
      <div class="flex items-center justify-center gap-2 mb-4 text-sm text-emerald-500 animate-fade-in" role="status" aria-live="polite">
        <CheckCircle2 class="w-4 h-4" /> Thanks for submitting your question!
      </div>
    {/if}
    {#if actionError}<p class="text-red-500 text-sm mb-4 text-center" role="alert">{actionError}</p>{/if}
    <div class="space-y-3 max-h-[50vh] overflow-y-auto">
      {#each [...responses].sort((a, b) => b.upvotes - a.upvotes) as response (response.id)}
        <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 flex items-start gap-3 animate-slide-up">
          <button onclick={() => handleUpvote(response.id)} disabled={readOnly} aria-label={`Upvote (${response.upvotes} votes)`} class="flex flex-col items-center text-slate-400 hover:text-purple-600 transition-colors shrink-0 disabled:opacity-50 disabled:hover:text-slate-400">
            <ChevronUp class="w-5 h-5" />
            <span class="text-xs font-bold">{response.upvotes}</span>
          </button>
          <div>
            <p class="text-slate-700 dark:text-slate-200 text-sm">{response.value}</p>
            {#if response.name}<p class="text-xs text-slate-500 mt-1">{response.name}</p>{/if}
          </div>
        </div>
      {/each}
    </div>
  {:else if slide.type === 'WORD_CLOUD'}
    <form onsubmit={(e) => { e.preventDefault(); handleTextSubmit(); }} class="space-y-2 mb-4">
      <input type="text" bind:value={guestName} placeholder="Your name (optional)"
        class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition" />
      <div class="flex gap-2">
        <input type="text" bind:value={inputValue} placeholder="Type your answer..." disabled={readOnly}
          class="flex-1 rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition disabled:opacity-50" />
        <button type="submit" class="btn-primary p-2" disabled={readOnly || isSubmitting} aria-label="Submit answer"><Send class="w-5 h-5" /></button>
      </div>
    </form>
    {#if thankYou}
      <div class="flex items-center justify-center gap-2 text-sm text-emerald-500 animate-fade-in" role="status" aria-live="polite">
        <CheckCircle2 class="w-4 h-4" /> Thanks for your answer!
      </div>
    {/if}
    {#if actionError}<p class="text-red-500 text-sm text-center" role="alert">{actionError}</p>{/if}
  {:else if slide.type === 'FEEDBACK'}
    {#if submitted}
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-center animate-slide-up" role="status" aria-live="polite">
        <CheckCircle2 class="w-12 h-12 text-emerald-500 mx-auto mb-3" />
        <p class="font-semibold text-slate-900 dark:text-white">Thanks{isRatingOnly ? '' : ' for your feedback'}!</p>
      </div>
    {:else if isRatingOnly}
      <form onsubmit={(e) => { e.preventDefault(); handleTextSubmit(); }} class="text-center space-y-4">
        <div class="flex items-center justify-center gap-2">
          {#each [1, 2, 3, 4, 5] as n}
            <button type="button" onclick={() => (starRating = n)} disabled={readOnly} class="transition-transform active:scale-90 disabled:opacity-50" aria-label={`${n} star${n === 1 ? '' : 's'}`} aria-pressed={starRating === n}>
              <Star class="w-9 h-9 {n <= starRating ? 'text-amber-400 fill-amber-400' : 'text-slate-300 dark:text-slate-700'}" />
            </button>
          {/each}
        </div>
        <input type="text" bind:value={guestName} placeholder="Your name (optional)" disabled={readOnly}
          class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition disabled:opacity-50" />
        <button type="submit" class="btn-primary w-full flex items-center justify-center gap-2" disabled={!starRating || readOnly || isSubmitting}>
          <Send class="w-4 h-4" /> Submit
        </button>
      </form>
    {:else}
      <form onsubmit={(e) => { e.preventDefault(); handleTextSubmit(); }}>
        <input type="text" bind:value={guestName} placeholder="Your name (optional)" disabled={readOnly}
          class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition mb-2 disabled:opacity-50" />
        <textarea bind:value={inputValue} placeholder="Share your thoughts..." rows="4" disabled={readOnly}
          class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition mb-2 resize-none disabled:opacity-50"></textarea>
        <button type="submit" class="btn-primary w-full flex items-center justify-center gap-2" disabled={readOnly || isSubmitting}>
          <Send class="w-4 h-4" /> Submit
        </button>
      </form>
    {/if}
  {/if}

{:else if variant === 'screen'}
  <div class="flex flex-col gap-4 w-full">
    <div class="text-center space-y-1">
      <div class="inline-flex items-center gap-2 bg-purple-500/10 text-purple-600 dark:text-purple-400 text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full border border-purple-500/20">
        <svelte:component this={typeIcon} class="w-3.5 h-3.5" /> {typeLabel}
      </div>
      <h1 class="font-heading font-bold text-slate-900 dark:text-slate-100 leading-snug" style={getFitTitleStyle(displayPrompt, 'question')}>{displayPrompt}</h1>
      <p class="text-slate-400 text-xs">{responses.length} response{responses.length === 1 ? '' : 's'}</p>
    </div>

    {#if slide.type === 'POLL'}
      <div class="space-y-3 max-w-xl mx-auto w-full my-auto">
        {#each pollResults() as row, i}
          {@const hues = ['bg-purple-600', 'bg-emerald-500', 'bg-cyan-500', 'bg-amber-500', 'bg-rose-500']}
          <div class="space-y-1">
            <div class="flex items-center justify-between text-sm sm:text-base">
              <span class="font-semibold text-slate-800 dark:text-slate-200">{row.label}</span>
              <span class="font-mono font-bold text-purple-600 dark:text-purple-400">{row.percent}%</span>
            </div>
            <div class="relative h-9 bg-slate-100 dark:bg-slate-950 rounded-xl overflow-hidden border border-slate-200 dark:border-slate-800">
              <div class="absolute inset-y-0 left-0 rounded-xl transition-all duration-700 {hues[i % hues.length]}"
                style={`width: ${row.percent}%; min-width: ${row.percent > 0 ? '12px' : '0'}`}></div>
              <span class="absolute inset-y-0 right-3 flex items-center text-slate-500 dark:text-slate-400 text-xs font-mono">{row.count}</span>
            </div>
          </div>
        {/each}
      </div>
    {:else if slide.type === 'QNA'}
      {#if responses.length === 0}
        <div class="text-center text-slate-400 text-base py-8">No questions submitted yet…</div>
      {:else}
        <div class="max-h-[60vh] overflow-y-auto space-y-3 pr-1 my-auto">
          {#each [...responses].sort((a, b) => (b.upvotes ?? 0) - (a.upvotes ?? 0)) as response (response.id)}
            <div class="flex items-start gap-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl p-4">
              <div class="flex flex-col items-center justify-center shrink-0 px-3 py-1.5 rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400 font-bold">
                <span class="text-xl font-bold">{response.upvotes ?? 0}</span>
                <span class="text-[9px] uppercase tracking-wider">votes</span>
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-slate-800 dark:text-slate-200 text-base font-medium leading-relaxed">{response.value}</p>
                <p class="text-slate-400 text-xs mt-1">{response.name || response.guest_identifier || 'Anonymous'}</p>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    {:else if slide.type === 'WORD_CLOUD'}
      {#if responses.length === 0}
        <div class="text-center text-slate-400 text-base py-8">Waiting for audience words…</div>
      {:else}
        {@const palette = ['text-purple-600 dark:text-purple-400', 'text-cyan-600 dark:text-cyan-400', 'text-emerald-600 dark:text-emerald-400', 'text-amber-600 dark:text-amber-400', 'text-rose-600 dark:text-rose-400']}
        <div class="flex flex-wrap items-center justify-center gap-x-6 gap-y-4 max-h-[60vh] overflow-y-auto p-4 my-auto">
          {#each wordCloudData() as item, i}
            <span class="font-heading font-extrabold transition-all duration-500 {palette[i % palette.length]}"
              style={`font-size: ${item.size * 1.2}rem; opacity: ${0.6 + (item.count / (responses.length || 1)) * 0.4}`}>{item.word}</span>
          {/each}
        </div>
      {/if}
    {:else if slide.type === 'FEEDBACK' && isRatingOnly}
      <div class="text-center py-6 my-auto">
        <div class="text-6xl font-heading font-bold text-amber-500">{averageRating().toFixed(1)}</div>
        <div class="flex items-center justify-center gap-1 mt-2">
          {#each [1, 2, 3, 4, 5] as n}
            <Star class="w-6 h-6 {n <= Math.round(averageRating()) ? 'text-amber-400 fill-amber-400' : 'text-slate-300 dark:text-slate-700'}" />
          {/each}
        </div>
      </div>
    {:else if slide.type === 'FEEDBACK'}
      {#if responses.length === 0}
        <div class="text-center text-slate-400 text-base py-8">No feedback responses yet…</div>
      {:else}
        <div class="max-h-[60vh] overflow-y-auto space-y-3 pr-1 my-auto">
          {#each responses as response (response.id)}
            <div class="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl p-4">
              <div class="flex items-center justify-between mb-1 text-xs text-slate-400">
                <span>{response.name || response.guest_identifier || 'Anonymous'}</span>
                {#if response.rating}<span class="text-amber-400 font-bold">{'★'.repeat(response.rating)}{'☆'.repeat(5 - response.rating)}</span>{/if}
              </div>
              <p class="text-slate-800 dark:text-slate-200 text-base">{response.value}</p>
            </div>
          {/each}
        </div>
      {/if}
    {/if}
  </div>

{:else}
  <!-- moderator -->
  <div class="card p-4 sm:p-5 space-y-3">
    <div class="flex items-center justify-between">
      <div class="text-lg font-semibold">{typeLabel}</div>
      <button onclick={onToggleEdit} class="btn-secondary text-xs px-3 py-1.5">{editing ? 'Cancel' : 'Edit'}</button>
    </div>

    {#if !editing}
      <p class="text-base font-medium text-surface-200">{displayPrompt}</p>
    {:else if slide.type === 'POLL'}
      <input class="input-field" type="text" bind:value={editQuestion} placeholder="Poll question" />
      <div class="space-y-2">
        {#each editOptions as option, index (index)}
          <div class="flex items-center gap-2">
            <input class="input-field flex-1" type="text" value={option}
              oninput={(e) => updateEditOption(index, (e.currentTarget as HTMLInputElement).value)}
              placeholder={`Option ${index + 1}`} />
            <button onclick={() => removeEditOption(index)} class="btn-danger text-xs px-3 py-1.5">Remove</button>
          </div>
        {/each}
      </div>
      <div class="flex items-center gap-2">
        <button onclick={addEditOption} class="btn-secondary">Add option</button>
        <button onclick={saveEdit} class="btn-primary text-sm">Save</button>
      </div>
    {:else}
      <input class="input-field" type="text" bind:value={editPrompt} placeholder="Prompt" />
      <div class="flex items-center gap-2">
        <button onclick={saveEdit} class="btn-primary text-sm">Save prompt</button>
      </div>
    {/if}

    {#if slide.type === 'POLL'}
      <div class="border border-surface-200 rounded-xl p-4">
        <div class="text-sm font-semibold mb-3">Live results</div>
        <div class="flex items-end gap-4">
          {#each pollResults() as row}
            <div class="flex flex-col items-center gap-2 flex-1">
              <div class="relative w-full h-28 bg-surface-100 rounded-lg overflow-hidden">
                <div class="absolute bottom-0 left-0 right-0 bg-brand-500 rounded-lg transition-all duration-500"
                  style={`height: ${row.percent}%; min-height: ${row.percent > 0 ? '6px' : '0px'}`}></div>
              </div>
              <div class="text-xs text-surface-500">{row.label}</div>
              <div class="text-xs text-surface-400">{row.percent}%</div>
            </div>
          {/each}
        </div>
      </div>
    {:else if slide.type === 'QNA'}
      {#if responses.length === 0}
        <div class="text-sm text-surface-400">No questions yet.</div>
      {:else}
        <div class="space-y-3">
          {#each responses as response (response.id)}
            <div class="p-3 rounded-xl border border-surface-200">
              <div class="text-xs text-surface-500 mb-1">{response.name || response.guest_identifier}</div>
              <div class="text-sm">{response.value}</div>
            </div>
          {/each}
        </div>
      {/if}
    {:else if slide.type === 'WORD_CLOUD'}
      {#if responses.length === 0}
        <div class="text-sm text-surface-400">No responses yet.</div>
      {:else}
        <div class="border border-surface-200 rounded-xl p-4 sm:p-5 flex flex-wrap items-center justify-center gap-3 min-h-[180px]">
          {#each wordCloudData() as item}
            <span class="text-brand-600 font-semibold transition-all"
              style={`font-size: ${item.size}rem; opacity: ${0.5 + (item.count / (responses.length || 1)) * 0.5}`}>{item.word}</span>
          {/each}
        </div>
        <div class="text-xs text-surface-400">{responses.length} response{responses.length === 1 ? '' : 's'}</div>
      {/if}
    {:else if isRatingOnly}
      <div class="border border-surface-200 rounded-xl p-4 text-center">
        <div class="text-4xl font-bold text-amber-500">{averageRating().toFixed(1)}</div>
        <div class="text-xs text-surface-400 mt-1">{responses.length} rating{responses.length === 1 ? '' : 's'}</div>
      </div>
    {:else}
      {#if responses.length === 0}
        <div class="text-sm text-surface-400">No feedback yet.</div>
      {:else}
        <div class="space-y-3">
          {#each responses as response (response.id)}
            <div class="p-3 rounded-xl border border-surface-200">
              <div class="flex items-center justify-between text-xs text-surface-500 mb-1">
                <span>{response.name || response.guest_identifier}</span>
                {#if response.rating}<span class="font-medium">Rating: {response.rating}</span>{/if}
              </div>
              <div class="text-sm">{response.value}</div>
            </div>
          {/each}
        </div>
      {/if}
    {/if}
  </div>
{/if}
