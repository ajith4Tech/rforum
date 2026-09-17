<script lang="ts">
  /**
   * Renders interactive slide types:
   *   - POLL
   *   - MULTIPLE_CHOICE
   *   - QUIZ
   *   - QNA
   *   - WORD_CLOUD
   *   - FEEDBACK
   *   - RATING
   *   - SCALE
   *   - SURVEY
   *
   * For one of three contexts:
   *   - 'guest'      submission form (session/[code] style)
   *   - 'screen'     large results-only display (screen/[code] style)
   *   - 'moderator'  results + inline edit form (dashboard editor style)
   */
  import { submitResponse, upvoteResponse } from '$lib/api';
  import {
    BarChart3, MessageSquare, AlignLeft, Cloud, Star, Send, ChevronUp,
    CheckCircle2, ListChecks, HelpCircle, Sliders, ClipboardList, Check, X, Plus, Trash2
  } from 'lucide-svelte';
  import { getFitTitleStyle } from '$lib/fitTitle';

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
    readOnly?: boolean;
    editing?: boolean;
    onToggleEdit?: () => void;
    onSaveContent?: (contentJson: Record<string, unknown>) => void | Promise<void>;
    onDirtyChange?: (dirty: boolean) => void;
  } = $props();

  const cj = $derived(slide?.content_json || {});
  const itype = $derived((cj.interaction_type || cj.mode || slide?.type || '').toUpperCase());

  const isQuiz = $derived(itype === 'QUIZ' || cj.mode === 'quiz');
  const isMultipleChoice = $derived(itype === 'MULTIPLE_CHOICE' || cj.mode === 'multiple_choice');
  const isScale = $derived(itype === 'SCALE' || cj.mode === 'scale');
  const isSurvey = $derived(itype === 'SURVEY' || cj.mode === 'survey');
  const isRatingOnly = $derived(cj.mode === 'rating_only' || itype === 'RATING');
  const isPoll = $derived((slide?.type === 'POLL' || itype === 'POLL') && !isQuiz && !isMultipleChoice);
  const isQna = $derived(slide?.type === 'QNA' || itype === 'QNA');
  const isWordCloud = $derived(slide?.type === 'WORD_CLOUD' || itype === 'WORD_CLOUD');
  const isFeedback = $derived((slide?.type === 'FEEDBACK' || itype === 'FEEDBACK') && !isRatingOnly && !isScale && !isSurvey);

  const typeIcon = $derived(
    isQuiz ? HelpCircle
      : isMultipleChoice ? ListChecks
      : isScale ? Sliders
      : isSurvey ? ClipboardList
      : isPoll ? BarChart3
      : isQna ? MessageSquare
      : isWordCloud ? Cloud
      : isRatingOnly ? Star
      : AlignLeft
  );

  const typeLabel = $derived(
    isQuiz ? 'Quiz'
      : isMultipleChoice ? 'Multiple Choice'
      : isScale ? 'Scale'
      : isSurvey ? 'Survey'
      : isPoll ? 'Poll'
      : isQna ? 'Q&A'
      : isWordCloud ? 'Word Cloud'
      : isRatingOnly ? 'Rating'
      : 'Feedback'
  );

  const promptText = $derived(
    slide?.type === 'POLL' || isMultipleChoice || isQuiz
      ? (cj.question || cj.prompt)
      : (cj.prompt || cj.question || cj.title)
  );

  function plainText(value: string): string {
    return (value || '').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
  }
  const displayPrompt = $derived(plainText(promptText || ''));

  // Scale parameters
  const scaleMin = $derived(typeof cj.min === 'number' ? cj.min : 1);
  const scaleMax = $derived(typeof cj.max === 'number' ? cj.max : 10);
  const scaleStep = $derived(typeof cj.step === 'number' && cj.step > 0 ? cj.step : 1);
  const scaleMinLabel = $derived(cj.min_label || (typeof cj.labels === 'object' ? cj.labels?.min : '') || '');
  const scaleMaxLabel = $derived(cj.max_label || (typeof cj.labels === 'object' ? cj.labels?.max : '') || (typeof cj.labels === 'string' ? cj.labels : ''));

  // Scale point array
  const scalePoints = $derived.by(() => {
    const pts: number[] = [];
    for (let v = scaleMin; v <= scaleMax; v += scaleStep) {
      pts.push(v);
    }
    return pts;
  });

  // Survey questions
  const surveyQuestions = $derived<any[]>(Array.isArray(cj.questions) ? cj.questions : []);

  // ── Multiple Choice: multi-select is always on (moderator does not
  // configure it) — a guest may pick one or more options before submitting.
  // Stored as a JSON array string in the single `value` field (same
  // encoding convention Survey already uses for structured answers), so no
  // backend/schema change was needed. Poll and Quiz are UNAFFECTED — both
  // remain plain single-string values, since Quiz's correct-answer scoring
  // specifically depends on an exact single-value match.
  function parseMultiValue(raw: string | undefined | null): string[] {
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    } catch {
      // Not JSON (or not an array) — treat as a single legacy/plain value.
    }
    return [raw];
  }

  // ── Guest submission state & persistence ──────────────────────────
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
    } catch {}
  }

  const priorResponse = $derived(variant === 'guest' && slide?.id ? getRespondedMap()[slide.id] : undefined);
  const alreadyResponded = $derived(
    (isPoll || isMultipleChoice || isQuiz || isRatingOnly || isFeedback || isScale || isSurvey) &&
    priorResponse !== undefined
  );

  let guestName = $state('');
  let inputValue = $state('');
  let starRating = $state(0);
  let scaleRating = $state<number | null>(null);
  let selectedOption = $state('');
  // pendingOptions: for Multiple Choice only — staged multi-selection before explicit submit
  let pendingOptions = $state<string[]>([]);
  let surveyAnswers = $state<Record<number, any>>({});
  let submitted = $state(false);
  let thankYou = $state(false);
  let actionError = $state('');
  let isSubmitting = $state(false);

  $effect(() => {
    void slide?.id;
    if (isMultipleChoice) {
      const parsed = alreadyResponded ? parseMultiValue(priorResponse) : [];
      pendingOptions = parsed;
      selectedOption = parsed.join(', ');
    } else {
      selectedOption = alreadyResponded && (isPoll || isQuiz) ? priorResponse! : '';
      pendingOptions = [];
    }
    submitted = alreadyResponded;
    starRating = 0;
    scaleRating = null;
    surveyAnswers = {};
    inputValue = '';
    thankYou = false;
    actionError = '';
  });

  // Single choice voting (Poll / Quiz — instant submit on click)
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

  // Multiple Choice: toggle one option in/out of the staged selection —
  // guest can pick any number of options before submitting.
  function toggleMultipleChoiceOption(option: string) {
    if (readOnly || submitted) return;
    pendingOptions = pendingOptions.includes(option)
      ? pendingOptions.filter((o) => o !== option)
      : [...pendingOptions, option];
  }

  // Multiple Choice: two-step — stage selection(s), then explicit submit
  async function handleMultipleChoiceSubmit() {
    if (readOnly || submitted || pendingOptions.length === 0) return;
    submitted = true;
    selectedOption = pendingOptions.join(', ');
    const payload = JSON.stringify(pendingOptions);
    try {
      await submitResponse(slide.id, payload, guestId);
      markResponded(slide.id, payload);
    } catch (err: any) {
      actionError = err?.message || 'Could not submit answer';
      submitted = false;
    }
  }

  // Scale rating submit
  async function handleScaleSubmit() {
    if (readOnly || isSubmitting || scaleRating === null) return;
    isSubmitting = true;
    try {
      const trimmedName = guestName.trim() || 'Guest';
      await submitResponse(
        slide.id,
        String(scaleRating),
        guestId,
        trimmedName !== 'Guest' ? trimmedName : undefined,
        scaleRating
      );
      submitted = true;
      markResponded(slide.id, String(scaleRating));
    } catch (err: any) {
      actionError = err?.message || 'Could not submit rating';
    } finally {
      isSubmitting = false;
    }
  }

  // Survey submit
  async function handleSurveySubmit() {
    if (readOnly || isSubmitting) return;
    if (Object.keys(surveyAnswers).length === 0) {
      actionError = 'Please answer at least one question before submitting.';
      return;
    }
    isSubmitting = true;
    try {
      const trimmedName = guestName.trim() || 'Guest';
      const payloadStr = JSON.stringify({ answers: surveyAnswers });
      await submitResponse(
        slide.id,
        payloadStr,
        guestId,
        trimmedName !== 'Guest' ? trimmedName : undefined
      );
      submitted = true;
      markResponded(slide.id, 'survey_submitted');
    } catch (err: any) {
      actionError = err?.message || 'Could not submit survey';
    } finally {
      isSubmitting = false;
    }
  }

  // Text / Rating submit (Q&A, Feedback, Word Cloud, Star Rating)
  async function handleTextSubmit() {
    if (readOnly || isSubmitting) return;
    if (!isQna && !isWordCloud && !isRatingOnly && !inputValue.trim()) return;
    if (isRatingOnly && !starRating) return;
    isSubmitting = true;
    try {
      const trimmedName = guestName.trim() || 'Guest';
      await submitResponse(
        slide.id,
        isRatingOnly ? String(starRating) : inputValue.trim(),
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

  // ── Aggregations for Screen & Moderator ──────────────────────────
  function pollResults() {
    const options: string[] = cj.options || [];
    const counts: Record<string, number> = {};
    options.forEach((opt) => (counts[opt] = 0));
    responses.forEach((r) => {
      // Multiple Choice responses are JSON-array-encoded (a guest can have
      // selected more than one option); Poll/Quiz responses remain a single
      // plain string. Percentages are computed against total RESPONDENTS,
      // not total selections, so a multi-select question's percentages can
      // legitimately sum past 100% — same convention any "select all that
      // apply" survey tool uses.
      const selected = isMultipleChoice ? parseMultiValue(r.value) : [r.value];
      selected.forEach((v) => { if (counts[v] !== undefined) counts[v]++; });
    });
    const total = responses.length || 1;
    return options.map((opt) => ({
      label: opt,
      count: counts[opt],
      percent: Math.round((counts[opt] / total) * 100),
      isCorrect: isQuiz && cj.correct_answer === opt
    }));
  }

  const quizStats = $derived.by(() => {
    if (!isQuiz) return { total: 0, correct: 0, incorrect: 0, percentCorrect: 0 };
    const correctAns = cj.correct_answer || '';
    let correct = 0;
    let incorrect = 0;
    responses.forEach((r) => {
      if (r.value === correctAns) correct++;
      else incorrect++;
    });
    const total = responses.length;
    return {
      total,
      correct,
      incorrect,
      percentCorrect: total > 0 ? Math.round((correct / total) * 100) : 0
    };
  });

  function scaleResults() {
    const counts: Record<number, number> = {};
    scalePoints.forEach((p) => (counts[p] = 0));
    let totalScore = 0;
    let validCount = 0;
    responses.forEach((r) => {
      const num = typeof r.rating === 'number' ? r.rating : parseFloat(r.value);
      if (!isNaN(num) && counts[num] !== undefined) {
        counts[num]++;
        totalScore += num;
        validCount++;
      }
    });
    const average = validCount > 0 ? (totalScore / validCount).toFixed(1) : '0.0';
    const total = validCount || 1;
    const distribution = scalePoints.map((p) => ({
      point: p,
      count: counts[p],
      percent: Math.round((counts[p] / total) * 100)
    }));
    return { average, totalCount: validCount, distribution };
  }

  function surveyAggregates() {
    return surveyQuestions.map((q, idx) => {
      const qType = q.response_type || 'text';
      if (qType === 'single_choice') {
        const opts: string[] = q.options || [];
        const counts: Record<string, number> = {};
        opts.forEach((o) => (counts[o] = 0));
        let total = 0;
        responses.forEach((r) => {
          try {
            const parsed = JSON.parse(r.value);
            const val = parsed?.answers?.[idx];
            if (val && counts[val] !== undefined) {
              counts[val]++;
              total++;
            }
          } catch {}
        });
        const safeTotal = total || 1;
        const optionsData = opts.map((o) => ({
          label: o,
          count: counts[o],
          percent: Math.round((counts[o] / safeTotal) * 100)
        }));
        return { ...q, qIndex: idx, type: 'single_choice', totalResponses: total, optionsData };
      } else if (qType === 'scale') {
        const min = typeof q.min === 'number' ? q.min : 1;
        const max = typeof q.max === 'number' ? q.max : 10;
        let sum = 0;
        let count = 0;
        responses.forEach((r) => {
          try {
            const parsed = JSON.parse(r.value);
            const val = parseFloat(parsed?.answers?.[idx]);
            if (!isNaN(val)) {
              sum += val;
              count++;
            }
          } catch {}
        });
        const avg = count > 0 ? (sum / count).toFixed(1) : '0.0';
        return { ...q, qIndex: idx, type: 'scale', totalResponses: count, average: avg, min, max };
      } else {
        let count = 0;
        responses.forEach((r) => {
          try {
            const parsed = JSON.parse(r.value);
            if (parsed?.answers?.[idx]) count++;
          } catch {}
        });
        return { ...q, qIndex: idx, type: 'text', totalResponses: count };
      }
    });
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

  // ── Moderator edit state ────────────────────────────
  let editQuestion = $state(cj.question ?? cj.prompt ?? '');
  let editPrompt = $state(cj.prompt ?? cj.question ?? '');
  let editOptions = $state<string[]>(cj.options ? [...cj.options] : []);
  let editCorrectAnswer = $state(cj.correct_answer ?? '');
  let editRevealAnswer = $state(Boolean(cj.reveal_answer));
  let editMin = $state(scaleMin);
  let editMax = $state(scaleMax);
  let editStep = $state(scaleStep);
  let editMinLabel = $state(scaleMinLabel);
  let editMaxLabel = $state(scaleMaxLabel);
  let editQuestions = $state<any[]>(Array.isArray(cj.questions) ? JSON.parse(JSON.stringify(cj.questions)) : []);

  function addEditOption() { editOptions = [...editOptions, '']; }
  function updateEditOption(i: number, v: string) { editOptions = editOptions.map((o, idx) => (idx === i ? v : o)); }
  function removeEditOption(i: number) { editOptions = editOptions.filter((_, idx) => idx !== i); }

  function addSurveyQuestion() {
    editQuestions = [
      ...editQuestions,
      { prompt: 'New question', response_type: 'single_choice', options: ['Option 1', 'Option 2'] }
    ];
  }
  function removeSurveyQuestion(i: number) {
    editQuestions = editQuestions.filter((_, idx) => idx !== i);
  }

  async function saveEdit() {
    try {
      if (isPoll || isMultipleChoice) {
        const cleaned = editOptions.map((o) => o.trim()).filter(Boolean);
        if (!editQuestion.trim() || cleaned.length < 2) {
          alert('Provide a question and at least two options.');
          return;
        }
        await onSaveContent?.({
          ...cj,
          question: editQuestion.trim(),
          options: cleaned,
          interaction_type: isMultipleChoice ? 'MULTIPLE_CHOICE' : 'POLL',
          mode: isMultipleChoice ? 'multiple_choice' : undefined
        });
      } else if (isQuiz) {
        const cleaned = editOptions.map((o) => o.trim()).filter(Boolean);
        if (!editQuestion.trim() || cleaned.length < 2) {
          alert('Provide a question and at least two options.');
          return;
        }
        await onSaveContent?.({
          ...cj,
          question: editQuestion.trim(),
          options: cleaned,
          correct_answer: editCorrectAnswer || cleaned[0],
          reveal_answer: editRevealAnswer,
          interaction_type: 'QUIZ',
          mode: 'quiz'
        });
      } else if (isScale) {
        await onSaveContent?.({
          ...cj,
          prompt: editPrompt.trim(),
          min: editMin,
          max: editMax,
          step: editStep,
          min_label: editMinLabel.trim(),
          max_label: editMaxLabel.trim(),
          interaction_type: 'SCALE',
          mode: 'scale'
        });
      } else if (isSurvey) {
        await onSaveContent?.({
          ...cj,
          prompt: editPrompt.trim(),
          questions: editQuestions,
          interaction_type: 'SURVEY',
          mode: 'survey'
        });
      } else {
        await onSaveContent?.({ ...cj, prompt: editPrompt.trim() });
      }
    } catch {
      return;
    }
    onToggleEdit?.();
  }

  $effect(() => {
    if (editing) {
      editQuestion = cj.question ?? cj.prompt ?? '';
      editPrompt = cj.prompt ?? cj.question ?? '';
      editOptions = cj.options ? [...cj.options] : [];
      editCorrectAnswer = cj.correct_answer ?? '';
      editRevealAnswer = Boolean(cj.reveal_answer);
      editMin = scaleMin;
      editMax = scaleMax;
      editStep = scaleStep;
      editMinLabel = scaleMinLabel;
      editMaxLabel = scaleMaxLabel;
      editQuestions = Array.isArray(cj.questions) ? JSON.parse(JSON.stringify(cj.questions)) : [];
    }
  });

  const isDirty = $derived.by(() => {
    if (!editing) return false;
    if (isPoll || isMultipleChoice) {
      const cleaned = editOptions.map((o) => o.trim()).filter(Boolean);
      return editQuestion.trim() !== (cj.question || '') || JSON.stringify(cleaned) !== JSON.stringify(cj.options || []);
    }
    if (isQuiz) {
      const cleaned = editOptions.map((o) => o.trim()).filter(Boolean);
      return editQuestion.trim() !== (cj.question || '') ||
        JSON.stringify(cleaned) !== JSON.stringify(cj.options || []) ||
        editCorrectAnswer !== (cj.correct_answer || '') ||
        editRevealAnswer !== Boolean(cj.reveal_answer);
    }
    if (isScale) {
      return editPrompt.trim() !== (cj.prompt || '') || editMin !== scaleMin || editMax !== scaleMax || editMinLabel !== scaleMinLabel || editMaxLabel !== scaleMaxLabel;
    }
    if (isSurvey) {
      return editPrompt.trim() !== (cj.prompt || '') || JSON.stringify(editQuestions) !== JSON.stringify(cj.questions || []);
    }
    return editPrompt.trim() !== (cj.prompt || '');
  });

  $effect(() => {
    onDirtyChange?.(isDirty);
  });
  $effect(() => {
    return () => onDirtyChange?.(false);
  });

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
</script>

{#if variant === 'guest'}
  <div class="text-center mb-4">
    <svelte:component this={typeIcon} class="w-10 h-10 text-purple-600 mx-auto mb-2" />
    <h1 class="font-heading font-bold text-slate-900 dark:text-white leading-tight" style={getFitTitleStyle(displayPrompt, 'question')}>{displayPrompt}</h1>
  </div>

  <!-- POLL & MULTIPLE CHOICE & QUIZ -->
  {#if isPoll || isMultipleChoice || isQuiz}
    {#if submitted}
      {#if isQuiz && cj.reveal_answer && cj.correct_answer}
        <!-- Quiz: show right/wrong after moderator reveals -->
        {@const wasCorrect = selectedOption === cj.correct_answer}
        <div class="rounded-2xl border p-6 text-center animate-slide-up {wasCorrect ? 'border-emerald-400 bg-emerald-50 dark:bg-emerald-950/30' : 'border-red-400 bg-red-50 dark:bg-red-950/30'}" role="status" aria-live="polite">
          {#if wasCorrect}
            <CheckCircle2 class="w-12 h-12 text-emerald-500 mx-auto mb-3" />
            <p class="font-bold text-xl text-emerald-700 dark:text-emerald-400">Correct! 🎉</p>
            <p class="text-sm text-emerald-600 dark:text-emerald-500 mt-1">You chose: {selectedOption}</p>
          {:else}
            <X class="w-12 h-12 text-red-500 mx-auto mb-3" />
            <p class="font-bold text-xl text-red-700 dark:text-red-400">Incorrect</p>
            <p class="text-sm text-slate-500 mt-1">Your answer: {selectedOption}</p>
            <p class="text-sm font-semibold text-emerald-600 dark:text-emerald-400 mt-2">✓ Correct answer: {cj.correct_answer}</p>
          {/if}
        </div>
      {:else}
        <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-center animate-slide-up" role="status" aria-live="polite">
          <CheckCircle2 class="w-12 h-12 text-emerald-500 mx-auto mb-3" />
          <p class="font-semibold text-slate-900 dark:text-white">{isQuiz ? 'Answer submitted!' : 'Vote submitted!'}</p>
          <p class="text-sm text-slate-500 mt-1">You chose: {selectedOption}</p>
          {#if isQuiz}<p class="text-xs text-slate-400 mt-2">Waiting for the moderator to reveal the answer…</p>{/if}
        </div>
      {/if}
    {:else if isMultipleChoice}
      <!-- Multiple Choice: checkbox-style — pick one or more, then explicit submit -->
      <div class="space-y-2">
        {#each cj.options || [] as option}
          {@const isChecked = pendingOptions.includes(option)}
          <button
            onclick={() => toggleMultipleChoiceOption(option)}
            disabled={readOnly}
            aria-pressed={isChecked}
            class="w-full rounded-2xl border p-4 transition-all duration-200 text-left text-lg font-medium flex items-center gap-3
                   active:scale-[0.98] cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed
                   {isChecked
                     ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-200 ring-2 ring-purple-500/30'
                     : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-white hover:border-purple-400 dark:hover:border-purple-500/50 hover:bg-purple-50 dark:hover:bg-purple-500/5'}"
          >
            <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-2 transition-colors {isChecked ? 'border-purple-500 bg-purple-500' : 'border-slate-300 dark:border-slate-600'}">
              {#if isChecked}<Check class="w-3.5 h-3.5 text-white" />{/if}
            </span>
            {option}
          </button>
        {/each}
      </div>
      <button
        onclick={handleMultipleChoiceSubmit}
        disabled={pendingOptions.length === 0 || readOnly}
        class="mt-4 btn-primary w-full flex items-center justify-center gap-2 py-3 text-base disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Send class="w-4 h-4" /> Submit Answer
      </button>
    {:else}
      <!-- Poll / Quiz: instant click-to-submit -->
      <div class="space-y-2">
        {#each cj.options || [] as option}
          <button
            onclick={() => handleVote(option)}
            disabled={readOnly}
            aria-pressed={selectedOption === option}
            class="w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4
                   hover:border-purple-400 dark:hover:border-purple-500/50 hover:bg-purple-50 dark:hover:bg-purple-500/5
                   transition-all duration-200 text-left text-lg font-medium text-slate-900 dark:text-white
                   active:scale-[0.98] cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >{option}</button>
        {/each}
      </div>
    {/if}
    {#if actionError}<p class="text-red-500 text-sm mt-3 text-center" role="alert">{actionError}</p>{/if}

  <!-- SCALE SLIDE -->
  {:else if isScale}
    {#if submitted}
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-center animate-slide-up" role="status" aria-live="polite">
        <CheckCircle2 class="w-12 h-12 text-emerald-500 mx-auto mb-3" />
        <p class="font-semibold text-slate-900 dark:text-white">Rating submitted!</p>
        {#if scaleRating !== null}<p class="text-sm text-slate-500 mt-1">Score: {scaleRating}</p>{/if}
      </div>
    {:else}
      <div class="space-y-5">
        <div class="flex flex-wrap items-center justify-center gap-2 py-2">
          {#each scalePoints as pt}
            <button
              type="button"
              onclick={() => (scaleRating = pt)}
              disabled={readOnly}
              aria-pressed={scaleRating === pt}
              class="h-12 w-12 rounded-2xl font-mono text-base font-bold transition-all active:scale-90 {scaleRating === pt ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/30 scale-105' : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 hover:border-purple-400'}"
            >
              {pt}
            </button>
          {/each}
        </div>

        {#if scaleMinLabel || scaleMaxLabel}
          <div class="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 px-1">
            <span>{scaleMinLabel}</span>
            <span>{scaleMaxLabel}</span>
          </div>
        {/if}

        <input
          type="text"
          bind:value={guestName}
          placeholder="Your name (optional)"
          disabled={readOnly}
          class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition disabled:opacity-50"
        />

        <button
          onclick={handleScaleSubmit}
          class="btn-primary w-full flex items-center justify-center gap-2 py-3 text-base"
          disabled={scaleRating === null || readOnly || isSubmitting}
        >
          <Send class="w-4 h-4" /> Submit Score
        </button>
        {#if actionError}<p class="text-red-500 text-sm text-center" role="alert">{actionError}</p>{/if}
      </div>
    {/if}

  <!-- SURVEY SLIDE -->
  {:else if isSurvey}
    {#if submitted}
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-center animate-slide-up" role="status" aria-live="polite">
        <CheckCircle2 class="w-12 h-12 text-emerald-500 mx-auto mb-3" />
        <p class="font-semibold text-slate-900 dark:text-white">Survey submitted!</p>
        <p class="text-sm text-slate-500 mt-1">Thank you for sharing your responses.</p>
      </div>
    {:else}
      <div class="space-y-6">
        {#each surveyQuestions as q, qIdx}
          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3">
            <p class="font-semibold text-slate-900 dark:text-white text-base">
              <span class="text-purple-600 dark:text-purple-400 font-mono text-xs mr-1.5">{qIdx + 1}.</span> {q.prompt}
            </p>

            {#if q.response_type === 'single_choice'}
              <div class="space-y-1.5">
                {#each q.options || [] as opt}
                  <button
                    type="button"
                    onclick={() => { surveyAnswers = { ...surveyAnswers, [qIdx]: opt }; }}
                    class="w-full text-left px-3.5 py-2.5 rounded-xl border text-sm transition-all {surveyAnswers[qIdx] === opt ? 'border-purple-500 bg-purple-50 dark:bg-purple-500/10 text-purple-700 dark:text-purple-300 font-medium' : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 text-slate-700 dark:text-slate-200'}"
                  >
                    {opt}
                  </button>
                {/each}
              </div>
            {:else if q.response_type === 'scale'}
              {@const qMin = typeof q.min === 'number' ? q.min : 1}
              {@const qMax = typeof q.max === 'number' ? q.max : 5}
              <div class="flex flex-wrap gap-1.5 py-1">
                {#each Array.from({ length: qMax - qMin + 1 }, (_, i) => qMin + i) as n}
                  <button
                    type="button"
                    onclick={() => { surveyAnswers = { ...surveyAnswers, [qIdx]: n }; }}
                    class="h-10 w-10 rounded-xl font-mono text-sm font-bold border transition-all {surveyAnswers[qIdx] === n ? 'bg-purple-600 text-white border-purple-600' : 'bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200'}"
                  >
                    {n}
                  </button>
                {/each}
              </div>
              {#if q.labels}
                <p class="text-xs text-slate-400">{typeof q.labels === 'string' ? q.labels : `${q.labels.min || ''} – ${q.labels.max || ''}`}</p>
              {/if}
            {:else}
              <textarea
                value={surveyAnswers[qIdx] || ''}
                oninput={(e) => { surveyAnswers = { ...surveyAnswers, [qIdx]: (e.currentTarget as HTMLTextAreaElement).value }; }}
                placeholder="Your response..."
                rows="2"
                class="w-full rounded-xl px-3 py-2 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 text-sm resize-none"
              ></textarea>
            {/if}
          </div>
        {/each}

        <input
          type="text"
          bind:value={guestName}
          placeholder="Your name (optional)"
          disabled={readOnly}
          class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition disabled:opacity-50"
        />

        <button
          onclick={handleSurveySubmit}
          class="btn-primary w-full flex items-center justify-center gap-2 py-3 text-base"
          disabled={readOnly || isSubmitting}
        >
          <Send class="w-4 h-4" /> Submit Survey
        </button>
        {#if actionError}<p class="text-red-500 text-sm text-center" role="alert">{actionError}</p>{/if}
      </div>
    {/if}

  <!-- QNA -->
  {:else if isQna}
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
          <button onclick={() => handleUpvote(response.id)} disabled={readOnly} aria-label={`Upvote (${response.upvotes} votes)`} class="flex flex-col items-center text-slate-400 hover:text-purple-600 transition-colors shrink-0 disabled:opacity-50">
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

  <!-- WORD CLOUD -->
  {:else if isWordCloud}
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

  <!-- FEEDBACK / RATING ONLY -->
  {:else if isRatingOnly}
    {#if submitted}
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-center animate-slide-up" role="status" aria-live="polite">
        <CheckCircle2 class="w-12 h-12 text-emerald-500 mx-auto mb-3" />
        <p class="font-semibold text-slate-900 dark:text-white">Thanks for rating!</p>
      </div>
    {:else}
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
          <Send class="w-4 h-4" /> Submit Rating
        </button>
        {#if actionError}<p class="text-red-500 text-sm text-center" role="alert">{actionError}</p>{/if}
      </form>
    {/if}

  <!-- FEEDBACK (TEXT) -->
  {:else}
    {#if submitted}
      <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-center animate-slide-up" role="status" aria-live="polite">
        <CheckCircle2 class="w-12 h-12 text-emerald-500 mx-auto mb-3" />
        <p class="font-semibold text-slate-900 dark:text-white">Thanks for your feedback!</p>
      </div>
    {:else}
      <form onsubmit={(e) => { e.preventDefault(); handleTextSubmit(); }}>
        <input type="text" bind:value={guestName} placeholder="Your name (optional)" disabled={readOnly}
          class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition mb-2 disabled:opacity-50" />
        <textarea bind:value={inputValue} placeholder="Share your thoughts..." rows="4" disabled={readOnly}
          class="w-full rounded-xl px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition mb-2 resize-none disabled:opacity-50"></textarea>
        <button type="submit" class="btn-primary w-full flex items-center justify-center gap-2" disabled={readOnly || isSubmitting}>
          <Send class="w-4 h-4" /> Submit Feedback
        </button>
        {#if actionError}<p class="text-red-500 text-sm mt-2 text-center" role="alert">{actionError}</p>{/if}
      </form>
    {/if}
  {/if}

<!-- ── SCREEN / PROJECTOR VARIANT ────────────────────────── -->
{:else if variant === 'screen'}
  <div class="flex flex-col gap-4 w-full h-full justify-between">
    <div class="text-center space-y-1">
      <div class="inline-flex items-center gap-2 bg-purple-500/10 text-purple-600 dark:text-purple-400 text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full border border-purple-500/20">
        <svelte:component this={typeIcon} class="w-3.5 h-3.5" /> {typeLabel}
      </div>
      <h1 class="font-heading font-bold text-slate-900 dark:text-slate-100 leading-snug" style={getFitTitleStyle(displayPrompt, 'question')}>{displayPrompt}</h1>
      <p class="text-slate-400 text-xs">{responses.length} response{responses.length === 1 ? '' : 's'}</p>
    </div>

    <!-- POLL & MULTIPLE CHOICE & QUIZ SCREEN -->
    {#if isPoll || isMultipleChoice || isQuiz}
      <div class="space-y-3 max-w-xl mx-auto w-full my-auto">
        {#if isQuiz && cj.reveal_answer}
          <div class="flex items-center justify-between px-3 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-semibold">
            <span class="flex items-center gap-1.5"><Check class="w-4 h-4" /> Answer Revealed</span>
            <span>{quizStats.percentCorrect}% correct ({quizStats.correct}/{quizStats.total})</span>
          </div>
        {/if}

        {#each pollResults() as row, i}
          {@const hues = ['bg-purple-600', 'bg-emerald-500', 'bg-cyan-500', 'bg-amber-500', 'bg-rose-500']}
          {@const isRevealedCorrect = isQuiz && cj.reveal_answer && row.isCorrect}
          <div class="space-y-1">
            <div class="flex items-center justify-between text-sm sm:text-base">
              <span class="font-semibold flex items-center gap-1.5 {isRevealedCorrect ? 'text-emerald-600 dark:text-emerald-400 font-bold' : 'text-slate-800 dark:text-slate-200'}">
                {row.label}
                {#if isRevealedCorrect}
                  <span class="inline-flex items-center gap-1 text-[11px] bg-emerald-500 text-white px-2 py-0.5 rounded-full uppercase tracking-wider font-bold">
                    <Check class="w-3 h-3" /> Correct
                  </span>
                {/if}
              </span>
              <span class="font-mono font-bold {isRevealedCorrect ? 'text-emerald-600 dark:text-emerald-400' : 'text-purple-600 dark:text-purple-400'}">{row.percent}%</span>
            </div>
            <div class="relative h-9 bg-slate-100 dark:bg-slate-950 rounded-xl overflow-hidden border {isRevealedCorrect ? 'border-emerald-500 ring-2 ring-emerald-500/30' : 'border-slate-200 dark:border-slate-800'}">
              <div
                class="absolute inset-y-0 left-0 rounded-xl transition-all duration-700 {isRevealedCorrect ? 'bg-emerald-500' : hues[i % hues.length]}"
                style={`width: ${row.percent}%; min-width: ${row.percent > 0 ? '12px' : '0'}`}
              ></div>
              <span class="absolute inset-y-0 right-3 flex items-center text-slate-500 dark:text-slate-400 text-xs font-mono">{row.count}</span>
            </div>
          </div>
        {/each}
      </div>

    <!-- SCALE SCREEN -->
    {:else if isScale}
      {@const res = scaleResults()}
      <div class="max-w-xl mx-auto w-full my-auto space-y-6">
        <div class="text-center">
          <div class="text-5xl sm:text-6xl font-heading font-extrabold text-teal-600 dark:text-teal-400 tracking-tight">
            {res.average}
          </div>
          <p class="text-xs text-slate-400 uppercase tracking-widest mt-1">Average Rating (out of {scaleMax})</p>
        </div>

        <div class="space-y-2">
          <div class="grid gap-1.5" style={`grid-template-columns: repeat(${res.distribution.length}, minmax(0, 1fr));`}>
            {#each res.distribution as d}
              <div class="flex flex-col items-center gap-1.5">
                <div class="relative w-full h-24 bg-slate-100 dark:bg-slate-950 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-800 flex flex-col justify-end">
                  <div class="w-full bg-teal-500 rounded-t-lg transition-all duration-700" style={`height: ${d.percent}%; min-height: ${d.percent > 0 ? '4px' : '0'}`}></div>
                </div>
                <span class="font-mono text-xs font-bold text-slate-700 dark:text-slate-300">{d.point}</span>
                <span class="font-mono text-[10px] text-slate-400">{d.count}</span>
              </div>
            {/each}
          </div>

          {#if scaleMinLabel || scaleMaxLabel}
            <div class="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 pt-1">
              <span>{scaleMinLabel}</span>
              <span>{scaleMaxLabel}</span>
            </div>
          {/if}
        </div>
      </div>

    <!-- SURVEY SCREEN (AGGREGATES ONLY) -->
    {:else if isSurvey}
      {@const aggs = surveyAggregates()}
      <div class="max-h-[60vh] overflow-y-auto space-y-4 max-w-2xl mx-auto w-full my-auto px-2">
        {#each aggs as q}
          <div class="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 p-4 space-y-3">
            <div class="flex items-center justify-between">
              <h3 class="font-bold text-slate-900 dark:text-white text-sm">
                <span class="text-purple-600 font-mono text-xs">{q.qIndex + 1}.</span> {q.prompt}
              </h3>
              <span class="text-xs text-slate-400 font-mono">{q.totalResponses} answer{q.totalResponses === 1 ? '' : 's'}</span>
            </div>

            {#if q.type === 'single_choice'}
              <div class="space-y-1.5">
                {#each q.optionsData as opt, oi}
                  {@const colors = ['bg-purple-600', 'bg-emerald-500', 'bg-cyan-500', 'bg-amber-500']}
                  <div class="space-y-0.5">
                    <div class="flex justify-between text-xs font-medium">
                      <span class="text-slate-700 dark:text-slate-300">{opt.label}</span>
                      <span class="font-mono text-purple-600 dark:text-purple-400">{opt.percent}% ({opt.count})</span>
                    </div>
                    <div class="h-4 bg-slate-100 dark:bg-slate-900 rounded-full overflow-hidden">
                      <div class="h-full rounded-full {colors[oi % colors.length]}" style={`width: ${opt.percent}%; min-width: ${opt.percent > 0 ? '6px' : '0'}`}></div>
                    </div>
                  </div>
                {/each}
              </div>
            {:else if q.type === 'scale'}
              <div class="flex items-center gap-4">
                <div class="text-2xl font-bold font-mono text-teal-600 dark:text-teal-400">{q.average}</div>
                <div class="flex-1">
                  <p class="text-xs text-slate-400">Average score (scale {q.min}–{q.max})</p>
                </div>
              </div>
            {:else}
              <p class="text-xs text-slate-500 dark:text-slate-400 italic">
                {q.totalResponses} text response{q.totalResponses === 1 ? '' : 's'} recorded
              </p>
            {/if}
          </div>
        {/each}
      </div>

    <!-- QNA SCREEN -->
    {:else if isQna}
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

    <!-- WORD CLOUD SCREEN -->
    {:else if isWordCloud}
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

    <!-- RATING ONLY SCREEN -->
    {:else if isRatingOnly}
      <div class="text-center py-6 my-auto">
        <div class="text-6xl font-heading font-bold text-amber-500">{averageRating().toFixed(1)}</div>
        <div class="flex items-center justify-center gap-1 mt-2">
          {#each [1, 2, 3, 4, 5] as n}
            <Star class="w-6 h-6 {n <= Math.round(averageRating()) ? 'text-amber-400 fill-amber-400' : 'text-slate-300 dark:text-slate-700'}" />
          {/each}
        </div>
      </div>

    <!-- FEEDBACK SCREEN -->
    {:else}
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

<!-- ── MODERATOR VARIANT ────────────────────────── -->
{:else}
  <div class="card p-4 sm:p-5 space-y-4">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <svelte:component this={typeIcon} class="w-5 h-5 text-purple-600 dark:text-purple-400" />
        <span class="text-lg font-bold">{typeLabel}</span>
      </div>
      <div class="flex items-center gap-2">
        <!-- Reveal Answer intentionally lives only in DeckView's toolbar now
             (the normal moderator view), not here — having it in both
             places would duplicate the same control across two screens. -->
        <button onclick={onToggleEdit} class="btn-secondary text-xs px-3 py-1.5">{editing ? 'Cancel' : 'Edit'}</button>
      </div>
    </div>

    {#if !editing}
      <p class="font-heading font-medium text-surface-800 dark:text-surface-100" style={getFitTitleStyle(displayPrompt, 'question')}>{displayPrompt}</p>
    {:else}
      <!-- MODERATOR EDIT FORM -->
      <div class="space-y-3 pt-2 border-t border-surface-200 dark:border-surface-800">
        {#if isPoll || isMultipleChoice}
          <label class="block text-xs font-semibold uppercase tracking-wider text-surface-500">Question</label>
          <input class="input-field" type="text" bind:value={editQuestion} placeholder="Question..." />
          
          <label class="block text-xs font-semibold uppercase tracking-wider text-surface-500 pt-1">Options</label>
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
          <div class="flex items-center gap-2 pt-2">
            <button onclick={addEditOption} class="btn-secondary text-xs">+ Add option</button>
            <button onclick={saveEdit} class="btn-primary text-xs">Save</button>
          </div>

        {:else if isQuiz}
          <label class="block text-xs font-semibold uppercase tracking-wider text-surface-500">Quiz Question</label>
          <input class="input-field" type="text" bind:value={editQuestion} placeholder="Quiz Question..." />

          <label class="block text-xs font-semibold uppercase tracking-wider text-surface-500 pt-1">Options (Select Correct Answer)</label>
          <div class="space-y-2">
            {#each editOptions as option, index (index)}
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  onclick={() => (editCorrectAnswer = option)}
                  class="h-8 px-2.5 rounded-lg border text-xs font-semibold flex items-center gap-1 transition {editCorrectAnswer === option ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 font-bold' : 'border-surface-200 text-surface-400 hover:border-surface-300'}"
                  title="Mark as correct answer"
                >
                  <Check class="w-3.5 h-3.5" />
                  {editCorrectAnswer === option ? 'Correct' : 'Mark'}
                </button>
                <input class="input-field flex-1" type="text" value={option}
                  oninput={(e) => updateEditOption(index, (e.currentTarget as HTMLInputElement).value)}
                  placeholder={`Option ${index + 1}`} />
                <button onclick={() => removeEditOption(index)} class="btn-danger text-xs px-3 py-1.5">Remove</button>
              </div>
            {/each}
          </div>
          <div class="flex items-center gap-2 pt-2">
            <button onclick={addEditOption} class="btn-secondary text-xs">+ Add option</button>
            <button onclick={saveEdit} class="btn-primary text-xs">Save Quiz</button>
          </div>

        {:else if isScale}
          <label class="block text-xs font-semibold uppercase tracking-wider text-surface-500">Prompt</label>
          <input class="input-field" type="text" bind:value={editPrompt} placeholder="Prompt..." />
          <div class="grid grid-cols-3 gap-3">
            <div>
              <label class="block text-xs text-surface-500 mb-1">Min</label>
              <input class="input-field" type="number" bind:value={editMin} />
            </div>
            <div>
              <label class="block text-xs text-surface-500 mb-1">Max</label>
              <input class="input-field" type="number" bind:value={editMax} />
            </div>
            <div>
              <label class="block text-xs text-surface-500 mb-1">Step</label>
              <input class="input-field" type="number" bind:value={editStep} min="1" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-surface-500 mb-1">Min Label</label>
              <input class="input-field" type="text" bind:value={editMinLabel} placeholder="e.g. 1 = Disagree" />
            </div>
            <div>
              <label class="block text-xs text-surface-500 mb-1">Max Label</label>
              <input class="input-field" type="text" bind:value={editMaxLabel} placeholder="e.g. 10 = Agree" />
            </div>
          </div>
          <button onclick={saveEdit} class="btn-primary text-xs mt-2">Save Scale</button>

        {:else if isSurvey}
          <label class="block text-xs font-semibold uppercase tracking-wider text-surface-500">Survey Title / Prompt</label>
          <input class="input-field" type="text" bind:value={editPrompt} placeholder="Survey title..." />
          
          <div class="space-y-3 pt-2">
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold uppercase tracking-wider text-surface-500">Questions</span>
              <button onclick={addSurveyQuestion} class="btn-secondary text-xs flex items-center gap-1"><Plus class="w-3 h-3" /> Add Question</button>
            </div>
            {#each editQuestions as q, qi (qi)}
              <div class="rounded-xl border border-surface-200 dark:border-surface-800 p-3 space-y-2 bg-surface-50/50 dark:bg-surface-900/50">
                <!-- Header row: prompt + type selector + delete -->
                <div class="flex items-start gap-2">
                  <span class="font-mono text-[10px] text-surface-400 pt-2 w-4 shrink-0">{qi + 1}.</span>
                  <input class="input-field flex-1" type="text" bind:value={q.prompt} placeholder="Question prompt..." />
                  <select bind:value={q.response_type} class="input-field text-xs w-36 shrink-0">
                    <option value="single_choice">Single Choice</option>
                    <option value="scale">Scale</option>
                    <option value="text">Text</option>
                  </select>
                  <button onclick={() => removeSurveyQuestion(qi)} class="btn-danger text-xs p-2 shrink-0"><Trash2 class="w-3.5 h-3.5" /></button>
                </div>
                <!-- Type-specific config -->
                {#if q.response_type === 'single_choice'}
                  <div class="pl-6 space-y-1.5">
                    <span class="text-[10px] uppercase tracking-wider text-surface-400 font-semibold">Answer Options</span>
                    {#each (q.options || []) as opt, oi}
                      <div class="flex items-center gap-2">
                        <input
                          class="input-field flex-1 text-xs"
                          type="text"
                          value={opt}
                          oninput={(e) => {
                            const opts = [...(q.options || [])];
                            opts[oi] = (e.currentTarget as HTMLInputElement).value;
                            q.options = opts;
                          }}
                          placeholder={`Option ${oi + 1}`}
                        />
                        <button
                          onclick={() => { q.options = (q.options || []).filter((_: string, i: number) => i !== oi); }}
                          class="text-red-400 hover:text-red-600 text-xs p-1"
                        >✕</button>
                      </div>
                    {/each}
                    <button
                      onclick={() => { q.options = [...(q.options || []), `Option ${(q.options || []).length + 1}`]; }}
                      class="text-xs text-purple-600 dark:text-purple-400 hover:underline font-semibold"
                    >+ Add option</button>
                  </div>
                {:else if q.response_type === 'scale'}
                  <div class="pl-6 space-y-2">
                    <span class="text-[10px] uppercase tracking-wider text-surface-400 font-semibold">Scale Config</span>
                    <div class="grid grid-cols-3 gap-2">
                      <div>
                        <label class="block text-[10px] text-surface-400 mb-0.5">Min</label>
                        <input class="input-field text-xs" type="number"
                          value={typeof q.min === 'number' ? q.min : 1}
                          oninput={(e) => { q.min = parseInt((e.currentTarget as HTMLInputElement).value) || 1; }}
                        />
                      </div>
                      <div>
                        <label class="block text-[10px] text-surface-400 mb-0.5">Max</label>
                        <input class="input-field text-xs" type="number"
                          value={typeof q.max === 'number' ? q.max : 5}
                          oninput={(e) => { q.max = parseInt((e.currentTarget as HTMLInputElement).value) || 5; }}
                        />
                      </div>
                      <div>
                        <label class="block text-[10px] text-surface-400 mb-0.5">Step</label>
                        <input class="input-field text-xs" type="number" min="1"
                          value={typeof q.step === 'number' ? q.step : 1}
                          oninput={(e) => { q.step = parseInt((e.currentTarget as HTMLInputElement).value) || 1; }}
                        />
                      </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                      <div>
                        <label class="block text-[10px] text-surface-400 mb-0.5">Min Label</label>
                        <input class="input-field text-xs" type="text" bind:value={q.min_label} placeholder="e.g. Strongly Disagree" />
                      </div>
                      <div>
                        <label class="block text-[10px] text-surface-400 mb-0.5">Max Label</label>
                        <input class="input-field text-xs" type="text" bind:value={q.max_label} placeholder="e.g. Strongly Agree" />
                      </div>
                    </div>
                  </div>
                {:else}
                  <div class="pl-6">
                    <p class="text-[10px] text-surface-400 italic">Participants type a free-form text answer.</p>
                  </div>
                {/if}
              </div>
            {/each}
          </div>
          <button onclick={saveEdit} class="btn-primary text-xs mt-2">Save Survey</button>

        {:else}
          <input class="input-field" type="text" bind:value={editPrompt} placeholder="Prompt..." />
          <button onclick={saveEdit} class="btn-primary text-xs mt-2">Save prompt</button>
        {/if}
      </div>
    {/if}

    <!-- MODERATOR LIVE RESULTS DISPLAY -->
    {#if isPoll || isMultipleChoice}
      <div class="border border-surface-200 dark:border-surface-800 rounded-xl p-4">
        <div class="text-sm font-semibold mb-3">Live results ({responses.length} responses)</div>
        <div class="flex items-end gap-4">
          {#each pollResults() as row}
            <div class="flex flex-col items-center gap-2 flex-1">
              <div class="relative w-full h-28 bg-surface-100 dark:bg-surface-800 rounded-lg overflow-hidden">
                <div class="absolute bottom-0 left-0 right-0 bg-brand-500 rounded-lg transition-all duration-500"
                  style={`height: ${row.percent}%; min-height: ${row.percent > 0 ? '6px' : '0px'}`}></div>
              </div>
              <div class="text-xs text-surface-500 truncate max-w-[5rem]" title={row.label}>{row.label}</div>
              <div class="text-xs text-surface-400">{row.percent}% ({row.count})</div>
            </div>
          {/each}
        </div>
      </div>

    {:else if isQuiz}
      <div class="border border-surface-200 dark:border-surface-800 rounded-xl p-4 space-y-3">
        <div class="flex items-center justify-between">
          <div class="text-sm font-semibold">Quiz Results</div>
          <div class="text-xs font-mono text-emerald-600 dark:text-emerald-400 font-bold">
            {quizStats.percentCorrect}% correct ({quizStats.correct}/{quizStats.total})
          </div>
        </div>
        <div class="flex items-end gap-4">
          {#each pollResults() as row}
            <div class="flex flex-col items-center gap-2 flex-1">
              <div class="relative w-full h-28 bg-surface-100 dark:bg-surface-800 rounded-lg overflow-hidden">
                <div class="absolute bottom-0 left-0 right-0 {row.isCorrect ? 'bg-emerald-500' : 'bg-brand-500'} rounded-lg transition-all duration-500"
                  style={`height: ${row.percent}%; min-height: ${row.percent > 0 ? '6px' : '0px'}`}></div>
              </div>
              <div class="text-xs text-surface-500 flex items-center gap-1 truncate max-w-[5rem]" title={row.label}>
                {#if row.isCorrect}<Check class="w-3 h-3 text-emerald-500 inline shrink-0" />{/if}
                <span class="truncate">{row.label}</span>
              </div>
              <div class="text-xs text-surface-400">{row.percent}% ({row.count})</div>
            </div>
          {/each}
        </div>
      </div>

    {:else if isScale}
      {@const res = scaleResults()}
      <div class="border border-surface-200 dark:border-surface-800 rounded-xl p-4 text-center space-y-2">
        <div class="text-4xl font-bold font-mono text-teal-600 dark:text-teal-400">{res.average}</div>
        <div class="text-xs text-surface-400">Average score ({res.totalCount} ratings)</div>
      </div>

    {:else if isSurvey}
      {@const aggs = surveyAggregates()}
      <div class="border border-surface-200 dark:border-surface-800 rounded-xl p-4 space-y-3">
        <div class="text-sm font-semibold">Survey Summary ({responses.length} responses)</div>
        <div class="space-y-2">
          {#each aggs as q}
            <div class="text-xs flex items-center justify-between p-2 rounded-lg bg-surface-100 dark:bg-surface-800">
              <span class="font-medium text-surface-800 dark:text-surface-200 truncate max-w-xs">{q.qIndex + 1}. {q.prompt}</span>
              <span class="font-mono text-surface-500">{q.totalResponses} answers {#if q.average}(avg {q.average}){/if}</span>
            </div>
          {/each}
        </div>
      </div>

    {:else if isQna}
      {#if responses.length === 0}
        <div class="text-sm text-surface-400">No questions yet.</div>
      {:else}
        <div class="space-y-3 max-h-60 overflow-y-auto">
          {#each responses as response (response.id)}
            <div class="p-3 rounded-xl border border-surface-200 dark:border-surface-800">
              <div class="text-xs text-surface-500 mb-1">{response.name || response.guest_identifier}</div>
              <div class="text-sm">{response.value}</div>
            </div>
          {/each}
        </div>
      {/if}

    {:else if isWordCloud}
      {#if responses.length === 0}
        <div class="text-sm text-surface-400">No responses yet.</div>
      {:else}
        <div class="border border-surface-200 dark:border-surface-800 rounded-xl p-4 sm:p-5 flex flex-wrap items-center justify-center gap-3 min-h-[140px]">
          {#each wordCloudData() as item}
            <span class="text-brand-600 font-semibold transition-all"
              style={`font-size: ${item.size}rem; opacity: ${0.5 + (item.count / (responses.length || 1)) * 0.5}`}>{item.word}</span>
          {/each}
        </div>
        <div class="text-xs text-surface-400">{responses.length} response{responses.length === 1 ? '' : 's'}</div>
      {/if}

    {:else if isRatingOnly}
      <div class="border border-surface-200 dark:border-surface-800 rounded-xl p-4 text-center">
        <div class="text-4xl font-bold text-amber-500">{averageRating().toFixed(1)}</div>
        <div class="text-xs text-surface-400 mt-1">{responses.length} rating{responses.length === 1 ? '' : 's'}</div>
      </div>

    {:else}
      {#if responses.length === 0}
        <div class="text-sm text-surface-400">No feedback yet.</div>
      {:else}
        <div class="space-y-3 max-h-60 overflow-y-auto">
          {#each responses as response (response.id)}
            <div class="p-3 rounded-xl border border-surface-200 dark:border-surface-800">
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