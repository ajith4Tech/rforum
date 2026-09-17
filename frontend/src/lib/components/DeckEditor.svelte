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
  let localCorrectAnswer = $state('');
  let localRevealAnswer = $state(false);
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
      localCorrectAnswer = cj.correct_answer ?? '';
      localRevealAnswer = Boolean(cj.reveal_answer);
      localMin = typeof cj.min === 'number' ? cj.min : 1;
      localMax = typeof cj.max === 'number' ? cj.max : 10;
      localStep = typeof cj.step === 'number' ? cj.step : 1;
      localMinLabel = cj.min_label ?? '';
      localMaxLabel = cj.max_label ?? '';
      localQuestions = Array.isArray(cj.questions) ? JSON.parse(JSON.stringify(cj.questions)) : [];

      setTimeout(() => {
        if (bodyEditorEl && bodyEditorEl.innerHTML !== localBody) {
          bodyEditorEl.innerHTML = localBody;
        }
        if (body2EditorEl && body2EditorEl.innerHTML !== localBody2) {
          body2EditorEl.innerHTML = localBody2;
        }
      }, 0);
    }
  });

  async function saveActiveSlideContent(updates: Record<string, unknown> = {}) {
    if (!activeSlide) return;
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
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
        cj.correct_answer = localCorrectAnswer;
        cj.reveal_answer = localRevealAnswer;
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
    await onUpdateSlideContent(activeSlide.id, finalContent);
    savePending = false;
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
    onSaveReady?.(saveActiveSlideContent);
    return () => onSaveReady?.(null);
  });
</script>

<div class="deck-editor flex flex-col h-full w-full bg-slate-100 dark:bg-slate-950 text-slate-900 dark:text-slate-100 rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-800 shadow-2xl transition-colors">

  <!-- TOP COMPACT TOOLBAR -->
  <header class="deck-toolbar flex items-center justify-between px-3.5 py-2 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 gap-2 select-none flex-wrap">
    
    <!-- Left Group: Undo/Redo & Add Slide -->
    <div class="flex items-center gap-1.5">
      <button onclick={onUndo} disabled={!canUndo} class="deck-btn" title="Undo (Ctrl+Z)"><Undo2 class="w-4 h-4" /></button>
      <button onclick={onRedo} disabled={!canRedo} class="deck-btn" title="Redo (Ctrl+Y)"><Redo2 class="w-4 h-4" /></button>
      
      <div class="h-4 w-px bg-slate-200 dark:bg-slate-800 mx-1"></div>

      <!-- Add Slide Menu Trigger -->
      <div class="relative">
        <button
          onclick={() => showAddMenu = !showAddMenu}
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-md transition active:scale-95"
        >
          <Plus class="w-4 h-4" />
          <span>New Slide</span>
        </button>

        {#if showAddMenu}
          <div class="absolute left-0 top-full mt-1.5 z-50 w-56 p-2 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 shadow-2xl space-y-1">
            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-2 py-1">Content Layouts</div>
            <button onclick={() => { onCreateSlide('CONTENT', 'title_content'); showAddMenu = false; }} class="deck-menu-item"><FileText class="w-3.5 h-3.5 text-purple-500" /> Content</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'image'); showAddMenu = false; }} class="deck-menu-item"><ImageIcon class="w-3.5 h-3.5 text-purple-500" /> Image</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'image_text'); showAddMenu = false; }} class="deck-menu-item"><Columns class="w-3.5 h-3.5 text-purple-500" /> Image + Text</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'two_column'); showAddMenu = false; }} class="deck-menu-item"><Columns class="w-3.5 h-3.5 text-purple-500" /> Two Column</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'video'); showAddMenu = false; }} class="deck-menu-item"><Video class="w-3.5 h-3.5 text-purple-500" /> Video</button>
            
            <div class="h-px bg-slate-200 dark:bg-slate-800 my-1"></div>
            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-2 py-1">Interactions</div>
            <button onclick={() => { onCreateSlide('POLL'); showAddMenu = false; }} class="deck-menu-item"><BarChart3 class="w-3.5 h-3.5 text-emerald-500" /> Poll</button>
            <button onclick={() => { onCreateSlide('MULTIPLE_CHOICE'); showAddMenu = false; }} class="deck-menu-item"><ListChecks class="w-3.5 h-3.5 text-indigo-500" /> Multiple Choice</button>
            <button onclick={() => { onCreateSlide('QUIZ'); showAddMenu = false; }} class="deck-menu-item"><HelpCircle class="w-3.5 h-3.5 text-violet-500" /> Quiz</button>
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
        <div class="relative">
          <button
            onclick={() => showLayoutMenu = !showLayoutMenu}
            class="deck-btn text-xs gap-1.5 px-2.5 font-medium border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700/80"
            title="Change Slide Layout"
          >
            <Layout class="w-3.5 h-3.5 text-slate-600 dark:text-slate-300" />
            <span class="capitalize hidden sm:inline">{activeLayout.replace('_', ' ')}</span>
          </button>
          {#if showLayoutMenu}
            <div class="absolute left-0 top-full mt-1.5 z-50 w-44 p-1.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 shadow-2xl">
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
      <div class="flex items-center gap-1 bg-slate-100 dark:bg-slate-950/70 p-1 rounded-lg border border-slate-200 dark:border-slate-800 overflow-x-auto">
        <button onclick={() => toggleBlock('h1')} class="deck-btn text-xs font-bold" title="Heading 1">H1</button>
        <button onclick={() => toggleBlock('h2')} class="deck-btn text-xs font-bold" title="Heading 2">H2</button>
        <button onclick={() => toggleBlock('p')} class="deck-btn text-xs font-semibold" title="Paragraph">¶</button>
        <div class="h-3.5 w-px bg-slate-200 dark:bg-slate-800"></div>
        <button onclick={() => exec('bold')} class="deck-btn" title="Bold (Ctrl+B)"><Bold class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('italic')} class="deck-btn" title="Italic (Ctrl+I)"><Italic class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('underline')} class="deck-btn" title="Underline (Ctrl+U)"><Underline class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('insertUnorderedList')} class="deck-btn" title="Bullet List"><List class="w-3.5 h-3.5" /></button>
      </div>
    {/if}

    <!-- Right Group: Save State & Toggle Properties -->
    <div class="flex items-center gap-2">
      <span class="text-xs text-slate-400 font-medium">
        {#if saveState === 'saving'}Saving…
        {:else if saveState === 'saved'}Saved ✓
        {/if}
      </span>
      <button
        onclick={() => showProperties = !showProperties}
        class="deck-btn text-xs gap-1.5 border border-slate-200 dark:border-slate-700 {showProperties ? 'bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-300' : ''}"
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
    <aside class="w-56 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex flex-col flex-shrink-0 select-none transition-colors">
      <div class="p-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs font-semibold text-slate-500">
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
            onkeydown={(e) => { if (e.key === 'Enter') onSelectSlide(s.id); }}
            class="group relative flex items-start gap-2 p-2 rounded-xl border transition-all cursor-pointer {s.id === activeSlideId ? 'border-purple-500 bg-purple-50/70 dark:bg-purple-950/40 ring-2 ring-purple-500/20' : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 bg-slate-50/50 dark:bg-slate-950/30'}"
          >
            <span class="font-mono text-[10px] text-slate-400 font-bold mt-0.5 w-3 text-right">{idx + 1}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1 text-xs font-semibold truncate text-slate-800 dark:text-slate-200">
                {#if s.type === 'POLL' && s.content_json?.mode === 'quiz'}<HelpCircle class="w-3.5 h-3.5 text-violet-500 shrink-0" />
                {:else if s.type === 'POLL' && s.content_json?.mode === 'multiple_choice'}<ListChecks class="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                {:else if s.type === 'POLL'}<BarChart3 class="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                {:else if s.type === 'FEEDBACK' && s.content_json?.mode === 'scale'}<Sliders class="w-3.5 h-3.5 text-teal-500 shrink-0" />
                {:else if s.type === 'FEEDBACK' && s.content_json?.mode === 'survey'}<ClipboardList class="w-3.5 h-3.5 text-orange-500 shrink-0" />
                {:else if s.type === 'FEEDBACK' && s.content_json?.mode === 'rating_only'}<Star class="w-3.5 h-3.5 text-amber-500 shrink-0" />
                {:else if s.type === 'FEEDBACK'}<FeedbackIcon class="w-3.5 h-3.5 text-rose-500 shrink-0" />
                {:else if s.type === 'QNA'}<MessageSquare class="w-3.5 h-3.5 text-cyan-500 shrink-0" />
                {:else if s.type === 'WORD_CLOUD'}<Cloud class="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                {:else if s.content_json?.layout === 'video'}<Video class="w-3.5 h-3.5 text-purple-500 shrink-0" />
                {:else}<FileText class="w-3.5 h-3.5 text-purple-500 shrink-0" />
                {/if}
                <span class="truncate">{s.content_json?.title || s.content_json?.question || s.content_json?.prompt || s.type}</span>
              </div>
            </div>
            <div class="opacity-0 group-hover:opacity-100 flex items-center gap-1">
              <button onclick={(e) => { e.stopPropagation(); onDuplicateSlide?.(s.id); }} class="text-slate-400 hover:text-purple-500 p-0.5"><Copy class="w-3 h-3" /></button>
              <button onclick={(e) => { e.stopPropagation(); onDeleteSlide(s.id); }} class="text-slate-400 hover:text-red-500 p-0.5"><Trash2 class="w-3 h-3" /></button>
            </div>
          </div>
        {/each}
      </div>
    </aside>

    <!-- CENTER SLIDE CANVAS -->
    <main class="flex-1 flex items-center justify-center p-4 sm:p-6 overflow-hidden bg-slate-100 dark:bg-slate-950/80">
      
      {#if activeSlide}
        <!-- 16:9 Aspect Ratio Container -->
        <div
          class="w-full max-w-5xl rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl p-6 sm:p-8 flex flex-col relative overflow-hidden transition-all"
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
                class="w-full font-bold bg-transparent outline-none border-b border-transparent hover:border-purple-400 focus:border-purple-500 transition px-2 py-1 text-xl"
                style={getFitTitleStyle(localTitle, 'title')}
              />
              <div class="flex items-center gap-2">
                <Video class="w-4 h-4 text-purple-500 shrink-0" />
                <input
                  type="text"
                  bind:value={localVideoUrl}
                  oninput={() => debouncedSave()}
                  placeholder="Paste YouTube, Vimeo, or direct MP4/WebM video URL..."
                  class="flex-1 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-xs text-slate-800 dark:text-slate-200 outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div class="flex-1 min-h-0 rounded-xl bg-black/90 flex items-center justify-center overflow-hidden border border-slate-800">
                {#if localVideoUrl}
                  <div class="text-center text-slate-400 text-xs flex flex-col items-center gap-2">
                    <Tv class="w-8 h-8 text-purple-400" />
                    <span>Video configured ({localVideoUrl.slice(0, 45)}...)</span>
                  </div>
                {:else}
                  <div class="text-center text-slate-500 text-xs">Enter a video URL above to preview playback</div>
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
                class="w-full font-bold bg-transparent outline-none border-b border-transparent hover:border-purple-400 focus:border-purple-500 transition px-2 py-1"
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
                  class="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/40 outline-none focus:ring-2 focus:ring-purple-500 overflow-y-auto text-base leading-relaxed prose dark:prose-invert max-w-none"
                ></div>
                <div
                  bind:this={body2EditorEl}
                  onfocus={() => focusedEditorTag = 'body2'}
                  oninput={() => { localBody2 = body2EditorEl?.innerHTML || ''; debouncedSave(); }}
                  contenteditable="true"
                  role="textbox"
                  aria-multiline="true"
                  class="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/40 outline-none focus:ring-2 focus:ring-purple-500 overflow-y-auto text-base leading-relaxed prose dark:prose-invert max-w-none"
                ></div>
              </div>
            </div>

          <!-- CONTENT SLIDE: IMAGE & TEXT LAYOUT -->
          {:else if activeType === 'CONTENT' && activeLayout === 'image_text'}
            <div class="flex-1 grid grid-cols-12 gap-6 items-center h-full overflow-hidden">
              <div class="col-span-5 h-full rounded-xl bg-slate-50 dark:bg-slate-950/40 border border-slate-200 dark:border-slate-800 flex flex-col items-center justify-center overflow-hidden p-2">
                {#if activeSlide.content_json?.file_url || activeSlide.content_json?.has_file}
                  <ZoomableImageViewer
                    src={getPageImageUrl(sessionId, activeSlide.id, activeSlide.content_json?.file_page || 1)}
                    page={activeSlide.content_json?.file_page || 1}
                    alt="Slide media page"
                    imgClass="max-h-full rounded-lg object-contain"
                  />
                {:else}
                  <ImageIcon class="w-10 h-10 text-slate-400 dark:text-slate-600 mb-2" />
                  <label class="cursor-pointer text-xs text-purple-600 dark:text-purple-400 hover:underline font-semibold">
                    Upload slide image
                    <input type="file" accept=".pdf,.ppt,.pptx,.png,.jpg,.jpeg,.webp" class="hidden" onchange={handleFileUploadChange} />
                  </label>
                {/if}
              </div>
              <div class="col-span-7 flex flex-col space-y-3 h-full overflow-hidden">
                <input
                  type="text"
                  bind:value={localTitle}
                  oninput={() => debouncedSave()}
                  placeholder="Slide Title"
                  class="w-full font-bold bg-transparent outline-none border-b border-transparent hover:border-purple-400 focus:border-purple-500 transition px-1 py-1"
                  style={getFitTitleStyle(localTitle, 'title')}
                />
                <div
                  bind:this={bodyEditorEl}
                  onfocus={() => focusedEditorTag = 'body'}
                  oninput={() => { localBody = bodyEditorEl?.innerHTML || ''; debouncedSave(); }}
                  contenteditable="true"
                  role="textbox"
                  aria-multiline="true"
                  class="flex-1 p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/40 outline-none focus:ring-2 focus:ring-purple-500 overflow-y-auto text-base leading-relaxed prose dark:prose-invert max-w-none"
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
                class="w-full font-bold bg-transparent outline-none border-b border-transparent hover:border-purple-400/50 focus:border-purple-500 transition px-2 py-1 placeholder-slate-400 dark:placeholder-slate-600"
                style={getFitTitleStyle(localTitle, 'title')}
              />
              <div
                bind:this={bodyEditorEl}
                onfocus={() => focusedEditorTag = 'body'}
                oninput={() => { localBody = bodyEditorEl?.innerHTML || ''; debouncedSave(); }}
                contenteditable="true"
                role="textbox"
                aria-multiline="true"
                class="flex-1 p-5 rounded-xl border border-slate-200 dark:border-slate-800/80 bg-slate-50 dark:bg-slate-950/30 outline-none focus:ring-2 focus:ring-purple-500 overflow-y-auto text-lg leading-relaxed prose dark:prose-invert max-w-none"
              ></div>
            </div>

          <!-- INTERACTIVE: QUIZ -->
          {:else if isQuiz}
            <div class="flex-1 flex flex-col items-center justify-center text-center max-w-3xl mx-auto space-y-4 w-full h-full overflow-hidden">
              <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest bg-violet-500/10 text-violet-600 dark:text-violet-400 border border-violet-500/20">
                <HelpCircle class="w-4 h-4" /> Quiz Slide
              </div>
              <textarea
                rows="2"
                bind:value={localQuestion}
                oninput={() => debouncedSave()}
                placeholder="Type your quiz question here…"
                class="w-full font-bold bg-transparent text-center outline-none border-b border-transparent hover:border-purple-400 focus:border-purple-500 transition py-1 resize-none text-lg"
              ></textarea>
              <div class="w-full space-y-2 text-left max-h-[50%] overflow-y-auto pr-1">
                {#each localOptions as opt, i}
                  <div class="flex items-center gap-2 bg-slate-50 dark:bg-slate-950/50 p-2.5 rounded-xl border {localCorrectAnswer === opt ? 'border-emerald-500 ring-1 ring-emerald-500/30 bg-emerald-50/20 dark:bg-emerald-950/20' : 'border-slate-200 dark:border-slate-800'}">
                    <button
                      type="button"
                      onclick={() => { localCorrectAnswer = opt; debouncedSave(); }}
                      class="h-7 px-2 rounded-lg border text-xs font-semibold flex items-center gap-1 transition {localCorrectAnswer === opt ? 'bg-emerald-500 text-white border-emerald-500' : 'border-slate-300 text-slate-500 hover:border-slate-400'}"
                    >
                      <Check class="w-3 h-3" /> {localCorrectAnswer === opt ? 'Correct' : 'Mark'}
                    </button>
                    <input
                      type="text"
                      value={opt}
                      oninput={(e) => { localOptions[i] = (e.currentTarget as HTMLInputElement).value; debouncedSave(); }}
                      class="flex-1 bg-transparent outline-none font-medium text-sm text-slate-800 dark:text-slate-200"
                      placeholder={`Option ${i + 1}`}
                    />
                    <button onclick={() => removePollOption(i)} class="text-slate-400 hover:text-red-500 text-xs font-bold px-1">✕</button>
                  </div>
                {/each}
                <button onclick={addPollOption} class="text-xs text-purple-600 dark:text-purple-400 hover:underline font-semibold text-center w-full pt-1">+ Add Option</button>
              </div>
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
                class="w-full font-bold bg-transparent text-center outline-none border-b border-transparent hover:border-purple-400 focus:border-purple-500 transition py-1 resize-none text-lg"
              ></textarea>
              <div class="flex items-center gap-2 justify-center py-2 flex-wrap">
                {#each Array.from({ length: Math.min(10, Math.floor((localMax - localMin) / (localStep || 1)) + 1) }, (_, i) => localMin + i * (localStep || 1)) as n}
                  <div class="h-10 w-10 rounded-xl bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center font-mono font-bold text-sm text-slate-700 dark:text-slate-300">
                    {n}
                  </div>
                {/each}
              </div>
              {#if localMinLabel || localMaxLabel}
                <div class="flex items-center justify-between w-full max-w-md text-xs text-slate-400 px-2">
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
                class="w-full font-bold bg-transparent text-center outline-none border-b border-transparent hover:border-purple-400 focus:border-purple-500 transition py-1 resize-none text-lg"
              ></textarea>
              <div class="w-full max-h-[55%] overflow-y-auto space-y-2 text-left pr-1">
                {#each localQuestions as q, qi}
                  <div class="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 space-y-2">
                    <div class="flex items-start gap-2">
                      <span class="font-mono text-[10px] text-slate-400 pt-2 w-4 shrink-0">{qi + 1}.</span>
                      <input
                        type="text"
                        value={q.prompt}
                        oninput={(e) => {
                          localQuestions[qi] = { ...q, prompt: (e.currentTarget as HTMLInputElement).value };
                          localQuestions = [...localQuestions];
                          debouncedSave();
                        }}
                        placeholder="Question prompt..."
                        class="flex-1 bg-transparent outline-none font-medium text-sm text-slate-800 dark:text-slate-200 border-b border-transparent hover:border-purple-300 focus:border-purple-500"
                      />
                      <select
                        value={q.response_type}
                        onchange={(e) => {
                          localQuestions[qi] = { ...q, response_type: (e.currentTarget as HTMLSelectElement).value };
                          localQuestions = [...localQuestions];
                          debouncedSave();
                        }}
                        class="text-[10px] font-mono uppercase bg-slate-200 dark:bg-slate-800 px-2 py-1 rounded text-slate-600 dark:text-slate-400 shrink-0"
                      >
                        <option value="single_choice">Single Choice</option>
                        <option value="scale">Scale</option>
                        <option value="text">Text</option>
                      </select>
                      <button onclick={() => removeSurveyQuestion(qi)} class="text-slate-400 hover:text-red-500 text-xs shrink-0">✕</button>
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
                              class="flex-1 bg-transparent outline-none text-xs border-b border-slate-200 dark:border-slate-700"
                              placeholder={`Option ${oi + 1}`}
                            />
                            <button
                              onclick={() => {
                                const opts = (q.options || []).filter((_: string, i: number) => i !== oi);
                                localQuestions[qi] = { ...q, options: opts };
                                localQuestions = [...localQuestions];
                                debouncedSave();
                              }}
                              class="text-red-400 hover:text-red-600 text-xs"
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
                          class="text-xs text-purple-600 dark:text-purple-400 hover:underline font-semibold"
                        >+ Add option</button>
                      </div>
                    {:else if q.response_type === 'scale'}
                      <div class="pl-6 grid grid-cols-3 gap-2">
                        <div>
                          <label class="block text-[10px] text-slate-400 mb-0.5">Min</label>
                          <input type="number" value={typeof q.min === 'number' ? q.min : 1}
                            oninput={(e) => { localQuestions[qi] = { ...q, min: parseInt((e.currentTarget as HTMLInputElement).value) || 1 }; localQuestions = [...localQuestions]; debouncedSave(); }}
                            class="w-full text-xs px-2 py-1 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900" />
                        </div>
                        <div>
                          <label class="block text-[10px] text-slate-400 mb-0.5">Max</label>
                          <input type="number" value={typeof q.max === 'number' ? q.max : 5}
                            oninput={(e) => { localQuestions[qi] = { ...q, max: parseInt((e.currentTarget as HTMLInputElement).value) || 5 }; localQuestions = [...localQuestions]; debouncedSave(); }}
                            class="w-full text-xs px-2 py-1 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900" />
                        </div>
                        <div>
                          <label class="block text-[10px] text-slate-400 mb-0.5">Step</label>
                          <input type="number" min="1" value={typeof q.step === 'number' ? q.step : 1}
                            oninput={(e) => { localQuestions[qi] = { ...q, step: parseInt((e.currentTarget as HTMLInputElement).value) || 1 }; localQuestions = [...localQuestions]; debouncedSave(); }}
                            class="w-full text-xs px-2 py-1 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900" />
                        </div>
                      </div>
                    {:else}
                      <p class="pl-6 text-[10px] text-slate-400 italic">Participants type a free-form text answer.</p>
                    {/if}
                  </div>
                {/each}
                <button onclick={addSurveyQuestion} class="text-xs text-purple-600 dark:text-purple-400 hover:underline font-semibold text-center w-full pt-1">+ Add Survey Question</button>
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
                class="w-full font-bold bg-transparent text-center outline-none border-b border-transparent hover:border-purple-400 focus:border-purple-500 transition py-1 resize-none"
                style={getFitTitleStyle(localQuestion, 'question')}
              ></textarea>
              <div class="w-full space-y-2 text-left max-h-[50%] overflow-y-auto pr-1">
                {#each localOptions as opt, i}
                  <div class="flex items-center gap-2 bg-slate-50 dark:bg-slate-950/50 p-3 rounded-xl border border-slate-200 dark:border-slate-800">
                    <input
                      type="text"
                      value={opt}
                      oninput={(e) => { localOptions[i] = (e.currentTarget as HTMLInputElement).value; debouncedSave(); }}
                      class="flex-1 bg-transparent outline-none font-medium text-sm text-slate-800 dark:text-slate-200"
                      placeholder={`Option ${i + 1}`}
                    />
                    <button onclick={() => removePollOption(i)} class="text-slate-400 hover:text-red-500 text-xs font-bold px-1">✕</button>
                  </div>
                {/each}
                <button onclick={addPollOption} class="text-xs text-purple-600 dark:text-purple-400 hover:underline font-semibold text-center w-full pt-1">+ Add Option</button>
              </div>
            </div>

          <!-- INTERACTIVE: QNA / WORD CLOUD / FEEDBACK / RATING -->
          {:else}
            <div class="flex-1 flex flex-col items-center justify-center text-center max-w-3xl mx-auto space-y-5 w-full h-full overflow-hidden">
              <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
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
                class="w-full font-bold bg-transparent text-center outline-none border-b border-transparent hover:border-purple-400 focus:border-purple-500 transition py-1 resize-none"
                style={getFitTitleStyle(localPrompt, 'question')}
              ></textarea>
              <div class="p-6 rounded-2xl bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 text-xs w-full">
                Live responses from audience members will display here during the presentation session.
              </div>
            </div>
          {/if}

        </div>
      {/if}

    </main>

    <!-- RIGHT CONTEXTUAL PROPERTIES PANEL -->
    {#if showProperties}
      <aside class="w-72 bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 p-4 flex flex-col space-y-5 flex-shrink-0 select-none overflow-y-auto transition-colors">
        <div class="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2">
          <span class="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Slide Properties</span>
          <button onclick={() => showProperties = false} class="text-slate-400 hover:text-slate-700 dark:hover:text-white text-xs">✕</button>
        </div>

        {#if activeSlide}
          <!-- Slide Type Info -->
          <div class="space-y-1">
            <span class="text-[10px] font-bold uppercase text-slate-400">Slide Type</span>
            <div class="text-sm font-semibold text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/30 p-2.5 rounded-lg border border-purple-200 dark:border-purple-500/20 capitalize">
              {activeType} ({activeLayout})
            </div>
          </div>

          <!-- Slide Layout Switcher -->
          {#if activeType === 'CONTENT'}
            <div class="space-y-2">
              <span class="text-[10px] font-bold uppercase text-slate-400">Slide Layout</span>
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
                    class="p-2 text-xs font-medium rounded-lg border text-left transition {activeLayout === l.id ? 'bg-purple-600 text-white border-purple-500' : 'bg-slate-50 dark:bg-slate-950 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-700'}"
                  >{l.label}</button>
                {/each}
              </div>
            </div>
          {/if}

          <!-- Media Attachment / File Settings -->
          {#if activeType === 'CONTENT' && activeLayout !== 'video'}
            <div class="space-y-2 border-t border-slate-200 dark:border-slate-800 pt-3">
              <span class="text-[10px] font-bold uppercase text-slate-400">Media & Attachments</span>
              {#if activeSlide.content_json?.file_url || activeSlide.content_json?.has_file}
                <div class="text-xs text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-950 p-3 rounded-lg border border-slate-200 dark:border-slate-800 space-y-2">
                  <div class="font-mono truncate">Page {activeSlide.content_json?.file_page || 1} of {activeSlide.content_json?.total_pages || 1}</div>
                  <label class="cursor-pointer inline-block text-purple-600 dark:text-purple-400 hover:underline">
                    Replace slide file
                    <input type="file" accept=".pdf,.ppt,.pptx,.png,.jpg,.jpeg,.webp" class="hidden" onchange={handleFileUploadChange} />
                  </label>
                </div>
              {:else}
                <label class="flex flex-col items-center justify-center p-4 rounded-xl border border-dashed border-slate-300 dark:border-slate-700 hover:border-purple-500 cursor-pointer text-xs text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition">
                  <Upload class="w-5 h-5 mb-1 text-purple-500" />
                  <span>Upload PDF / PPTX slide</span>
                  <input type="file" accept=".pdf,.ppt,.pptx,.png,.jpg,.jpeg,.webp" class="hidden" onchange={handleFileUploadChange} />
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
    transition: all 0.12s ease;
  }
  .deck-btn:hover {
    background: rgba(148, 163, 184, 0.2);
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