<script lang="ts">
  import {
    Plus, Trash2, Copy, GripVertical, ChevronUp, ChevronDown, Layout, Type,
    Bold, Italic, Underline, Strikethrough, AlignLeft, AlignCenter, AlignRight,
    List, ListOrdered, Link, Code, Eraser, Undo2, Redo2, Highlighter,
    SlidersHorizontal, Eye, Upload, FileText, BarChart3, MessageSquare, Cloud, AlignLeft as FeedbackIcon,
    Sparkles, Image as ImageIcon, Columns, Heading1, Heading2, Check, Video, ListChecks, HelpCircle, Sliders, ClipboardList, Star, Tv
  } from 'lucide-svelte';
  import ZoomableImageViewer from '$lib/components/ZoomableImageViewer.svelte';
  import { getPageImageUrl } from '$lib/api';
  import { theme } from '$lib/theme';
  import { getFitTitleStyle } from '$lib/fitTitle';
  import { sanitizeRichHtml } from '$lib/sanitizeHtml';
  import { validQuizAnswer } from '$lib/quiz';

  let {
    sessionId,
    slides = [],
    activeSlideId = null,
    saveState = 'idle' as 'idle' | 'saving' | 'saved',
    canUndo = false,
    canRedo = false,
    onSelectSlide,
    onCreateSlide,
    onUpdateSlideContent,
    onDeleteSlide,
    onDuplicateSlide,
    onReorderSlides,
    onUploadFile,
    onUndo,
    onRedo,
    onDirtyChange,
    onSaveReady
  }: {
    sessionId: string;
    slides: any[];
    activeSlideId: string | null;
    saveState?: 'idle' | 'saving' | 'saved';
    canUndo?: boolean;
    canRedo?: boolean;
    onSelectSlide: (id: string) => void;
    onCreateSlide: (type: string, layout?: string) => void;
    onUpdateSlideContent: (slideId: string, contentJson: Record<string, unknown>) => void;
    onDeleteSlide: (slideId: string) => void;
    onDuplicateSlide?: (slideId: string) => void;
    onReorderSlides?: (slideIds: string[]) => void;
    onUploadFile?: (slideId: string, file: File) => void;
    onUndo?: () => void;
    onRedo?: () => void;
    onDirtyChange?: (dirty: boolean) => void;
    onSaveReady?: (save: (() => Promise<void>) | null) => void;
  } = $props();

  const activeSlide = $derived(slides.find(s => s.id === activeSlideId) || slides[0] || null);
  const activeType = $derived(activeSlide?.type?.toUpperCase() || 'CONTENT');
  const activeLayout = $derived(activeSlide?.content_json?.layout || (activeType === 'CONTENT' ? 'title_content' : 'interactive'));

  const isQuiz = $derived(activeSlide?.content_json?.interaction_type === 'QUIZ' || activeSlide?.content_json?.mode === 'quiz');
  const isMultipleChoice = $derived(activeSlide?.content_json?.interaction_type === 'MULTIPLE_CHOICE' || activeSlide?.content_json?.mode === 'multiple_choice');
  const isScale = $derived(activeSlide?.content_json?.interaction_type === 'SCALE' || activeSlide?.content_json?.mode === 'scale');
  const isSurvey = $derived(activeSlide?.content_json?.interaction_type === 'SURVEY' || activeSlide?.content_json?.mode === 'survey');
  const isRatingOnly = $derived(activeSlide?.content_json?.mode === 'rating_only' || activeSlide?.content_json?.interaction_type === 'RATING');

  let showAddMenu = $state(false);
  let showLayoutMenu = $state(false);
  let showProperties = $state(true);

  // Local buffered fields for active slide elements
  let localTitle = $state('');
  let localSubtitle = $state('');
  let localBody = $state('');
  let localBody2 = $state('');
  let localQuestion = $state('');
  let localOptions = $state<string[]>([]);
  let localPrompt = $state('');
  let localVideoUrl = $state('');
  // Quiz: the correct answer is tracked by option position while editing, so
  // renaming or removing options can never leave it pointing at stale text.
  let localCorrectIndex = $state<number | null>(null);
  let localRevealAnswer = $state(false);
  // Why the marked option can't be saved as the answer right now: 'blank'
  // while its text is being retyped, 'duplicate' when another option has the
  // same text (the answer would be ambiguous), 'none' when nothing is marked.
  const correctOptionIssue = $derived.by((): 'none' | 'blank' | 'duplicate' | null => {
    if (localCorrectIndex === null) return 'none';
    const text = localOptions[localCorrectIndex] ?? '';
    if (!text.trim()) return 'blank';
    if (localOptions.filter((o) => o === text).length > 1) return 'duplicate';
    return null;
  });
  let localMin = $state(1);
  let localMax = $state(10);
  let localStep = $state(1);
  let localMinLabel = $state('');
  let localMaxLabel = $state('');
  let localQuestions = $state<any[]>([]);

  // Active rich text element ref
  let bodyEditorEl: HTMLDivElement | null = $state(null);
  let body2EditorEl: HTMLDivElement | null = $state(null);
  let focusedEditorTag = $state<'body' | 'body2' | null>('body');

  // Toolbar dropdown states
  let showFontFamily = $state(false);
  let showFontSize = $state(false);
  let showColorPicker = $state(false);
  let showHighlightPicker = $state(false);

  const TEXT_COLORS = [
    '#ffffff', '#f8fafc', '#cbd5e1', '#64748b', '#0f172a',
    '#ef4444', '#f97316', '#f59e0b', '#84cc16', '#10b981',
    '#06b6d4', '#3b82f6', '#6366f1', '#a855f7', '#ec4899',
  ];
  const HIGHLIGHT_COLORS = [
    '#fef08a', '#bbf7d0', '#bae6fd', '#e9d5ff', '#fecaca',
    '#fed7aa', '#d9f99d', '#f5d0fe', '#334155', 'transparent',
  ];
  const FONT_SIZES = ['14px','16px','18px','22px','26px','32px','40px','48px'];
  const FONT_FAMILIES = [
    { label: 'Inter (Sans)', value: 'Inter, system-ui, sans-serif' },
    { label: 'Glacial (Modern)', value: "'Glacial Indifference', Inter, sans-serif" },
    { label: 'JetBrains (Mono)', value: "'JetBrains Mono', monospace" },
    { label: 'Georgia (Serif)', value: 'Georgia, serif' },
  ];

  let saveTimer: ReturnType<typeof setTimeout> | null = null;
  let savePending = $state(false);
  function debouncedSave(updates: Record<string, unknown> = {}) {
    if (saveTimer) clearTimeout(saveTimer);
    savePending = true;
    saveTimer = setTimeout(() => {
      void saveActiveSlideContent(updates);
    }, 250);
  }

  /** Load stored rich text into a contenteditable — always sanitized, since
   * assigning innerHTML would otherwise run any handlers it carries. The
   * server's sanitized HTML serializes slightly differently from the
   * browser's own innerHTML, so the editor the moderator is typing in is left
   * alone for the same slide (rewriting it would reset the caret). */
  let editorSyncedSlideId: string | null = null;
  function syncRichEditor(el: HTMLDivElement | null, html: string, slideChanged: boolean) {
    if (!el || (!slideChanged && document.activeElement === el)) return;
    const safe = sanitizeRichHtml(html);
    if (el.innerHTML !== safe) el.innerHTML = safe;
  }

  // Synchronize local edit buffer when active slide changes
  $effect(() => {
    if (activeSlide) {
      const cj = activeSlide.content_json || {};
      localTitle = cj.title ?? '';
      localSubtitle = cj.subtitle ?? '';
      localBody = cj.body ?? '';
      localBody2 = cj.body2 ?? '';
      localQuestion = cj.question ?? '';
      localOptions = cj.options ? [...cj.options] : ['Option 1', 'Option 2'];
      localPrompt = cj.prompt ?? '';
      localVideoUrl = cj.video_url || cj.url || '';
      // Read from cj, not localOptions: reading that $state here would make
      // every option keystroke re-run this effect and reset the buffers.
      const correctIdx = typeof cj.correct_answer === 'string' && cj.correct_answer !== '' && Array.isArray(cj.options)
        ? cj.options.indexOf(cj.correct_answer)
        : -1;
      localCorrectIndex = correctIdx === -1 ? null : correctIdx;
      localRevealAnswer = Boolean(cj.reveal_answer);
      localMin = typeof cj.min === 'number' ? cj.min : 1;
      localMax = typeof cj.max === 'number' ? cj.max : 10;
      localStep = typeof cj.step === 'number' ? cj.step : 1;
      localMinLabel = cj.min_label ?? '';
      localMaxLabel = cj.max_label ?? '';
      localQuestions = Array.isArray(cj.questions) ? JSON.parse(JSON.stringify(cj.questions)) : [];

      const slideChanged = activeSlide.id !== editorSyncedSlideId;
      editorSyncedSlideId = activeSlide.id;
      if (slideChanged) {
        // Pending-save state belongs to the slide that was left (its unsaved
        // edits were discarded via the page's confirm): a pending debounce
        // must not fire for the new slide, and an autosave paused by that
        // slide's quiz answer must not leave the new one looking unsaved.
        if (saveTimer) {
          clearTimeout(saveTimer);
          saveTimer = null;
        }
        savePending = false;
      }
      setTimeout(() => {
        syncRichEditor(bodyEditorEl, localBody, slideChanged);
        syncRichEditor(body2EditorEl, localBody2, slideChanged);
      }, 0);
    }
  });

  /** `force` is for explicit saves (the leave-page prompt). Autosaves of a
   * quiz wait while the marked option is blank or ambiguous: saving drops
   * blank options, which would silently unmark the answer mid-retype. */
  async function saveActiveSlideContent(updates: Record<string, unknown> = {}, { force = false } = {}) {
    if (!activeSlide) return;
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    const quizAnswerUnsettled = isQuiz && (correctOptionIssue === 'blank' || correctOptionIssue === 'duplicate');
    if (quizAnswerUnsettled && !force) {
      savePending = true; // shown as unsaved; saved once the option text is fixed
      return;
    }
    const cj = { ...(activeSlide.content_json || {}) };
    if (activeType === 'CONTENT') {
      cj.title = localTitle;
      cj.subtitle = localSubtitle;
      cj.body = localBody;
      cj.body2 = localBody2;
      cj.video_url = localVideoUrl;
    } else if (activeType === 'POLL') {
      cj.question = localQuestion;
      cj.options = localOptions.filter(o => o.trim() !== '');
      if (isQuiz) {
        const stored = activeSlide.content_json || {};
        if (localCorrectIndex !== null && !quizAnswerUnsettled) {
          cj.correct_answer = localOptions[localCorrectIndex];
        } else if (localCorrectIndex === null && stored.correct_answer && !validQuizAnswer(stored)) {
          // Untouched invalid legacy answer: kept as stored (never treated as correct).
          cj.correct_answer = stored.correct_answer;
        } else {
          cj.correct_answer = '';
        }
        // Revealing requires a valid answer (same rule as the server, $lib/quiz).
        cj.reveal_answer = localRevealAnswer && validQuizAnswer(cj) !== '';
      }
    } else if (activeType === 'FEEDBACK') {
      cj.prompt = localPrompt;
      if (isScale) {
        cj.min = localMin;
        cj.max = localMax;
        cj.step = localStep;
        cj.min_label = localMinLabel;
        cj.max_label = localMaxLabel;
      } else if (isSurvey) {
        cj.questions = localQuestions;
      }
    } else if (activeType === 'QNA' || activeType === 'WORD_CLOUD') {
      cj.prompt = localPrompt;
    }
    const finalContent = { ...cj, ...updates };
    const savedSlideId = activeSlide.id;
    await onUpdateSlideContent(savedSlideId, finalContent);
    // If the moderator moved to another slide (or queued newer edits) while
    // this save was in flight, the pending state is no longer this save's.
    if (activeSlide?.id === savedSlideId && !saveTimer) savePending = false;
  }

  function changeLayout(newLayout: string) {
    showLayoutMenu = false;
    void saveActiveSlideContent({ layout: newLayout });
  }

  // ExecCommand for rich text body editing
  function getActiveEditor(): HTMLDivElement | null {
    return focusedEditorTag === 'body2' ? body2EditorEl : bodyEditorEl;
  }

  function exec(cmd: string, value?: string) {
    const el = getActiveEditor();
    el?.focus();
    // eslint-disable-next-line @typescript-eslint/no-deprecated
    document.execCommand(cmd, false, value ?? undefined);
    if (focusedEditorTag === 'body2' && body2EditorEl) {
      localBody2 = body2EditorEl.innerHTML;
    } else if (bodyEditorEl) {
      localBody = bodyEditorEl.innerHTML;
    }
    void saveActiveSlideContent();
  }

  function toggleBlock(tag: string) { exec('formatBlock', `<${tag}>`); }
  function applyFontFamily(f: string) { exec('fontName', f); showFontFamily = false; }
  function applyFontSize(s: string) { exec('insertHTML', `<span style="font-size:${s}">${window.getSelection()?.toString() || '&#8203;'}</span>`); showFontSize = false; }
  function applyColor(c: string) { exec('foreColor', c); showColorPicker = false; }
  function applyHighlight(c: string) { exec('hiliteColor', c); showHighlightPicker = false; }
  function insertLink() { const u = prompt('Enter URL:'); if (u) exec('createLink', u); }

  // Drag and drop reordering
  let draggedIndex: number | null = $state(null);
  function handleDragStart(index: number) { draggedIndex = index; }
  function handleDrop(targetIndex: number) {
    if (draggedIndex === null || draggedIndex === targetIndex) return;
    const ids = slides.map(s => s.id);
    const [moved] = ids.splice(draggedIndex, 1);
    ids.splice(targetIndex, 0, moved);
    draggedIndex = null;
    onReorderSlides?.(ids);
  }

  function handleFileUploadChange(e: Event) {
    const files = (e.currentTarget as HTMLInputElement).files;
    if (files && files.length > 0 && activeSlide) {
      onUploadFile?.(activeSlide.id, files[0]);
    }
  }

  function addPollOption() {
    localOptions = [...localOptions, `Option ${localOptions.length + 1}`];
    void saveActiveSlideContent();
  }
  function removePollOption(index: number) {
    localOptions = localOptions.filter((_, i) => i !== index);
    if (localCorrectIndex === index) localCorrectIndex = null;
    else if (localCorrectIndex !== null && localCorrectIndex > index) localCorrectIndex -= 1;
    void saveActiveSlideContent();
  }

  function addSurveyQuestion() {
    localQuestions = [
      ...localQuestions,
      { prompt: 'New question', response_type: 'single_choice', options: ['Option 1', 'Option 2'] }
    ];
    void saveActiveSlideContent();
  }
  function removeSurveyQuestion(idx: number) {
    localQuestions = localQuestions.filter((_, i) => i !== idx);
    void saveActiveSlideContent();
  }

  // Toolbar menus close on Escape (returning focus to their trigger) or on a
  // click anywhere outside them.
  function handleMenuKeydown(e: KeyboardEvent) {
    if (e.key !== 'Escape' || (!showAddMenu && !showLayoutMenu)) return;
    const trigger = showAddMenu ? addMenuTrigger : layoutMenuTrigger;
    showAddMenu = false;
    showLayoutMenu = false;
    trigger?.focus();
  }
  function handleMenuOutsideClick(e: MouseEvent) {
    if (!showAddMenu && !showLayoutMenu) return;
    if ((e.target as HTMLElement | null)?.closest('[data-deck-menu]')) return;
    showAddMenu = false;
    showLayoutMenu = false;
  }
  let addMenuTrigger: HTMLButtonElement | null = $state(null);
  let layoutMenuTrigger: HTMLButtonElement | null = $state(null);

  const isDirty = $derived.by(() => {
    if (!activeSlide) return false;
    if (savePending) return true;
    const cj = activeSlide.content_json || {};
    if (activeType === 'CONTENT') {
      return localTitle !== (cj.title || '') || localSubtitle !== (cj.subtitle || '') || localBody !== (cj.body || '') || localBody2 !== (cj.body2 || '') || localVideoUrl !== (cj.video_url || '');
    }
    if (activeType === 'POLL') {
      const cleaned = localOptions.map((o) => o.trim()).filter(Boolean);
      return localQuestion.trim() !== (cj.question || '') || JSON.stringify(cleaned) !== JSON.stringify(cj.options || []);
    }
    if (activeType === 'FEEDBACK' || activeType === 'QNA' || activeType === 'WORD_CLOUD') {
      return localPrompt !== (cj.prompt || '');
    }
    return false;
  });

  $effect(() => {
    onDirtyChange?.(isDirty);
  });

  $effect(() => {
    onSaveReady?.(() => saveActiveSlideContent({}, { force: true }));
    return () => onSaveReady?.(null);
  });
</script>

<svelte:window onclick={handleMenuOutsideClick} onkeydown={handleMenuKeydown} />

<div class="deck-editor flex flex-col h-full w-full bg-surface-100 dark:bg-surface-950 text-surface-900 dark:text-surface-100 rounded-2xl overflow-hidden border border-surface-200 dark:border-surface-800 shadow-2xl transition-colors">

  <!-- TOP COMPACT TOOLBAR -->
  <header class="deck-toolbar flex items-center justify-between px-3.5 py-2 bg-white dark:bg-surface-900 border-b border-surface-200 dark:border-surface-800 gap-2 select-none flex-wrap">
    
    <!-- Left Group: Undo/Redo & Add Slide -->
    <div class="flex items-center gap-1.5">
      <button onclick={onUndo} disabled={!canUndo} class="deck-btn" title="Undo (Ctrl+Z)" aria-label="Undo"><Undo2 class="w-4 h-4" /></button>
      <button onclick={onRedo} disabled={!canRedo} class="deck-btn" title="Redo (Ctrl+Y)" aria-label="Redo"><Redo2 class="w-4 h-4" /></button>
      
      <div class="h-4 w-px bg-surface-200 dark:bg-surface-800 mx-1"></div>

      <!-- Add Slide Menu Trigger -->
      <div class="relative" data-deck-menu>
        <button
          bind:this={addMenuTrigger}
          onclick={() => { showAddMenu = !showAddMenu; showLayoutMenu = false; }}
          aria-haspopup="true"
          aria-expanded={showAddMenu}
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold shadow-md transition active:scale-95"
        >
          <Plus class="w-4 h-4" />
          <span>New Slide</span>
        </button>

        {#if showAddMenu}
          <div class="absolute left-0 top-full mt-1.5 z-50 w-56 p-2 rounded-xl bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-700 shadow-2xl space-y-1">
            <div class="text-[10px] font-bold uppercase tracking-wider text-surface-500 px-2 py-1">Content Layouts</div>
            <button onclick={() => { onCreateSlide('CONTENT', 'title_content'); showAddMenu = false; }} class="deck-menu-item"><FileText class="w-3.5 h-3.5 text-brand-500" /> Content</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'image'); showAddMenu = false; }} class="deck-menu-item"><ImageIcon class="w-3.5 h-3.5 text-brand-500" /> Image</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'image_text'); showAddMenu = false; }} class="deck-menu-item"><Columns class="w-3.5 h-3.5 text-brand-500" /> Image + Text</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'two_column'); showAddMenu = false; }} class="deck-menu-item"><Columns class="w-3.5 h-3.5 text-brand-500" /> Two Column</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'video'); showAddMenu = false; }} class="deck-menu-item"><Video class="w-3.5 h-3.5 text-brand-500" /> Video</button>
            
            <div class="h-px bg-surface-200 dark:bg-surface-800 my-1"></div>
            <div class="text-[10px] font-bold uppercase tracking-wider text-surface-500 px-2 py-1">Interactions</div>
            <button onclick={() => { onCreateSlide('POLL'); showAddMenu = false; }} class="deck-menu-item"><BarChart3 class="w-3.5 h-3.5 text-emerald-500" /> Poll</button>
            <button onclick={() => { onCreateSlide('MULTIPLE_CHOICE'); showAddMenu = false; }} class="deck-menu-item"><ListChecks class="w-3.5 h-3.5 text-indigo-500" /> Multiple Choice</button>
            <button onclick={() => { onCreateSlide('QUIZ'); showAddMenu = false; }} class="deck-menu-item"><HelpCircle class="w-3.5 h-3.5 text-brand-500" /> Quiz</button>
            <button onclick={() => { onCreateSlide('QNA'); showAddMenu = false; }} class="deck-menu-item"><MessageSquare class="w-3.5 h-3.5 text-cyan-500" /> Q&A</button>
            <button onclick={() => { onCreateSlide('RATING'); showAddMenu = false; }} class="deck-menu-item"><Star class="w-3.5 h-3.5 text-amber-500" /> Rating</button>
            <button onclick={() => { onCreateSlide('SCALE'); showAddMenu = false; }} class="deck-menu-item"><Sliders class="w-3.5 h-3.5 text-teal-500" /> Scale</button>
            <button onclick={() => { onCreateSlide('FEEDBACK'); showAddMenu = false; }} class="deck-menu-item"><FeedbackIcon class="w-3.5 h-3.5 text-rose-500" /> Feedback</button>
            <button onclick={() => { onCreateSlide('WORD_CLOUD'); showAddMenu = false; }} class="deck-menu-item"><Cloud class="w-3.5 h-3.5 text-emerald-500" /> Word Cloud</button>
            <button onclick={() => { onCreateSlide('SURVEY'); showAddMenu = false; }} class="deck-menu-item"><ClipboardList class="w-3.5 h-3.5 text-orange-500" /> Survey</button>
          </div>
        {/if}
      </div>

      <!-- Layout Selector -->
      {#if activeType === 'CONTENT'}
        <div class="relative" data-deck-menu>
          <button
            bind:this={layoutMenuTrigger}
            onclick={() => { showLayoutMenu = !showLayoutMenu; showAddMenu = false; }}
            aria-haspopup="true"
            aria-expanded={showLayoutMenu}
            class="deck-btn text-xs gap-1.5 px-2.5 font-medium border border-surface-200 dark:border-surface-700 bg-surface-100 dark:bg-surface-800 hover:bg-surface-200 dark:hover:bg-surface-700/80"
            title="Change Slide Layout"
          >
            <Layout class="w-3.5 h-3.5 text-surface-600 dark:text-surface-300" />
            <span class="capitalize hidden sm:inline">{activeLayout.replace('_', ' ')}</span>
          </button>
          {#if showLayoutMenu}
            <div class="absolute left-0 top-full mt-1.5 z-50 w-44 p-1.5 rounded-xl bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-700 shadow-2xl">
              <button onclick={() => changeLayout('title')} class="deck-menu-item">Title Slide</button>
              <button onclick={() => changeLayout('title_content')} class="deck-menu-item">Content</button>
              <button onclick={() => changeLayout('two_column')} class="deck-menu-item">Two Columns</button>
              <button onclick={() => changeLayout('section')} class="deck-menu-item">Section Header</button>
              <button onclick={() => changeLayout('image_text')} class="deck-menu-item">Image & Text</button>
              <button onclick={() => changeLayout('video')} class="deck-menu-item">Video</button>
              <button onclick={() => changeLayout('blank')} class="deck-menu-item">Blank</button>
            </div>
          {/if}
        </div>
      {/if}
    </div>

    <!-- Center Group: Rich Text Formatting Tools -->
    {#if activeType === 'CONTENT' && activeLayout !== 'video'}
      <div class="flex items-center gap-1 bg-surface-100 dark:bg-surface-950/70 p-1 rounded-lg border border-surface-200 dark:border-surface-800 overflow-x-auto">
        <button onclick={() => toggleBlock('h1')} class="deck-btn text-xs font-bold" title="Heading 1">H1</button>
        <button onclick={() => toggleBlock('h2')} class="deck-btn text-xs font-bold" title="Heading 2">H2</button>
        <button onclick={() => toggleBlock('p')} class="deck-btn text-xs font-semibold" title="Paragraph">¶</button>
        <div class="h-3.5 w-px bg-surface-200 dark:bg-surface-800"></div>
        <button onclick={() => exec('bold')} class="deck-btn" title="Bold (Ctrl+B)"><Bold class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('italic')} class="deck-btn" title="Italic (Ctrl+I)"><Italic class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('underline')} class="deck-btn" title="Underline (Ctrl+U)"><Underline class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('insertUnorderedList')} class="deck-btn" title="Bullet List"><List class="w-3.5 h-3.5" /></button>
      </div>
    {/if}

    <!-- Right Group: Save State & Toggle Properties -->
    <div class="flex items-center gap-2">
      <span class="text-xs text-surface-500 dark:text-surface-400 font-medium" role="status">
        {#if saveState === 'saving'}Saving…
        {:else if saveState === 'saved'}Saved ✓
        {/if}
      </span>
      <button
        onclick={() => showProperties = !showProperties}
        aria-pressed={showProperties}
        class="deck-btn text-xs gap-1.5 border border-surface-200 dark:border-surface-700 {showProperties ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-600 dark:text-brand-300' : ''}"
        title="Toggle Properties Panel"
      >
        <SlidersHorizontal class="w-3.5 h-3.5" />
        <span class="hidden sm:inline">Properties</span>
      </button>
    </div>
  </header>

  <!-- MAIN WORKSPACE -->
  <div class="flex-1 flex min-h-0 overflow-hidden relative">

    <!-- LEFT SLIDE FILMSTRIP -->
    <aside class="w-56 bg-white dark:bg-surface-900 border-r border-surface-200 dark:border-surface-800 flex flex-col flex-shrink-0 select-none transition-colors">
      <div class="p-3 border-b border-surface-200 dark:border-surface-800 flex items-center justify-between text-xs font-semibold text-surface-500 dark:text-surface-400">
        <span>SLIDES ({slides.length})</span>
      </div>

      <div class="flex-1 overflow-y-auto p-2 space-y-2">
        {#each slides as s, idx (s.id)}
          <div
            draggable="true"
            ondragstart={() => handleDragStart(idx)}
            ondragover={(e) => e.preventDefault()}
            ondrop={() => handleDrop(idx)}
            onclick={() => onSelectSlide(s.id)}
            role="button"
            tabindex="0"
            onkeydown={(e) => {
              if (e.target !== e.currentTarget) return;
              if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectSlide(s.id); }
            }}
            aria-current={s.id === activeSlideId ? 'true' : undefined}
            class="group relative flex items-start gap-2 p-2 rounded-xl border transition cursor-pointer {s.id === activeSlideId ? 'border-brand-500 bg-brand-50/70 dark:bg-brand-900/40 ring-2 ring-brand-500/20' : 'border-surface-200 dark:border-surface-800 hover:border-surface-300 dark:hover:border-surface-700 bg-surface-50/50 dark:bg-surface-950/30'}"
          >
            <span class="font-mono text-[10px] text-surface-400 font-bold mt-0.5 w-3 text-right">{idx + 1}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1 text-xs font-semibold truncate text-surface-800 dark:text-surface-200">
                {#if s.type === 'POLL' && s.content_json?.mode === 'quiz'}<HelpCircle class="w-3.5 h-3.5 text-brand-500 shrink-0" />
                {:else if s.type === 'POLL' && s.content_json?.mode === 'multiple_choice'}<ListChecks class="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                {:else if s.type === 'POLL'}<BarChart3 class="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                {:else if s.type === 'FEEDBACK' && s.content_json?.mode === 'scale'}<Sliders class="w-3.5 h-3.5 text-teal-500 shrink-0" />
                {:else if s.type === 'FEEDBACK' && s.content_json?.mode === 'survey'}<ClipboardList class="w-3.5 h-3.5 text-orange-500 shrink-0" />
                {:else if s.type === 'FEEDBACK' && s.content_json?.mode === 'rating_only'}<Star class="w-3.5 h-3.5 text-amber-500 shrink-0" />
                {:else if s.type === 'FEEDBACK'}<FeedbackIcon class="w-3.5 h-3.5 text-rose-500 shrink-0" />
                {:else if s.type === 'QNA'}<MessageSquare class="w-3.5 h-3.5 text-cyan-500 shrink-0" />
                {:else if s.type === 'WORD_CLOUD'}<Cloud class="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                {:else if s.content_json?.layout === 'video'}<Video class="w-3.5 h-3.5 text-brand-500 shrink-0" />
                {:else}<FileText class="w-3.5 h-3.5 text-brand-500 shrink-0" />
                {/if}
                <span class="truncate">{s.content_json?.title || s.content_json?.question || s.content_json?.prompt || s.type}</span>
              </div>
            </div>
            <div class="opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity flex items-center gap-1">
              <button onclick={(e) => { e.stopPropagation(); onDuplicateSlide?.(s.id); }} class="rounded text-surface-400 hover:text-brand-600 dark:hover:text-brand-400 p-0.5" title="Duplicate slide" aria-label="Duplicate slide {idx + 1}"><Copy class="w-3 h-3" /></button>
              <button onclick={(e) => { e.stopPropagation(); onDeleteSlide(s.id); }} class="rounded text-surface-400 hover:text-red-600 dark:hover:text-red-400 p-0.5" title="Delete slide" aria-label="Delete slide {idx + 1}"><Trash2 class="w-3 h-3" /></button>
            </div>
          </div>
        {/each}
      </div>
    </aside>

    <!-- CENTER SLIDE CANVAS -->
    <main class="flex-1 flex items-center justify-center p-4 sm:p-6 overflow-hidden bg-surface-100 dark:bg-surface-950/80">
      
      {#if activeSlide}
        <!-- 16:9 Aspect Ratio Container -->
        <div
          class="w-full max-w-5xl rounded-2xl bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 shadow-2xl p-6 sm:p-8 flex flex-col relative overflow-hidden transition-colors"
          style="aspect-ratio: 16/9; max-height: calc(100vh - 180px);"
        >

          <!-- CONTENT SLIDE: VIDEO LAYOUT -->
          {#if activeType === 'CONTENT' && activeLayout === 'video'}
            <div class="flex-1 flex flex-col space-y-4 h-full overflow-hidden">
              <input
                type="text"
                bind:value={localTitle}
                oninput={() => debouncedSave()}
                placeholder="Video Title"
                aria-label="Video title"
                class="w-full font-bold bg-transparent outline-none border-b border-transparent hover:border-brand-400 focus:border-brand-500 transition px-2 py-1 text-xl"
                style={getFitTitleStyle(localTitle, 'title')}
              />
              <div class="flex items-center gap-2">
                <Video class="w-4 h-4 text-brand-500 shrink-0" />
                <input
                  type="text"
                  bind:value={localVideoUrl}
                  oninput={() => debouncedSave()}
                  placeholder="Paste YouTube, Vimeo, or direct MP4/WebM video URL..."
                  aria-label="Video URL"
                  class="flex-1 px-3 py-1.5 rounded-lg border border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-950 text-xs text-surface-800 dark:text-surface-200 outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
              <div class="flex-1 min-h-0 rounded-xl bg-black/90 flex items-center justify-center overflow-hidden border border-surface-800">
                {#if localVideoUrl}
                  <div class="text-center text-surface-300 text-xs flex flex-col items-center gap-2">
                    <Tv class="w-8 h-8 text-brand-400" />
                    <span>Video configured ({localVideoUrl.slice(0, 45)}...)</span>
                  </div>
                {:else}
                  <div class="text-center text-white/60 text-xs">Enter a video URL above to preview playback</div>
                {/if}
              </div>
            </div>

          <!-- CONTENT SLIDE: TWO COLUMN LAYOUT -->
          {:else if activeType === 'CONTENT' && activeLayout === 'two_column'}
            <div class="flex-1 flex flex-col space-y-4 h-full overflow-hidden">
              <input
                type="text"
                bind:value={localTitle}
                oninput={() => debouncedSave()}
                placeholder="Slide Title"
                aria-label="Slide title"
                class="w-full font-bold bg-transparent outline-none border-b border-transparent hover:border-brand-400 focus:border-brand-500 transition px-2 py-1"
                style={getFitTitleStyle(localTitle, 'title')}
              />
              <div class="flex-1 grid grid-cols-2 gap-4 min-h-0 overflow-hidden">
                <div
                  bind:this={bodyEditorEl}
                  onfocus={() => focusedEditorTag = 'body'}
                  oninput={() => { localBody = bodyEditorEl?.innerHTML || ''; debouncedSave(); }}
                  contenteditable="true"
                  role="textbox"
                  aria-multiline="true"
                  aria-label="Left column"
                  class="p-4 rounded-xl border border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-950/40 outline-none focus:ring-2 focus:ring-brand-500 overflow-y-auto text-base leading-relaxed prose dark:prose-invert max-w-none"
                ></div>
                <div
                  bind:this={body2EditorEl}
                  onfocus={() => focusedEditorTag = 'body2'}
                  oninput={() => { localBody2 = body2EditorEl?.innerHTML || ''; debouncedSave(); }}
                  contenteditable="true"
                  role="textbox"
                  aria-multiline="true"
                  aria-label="Right column"
                  class="p-4 rounded-xl border border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-950/40 outline-none focus:ring-2 focus:ring-brand-500 overflow-y-auto text-base leading-relaxed prose dark:prose-invert max-w-none"
                ></div>
              </div>
            </div>

          <!-- CONTENT SLIDE: IMAGE & TEXT LAYOUT -->
          {:else if activeType === 'CONTENT' && activeLayout === 'image_text'}
            <div class="flex-1 grid grid-cols-12 gap-6 items-center h-full overflow-hidden">
              <div class="col-span-5 h-full rounded-xl bg-surface-50 dark:bg-surface-950/40 border border-surface-200 dark:border-surface-800 flex flex-col items-center justify-center overflow-hidden p-2">
                {#if activeSlide.content_json?.file_url || activeSlide.content_json?.has_file}
                  <ZoomableImageViewer
                    src={getPageImageUrl(sessionId, activeSlide.id, activeSlide.content_json?.file_page || 1)}
                    page={activeSlide.content_json?.file_page || 1}
                    alt="Slide media page"
                    imgClass="max-h-full rounded-lg object-contain"
                  />
                {:else}
                  <ImageIcon class="w-10 h-10 text-surface-400 dark:text-surface-600 mb-2" />
                  <label class="cursor-pointer text-xs text-brand-600 dark:text-brand-400 hover:underline font-semibold rounded focus-within:ring-2 focus-within:ring-brand-500">
                    Upload slide image
                    <input type="file" accept=".pdf,.ppt,.pptx,.png,.jpg,.jpeg,.webp" class="sr-only" onchange={handleFileUploadChange} />
                  </label>
                {/if}
              </div>
              <div class="col-span-7 flex flex-col space-y-3 h-full overflow-hidden">
                <input
                  type="text"
                  bind:value={localTitle}
                  oninput={() => debouncedSave()}
                  placeholder="Slide Title"
                  aria-label="Slide title"
                  class="w-full font-bold bg-transparent outline-none border-b border-transparent hover:border-brand-400 focus:border-brand-500 transition px-1 py-1"
                  style={getFitTitleStyle(localTitle, 'title')}
                />
                <div
                  bind:this={bodyEditorEl}
                  onfocus={() => focusedEditorTag = 'body'}
                  oninput={() => { localBody = bodyEditorEl?.innerHTML || ''; debouncedSave(); }}
                  contenteditable="true"
                  role="textbox"
                  aria-multiline="true"
                  aria-label="Slide body"
                  class="flex-1 p-4 rounded-xl border border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-950/40 outline-none focus:ring-2 focus:ring-brand-500 overflow-y-auto text-base leading-relaxed prose dark:prose-invert max-w-none"
                ></div>
              </div>
            </div>

          <!-- DEFAULT CONTENT SLIDE -->
          {:else if activeType === 'CONTENT'}
            <div class="flex-1 flex flex-col space-y-4 h-full overflow-hidden">
              <input
                type="text"
                bind:value={localTitle}
                oninput={() => debouncedSave()}
                placeholder="Click to add slide title"
                aria-label="Slide title"
                class="w-full font-bold bg-transparent outline-none border-b border-transparent hover:border-brand-400/50 focus:border-brand-500 transition px-2 py-1 placeholder-surface-400 dark:placeholder-surface-600"
                style={getFitTitleStyle(localTitle, 'title')}
              />
              <div
                bind:this={bodyEditorEl}
                onfocus={() => focusedEditorTag = 'body'}
                oninput={() => { localBody = bodyEditorEl?.innerHTML || ''; debouncedSave(); }}
                contenteditable="true"
                role="textbox"
                aria-multiline="true"
                aria-label="Slide body"
                class="flex-1 p-5 rounded-xl border border-surface-200 dark:border-surface-800/80 bg-surface-50 dark:bg-surface-950/30 outline-none focus:ring-2 focus:ring-brand-500 overflow-y-auto text-lg leading-relaxed prose dark:prose-invert max-w-none"
              ></div>
            </div>

          <!-- INTERACTIVE: QUIZ -->
          {:else if isQuiz}
            <div class="flex-1 flex flex-col items-center justify-center text-center max-w-3xl mx-auto space-y-4 w-full h-full overflow-hidden">
              <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest bg-brand-500/10 text-brand-600 dark:text-brand-400 border border-brand-500/20">
                <HelpCircle class="w-4 h-4" /> Quiz Slide
              </div>
              <textarea
                rows="2"
                bind:value={localQuestion}
                oninput={() => debouncedSave()}
                placeholder="Type your quiz question here…"
                aria-label="Quiz question"
                class="w-full font-bold bg-transparent text-center outline-none border-b border-transparent hover:border-brand-400 focus:border-brand-500 transition py-1 resize-none text-lg"
              ></textarea>
              <div class="w-full space-y-2 text-left max-h-[50%] overflow-y-auto pr-1">
                {#each localOptions as opt, i}
                  <div class="flex items-center gap-2 bg-surface-50 dark:bg-surface-950/50 p-2.5 rounded-xl border {localCorrectIndex === i ? 'border-emerald-500 ring-1 ring-emerald-500/30 bg-emerald-50/20 dark:bg-emerald-950/20' : 'border-surface-200 dark:border-surface-800'}">
                    <button
                      type="button"
                      onclick={() => { localCorrectIndex = i; debouncedSave(); }}
                      aria-pressed={localCorrectIndex === i}
                      aria-label={localCorrectIndex === i ? `Option ${i + 1} is the correct answer` : `Mark option ${i + 1} as correct`}
                      class="h-7 px-2 rounded-lg border text-xs font-semibold flex items-center gap-1 transition {localCorrectIndex === i ? 'bg-emerald-600 text-white border-emerald-600' : 'border-surface-300 text-surface-600 hover:border-surface-400 hover:text-surface-900 dark:border-surface-700 dark:text-surface-400 dark:hover:border-surface-600 dark:hover:text-surface-100'}"
                    >
                      <Check class="w-3 h-3" /> {localCorrectIndex === i ? 'Correct' : 'Mark'}
                    </button>
                    <input
                      type="text"
                      value={opt}
                      oninput={(e) => { localOptions[i] = (e.currentTarget as HTMLInputElement).value; debouncedSave(); }}
                      class="flex-1 bg-transparent outline-none font-medium text-sm text-surface-800 dark:text-surface-200"
                      placeholder={`Option ${i + 1}`}
                      aria-label={`Option ${i + 1}`}
                    />
                    <button onclick={() => removePollOption(i)} class="rounded text-surface-400 hover:text-red-600 dark:hover:text-red-400 text-xs font-bold px-1" aria-label={`Remove option ${i + 1}`}>✕</button>
                  </div>
                {/each}
                <button onclick={addPollOption} class="text-xs text-brand-600 dark:text-brand-400 hover:underline font-semibold text-center w-full pt-1">+ Add Option</button>
              </div>
              {#if correctOptionIssue}
                <p class="text-xs font-medium text-amber-600 dark:text-amber-400" role="status">
                  {#if correctOptionIssue === 'blank'}Type the correct option's text — changes are saved once it isn't empty.
                  {:else if correctOptionIssue === 'duplicate'}Another option has the same text as the correct answer — change one of them to save.
                  {:else}No correct answer marked — mark one before revealing the answer.{/if}
                </p>
              {/if}
            </div>

          <!-- INTERACTIVE: SCALE -->
          {:else if isScale}
            <div class="flex-1 flex flex-col items-center justify-center text-center max-w-3xl mx-auto space-y-5 w-full h-full overflow-hidden">
              <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest bg-teal-500/10 text-teal-600 dark:text-teal-400 border border-teal-500/20">
                <Sliders class="w-4 h-4" /> Scale Slide
              </div>
              <textarea
                rows="2"
                bind:value={localPrompt}
                oninput={() => debouncedSave()}
                placeholder="Type your rating/scale prompt here…"
                aria-label="Scale prompt"
                class="w-full font-bold bg-transparent text-center outline-none border-b border-transparent hover:border-brand-400 focus:border-brand-500 transition py-1 resize-none text-lg"
              ></textarea>
              <div class="flex items-center gap-2 justify-center py-2 flex-wrap">
                {#each Array.from({ length: Math.min(10, Math.floor((localMax - localMin) / (localStep || 1)) + 1) }, (_, i) => localMin + i * (localStep || 1)) as n}
                  <div class="h-10 w-10 rounded-xl bg-surface-100 dark:bg-surface-800 border border-surface-200 dark:border-surface-700 flex items-center justify-center font-mono font-bold text-sm text-surface-700 dark:text-surface-300">
                    {n}
                  </div>
                {/each}
              </div>
              {#if localMinLabel || localMaxLabel}
                <div class="flex items-center justify-between w-full max-w-md text-xs text-surface-500 dark:text-surface-400 px-2">
                  <span>{localMinLabel}</span>
                  <span>{localMaxLabel}</span>
                </div>
              {/if}
            </div>

          <!-- INTERACTIVE: SURVEY -->
          {:else if isSurvey}
            <div class="flex-1 flex flex-col items-center justify-center text-center max-w-3xl mx-auto space-y-4 w-full h-full overflow-hidden">
              <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
                <ClipboardList class="w-4 h-4" /> Audience Survey
              </div>
              <textarea
                rows="1"
                bind:value={localPrompt}
                oninput={() => debouncedSave()}
                placeholder="Survey Title / Prompt…"
                aria-label="Survey prompt"
                class="w-full font-bold bg-transparent text-center outline-none border-b border-transparent hover:border-brand-400 focus:border-brand-500 transition py-1 resize-none text-lg"
              ></textarea>
              <div class="w-full max-h-[55%] overflow-y-auto space-y-2 text-left pr-1">
                {#each localQuestions as q, qi}
                  <div class="p-3 rounded-xl border border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-950/50 space-y-2">
                    <div class="flex items-start gap-2">
                      <span class="font-mono text-[10px] text-surface-400 pt-2 w-4 shrink-0">{qi + 1}.</span>
                      <input
                        type="text"
                        value={q.prompt}
                        oninput={(e) => {
                          localQuestions[qi] = { ...q, prompt: (e.currentTarget as HTMLInputElement).value };
                          localQuestions = [...localQuestions];
                          debouncedSave();
                        }}
                        placeholder="Question prompt..."
                        aria-label={`Question ${qi + 1} prompt`}
                        class="flex-1 bg-transparent outline-none font-medium text-sm text-surface-800 dark:text-surface-200 border-b border-transparent hover:border-brand-300 focus:border-brand-500"
                      />
                      <select
                        value={q.response_type}
                        onchange={(e) => {
                          localQuestions[qi] = { ...q, response_type: (e.currentTarget as HTMLSelectElement).value };
                          localQuestions = [...localQuestions];
                          debouncedSave();
                        }}
                        aria-label={`Question ${qi + 1} answer type`}
                        class="text-[10px] font-mono uppercase bg-surface-200 dark:bg-surface-800 px-2 py-1 rounded text-surface-600 dark:text-surface-400 shrink-0"
                      >
                        <option value="single_choice">Single Choice</option>
                        <option value="scale">Scale</option>
                        <option value="text">Text</option>
                      </select>
                      <button onclick={() => removeSurveyQuestion(qi)} class="rounded text-surface-400 hover:text-red-600 dark:hover:text-red-400 text-xs shrink-0" aria-label={`Remove question ${qi + 1}`}>✕</button>
                    </div>

                    {#if q.response_type === 'single_choice'}
                      <div class="pl-6 space-y-1.5">
                        {#each (q.options || []) as opt, oi}
                          <div class="flex items-center gap-2">
                            <input
                              type="text"
                              value={opt}
                              oninput={(e) => {
                                const opts = [...(q.options || [])];
                                opts[oi] = (e.currentTarget as HTMLInputElement).value;
                                localQuestions[qi] = { ...q, options: opts };
                                localQuestions = [...localQuestions];
                                debouncedSave();
                              }}
                              class="flex-1 bg-transparent outline-none text-xs border-b border-surface-200 dark:border-surface-700"
                              placeholder={`Option ${oi + 1}`}
                              aria-label={`Question ${qi + 1}, option ${oi + 1}`}
                            />
                            <button
                              onclick={() => {
                                const opts = (q.options || []).filter((_: string, i: number) => i !== oi);
                                localQuestions[qi] = { ...q, options: opts };
                                localQuestions = [...localQuestions];
                                debouncedSave();
                              }}
                              class="rounded text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 text-xs"
                              aria-label={`Remove option ${oi + 1} from question ${qi + 1}`}
                            >✕</button>
                          </div>
                        {/each}
                        <button
                          onclick={() => {
                            const opts = [...(q.options || []), `Option ${(q.options || []).length + 1}`];
                            localQuestions[qi] = { ...q, options: opts };
                            localQuestions = [...localQuestions];
                            debouncedSave();
                          }}
                          class="text-xs text-brand-600 dark:text-brand-400 hover:underline font-semibold"
                        >+ Add option</button>
                      </div>
                    {:else if q.response_type === 'scale'}
                      <div class="pl-6 grid grid-cols-3 gap-2">
                        <div>
                          <label for="survey-q{qi}-min" class="block text-[10px] text-surface-500 dark:text-surface-400 mb-0.5">Min</label>
                          <input id="survey-q{qi}-min" type="number" value={typeof q.min === 'number' ? q.min : 1}
                            oninput={(e) => { localQuestions[qi] = { ...q, min: parseInt((e.currentTarget as HTMLInputElement).value) || 1 }; localQuestions = [...localQuestions]; debouncedSave(); }}
                            class="w-full text-xs px-2 py-1 rounded border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900" />
                        </div>
                        <div>
                          <label for="survey-q{qi}-max" class="block text-[10px] text-surface-500 dark:text-surface-400 mb-0.5">Max</label>
                          <input id="survey-q{qi}-max" type="number" value={typeof q.max === 'number' ? q.max : 5}
                            oninput={(e) => { localQuestions[qi] = { ...q, max: parseInt((e.currentTarget as HTMLInputElement).value) || 5 }; localQuestions = [...localQuestions]; debouncedSave(); }}
                            class="w-full text-xs px-2 py-1 rounded border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900" />
                        </div>
                        <div>
                          <label for="survey-q{qi}-step" class="block text-[10px] text-surface-500 dark:text-surface-400 mb-0.5">Step</label>
                          <input id="survey-q{qi}-step" type="number" min="1" value={typeof q.step === 'number' ? q.step : 1}
                            oninput={(e) => { localQuestions[qi] = { ...q, step: parseInt((e.currentTarget as HTMLInputElement).value) || 1 }; localQuestions = [...localQuestions]; debouncedSave(); }}
                            class="w-full text-xs px-2 py-1 rounded border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-900" />
                        </div>
                      </div>
                    {:else}
                      <p class="pl-6 text-[10px] text-surface-500 dark:text-surface-400 italic">Participants type a free-form text answer.</p>
                    {/if}
                  </div>
                {/each}
                <button onclick={addSurveyQuestion} class="text-xs text-brand-600 dark:text-brand-400 hover:underline font-semibold text-center w-full pt-1">+ Add Survey Question</button>
              </div>
            </div>

          <!-- INTERACTIVE: POLL / MULTIPLE CHOICE -->
          {:else if activeType === 'POLL'}
            <div class="flex-1 flex flex-col items-center justify-center text-center max-w-3xl mx-auto space-y-5 w-full h-full overflow-hidden">
              <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                {#if isMultipleChoice}<ListChecks class="w-4 h-4 text-indigo-500" /> Multiple Choice{:else}<BarChart3 class="w-4 h-4 text-emerald-500" /> Interactive Poll{/if}
              </div>
              <textarea
                rows="2"
                bind:value={localQuestion}
                oninput={() => debouncedSave()}
                placeholder="Type your question here…"
                aria-label="Question"
                class="w-full font-bold bg-transparent text-center outline-none border-b border-transparent hover:border-brand-400 focus:border-brand-500 transition py-1 resize-none"
                style={getFitTitleStyle(localQuestion, 'question')}
              ></textarea>
              <div class="w-full space-y-2 text-left max-h-[50%] overflow-y-auto pr-1">
                {#each localOptions as opt, i}
                  <div class="flex items-center gap-2 bg-surface-50 dark:bg-surface-950/50 p-3 rounded-xl border border-surface-200 dark:border-surface-800">
                    <input
                      type="text"
                      value={opt}
                      oninput={(e) => { localOptions[i] = (e.currentTarget as HTMLInputElement).value; debouncedSave(); }}
                      class="flex-1 bg-transparent outline-none font-medium text-sm text-surface-800 dark:text-surface-200"
                      placeholder={`Option ${i + 1}`}
                      aria-label={`Option ${i + 1}`}
                    />
                    <button onclick={() => removePollOption(i)} class="rounded text-surface-400 hover:text-red-600 dark:hover:text-red-400 text-xs font-bold px-1" aria-label={`Remove option ${i + 1}`}>✕</button>
                  </div>
                {/each}
                <button onclick={addPollOption} class="text-xs text-brand-600 dark:text-brand-400 hover:underline font-semibold text-center w-full pt-1">+ Add Option</button>
              </div>
            </div>

          <!-- INTERACTIVE: QNA / WORD CLOUD / FEEDBACK / RATING -->
          {:else}
            <div class="flex-1 flex flex-col items-center justify-center text-center max-w-3xl mx-auto space-y-5 w-full h-full overflow-hidden">
              <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest bg-brand-500/10 text-brand-600 dark:text-brand-400 border border-brand-500/20">
                {#if activeType === 'QNA'}<MessageSquare class="w-4 h-4 text-cyan-500" /> Interactive Q&A
                {:else if activeType === 'WORD_CLOUD'}<Cloud class="w-4 h-4 text-amber-500" /> Word Cloud
                {:else if isRatingOnly}<Star class="w-4 h-4 text-amber-500" /> Rating Slide
                {:else}<FeedbackIcon class="w-4 h-4 text-rose-500" /> Audience Feedback
                {/if}
              </div>
              <textarea
                rows="2"
                bind:value={localPrompt}
                oninput={() => debouncedSave()}
                placeholder="Type your audience prompt here…"
                aria-label="Audience prompt"
                class="w-full font-bold bg-transparent text-center outline-none border-b border-transparent hover:border-brand-400 focus:border-brand-500 transition py-1 resize-none"
                style={getFitTitleStyle(localPrompt, 'question')}
              ></textarea>
              <div class="p-6 rounded-2xl bg-surface-50 dark:bg-surface-950/50 border border-surface-200 dark:border-surface-800 text-surface-500 dark:text-surface-400 text-xs w-full">
                Live responses from audience members will display here during the presentation session.
              </div>
            </div>
          {/if}

        </div>
      {/if}

    </main>

    <!-- RIGHT CONTEXTUAL PROPERTIES PANEL -->
    {#if showProperties}
      <aside class="w-72 bg-white dark:bg-surface-900 border-l border-surface-200 dark:border-surface-800 p-4 flex flex-col space-y-5 flex-shrink-0 select-none overflow-y-auto transition-colors">
        <div class="flex items-center justify-between border-b border-surface-200 dark:border-surface-800 pb-2">
          <span class="text-xs font-bold uppercase tracking-wider text-surface-600 dark:text-surface-300">Slide Properties</span>
          <button onclick={() => showProperties = false} class="rounded text-surface-400 hover:text-surface-700 dark:hover:text-white text-xs" aria-label="Close properties panel">✕</button>
        </div>

        {#if activeSlide}
          <!-- Slide Type Info -->
          <div class="space-y-1">
            <span class="text-[10px] font-bold uppercase text-surface-400">Slide Type</span>
            <div class="text-sm font-semibold text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-900/30 p-2.5 rounded-lg border border-brand-200 dark:border-brand-500/20 capitalize">
              {activeType} ({activeLayout})
            </div>
          </div>

          <!-- Slide Layout Switcher -->
          {#if activeType === 'CONTENT'}
            <div class="space-y-2">
              <span class="text-[10px] font-bold uppercase text-surface-400">Slide Layout</span>
              <div class="grid grid-cols-2 gap-2">
                {#each [
                  { id: 'title', label: 'Title' },
                  { id: 'title_content', label: 'Content' },
                  { id: 'two_column', label: '2 Column' },
                  { id: 'section', label: 'Section' },
                  { id: 'image_text', label: 'Image+Text' },
                  { id: 'video', label: 'Video' },
                  { id: 'blank', label: 'Blank' }
                ] as l}
                  <button
                    onclick={() => changeLayout(l.id)}
                    aria-pressed={activeLayout === l.id}
                    class="p-2 text-xs font-medium rounded-lg border text-left transition {activeLayout === l.id ? 'bg-brand-600 text-white border-brand-500' : 'bg-surface-50 dark:bg-surface-950 border-surface-200 dark:border-surface-800 text-surface-700 dark:text-surface-300 hover:border-surface-300 dark:hover:border-surface-700'}"
                  >{l.label}</button>
                {/each}
              </div>
            </div>
          {/if}

          <!-- Media Attachment / File Settings -->
          {#if activeType === 'CONTENT' && activeLayout !== 'video'}
            <div class="space-y-2 border-t border-surface-200 dark:border-surface-800 pt-3">
              <span class="text-[10px] font-bold uppercase text-surface-400">Media & Attachments</span>
              {#if activeSlide.content_json?.file_url || activeSlide.content_json?.has_file}
                <div class="text-xs text-surface-700 dark:text-surface-300 bg-surface-50 dark:bg-surface-950 p-3 rounded-lg border border-surface-200 dark:border-surface-800 space-y-2">
                  <div class="font-mono truncate">Page {activeSlide.content_json?.file_page || 1} of {activeSlide.content_json?.total_pages || 1}</div>
                  <label class="cursor-pointer inline-block rounded text-brand-600 dark:text-brand-400 hover:underline focus-within:ring-2 focus-within:ring-brand-500">
                    Replace slide file
                    <input type="file" accept=".pdf,.ppt,.pptx,.png,.jpg,.jpeg,.webp" class="sr-only" onchange={handleFileUploadChange} />
                  </label>
                </div>
              {:else}
                <label class="flex flex-col items-center justify-center p-4 rounded-xl border border-dashed border-surface-300 dark:border-surface-700 hover:border-brand-500 focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-500/40 cursor-pointer text-xs text-surface-500 dark:text-surface-400 hover:text-surface-900 dark:hover:text-white transition">
                  <Upload class="w-5 h-5 mb-1 text-brand-500" />
                  <span>Upload PDF / PPTX slide</span>
                  <input type="file" accept=".pdf,.ppt,.pptx,.png,.jpg,.jpeg,.webp" class="sr-only" onchange={handleFileUploadChange} />
                </label>
              {/if}
            </div>
          {/if}

        {/if}
      </aside>
    {/if}

  </div>

</div>

<style>
  .deck-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 4px 6px;
    border-radius: 6px;
    transition: background-color 0.12s ease, color 0.12s ease;
  }
  .deck-btn:not(:disabled):hover {
    background: rgba(148, 163, 184, 0.2);
  }
  .deck-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .deck-menu-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    text-align: left;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 12px;
    transition: background 0.12s ease;
  }
  .deck-menu-item:hover {
    background: rgba(148, 163, 184, 0.2);
  }
</style>