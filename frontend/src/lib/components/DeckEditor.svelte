<script lang="ts">
  import {
    Plus, Trash2, Copy, GripVertical, ChevronUp, ChevronDown, Layout, Type,
    Bold, Italic, Underline, Strikethrough, AlignLeft, AlignCenter, AlignRight,
    List, ListOrdered, Link, Code, Eraser, Undo2, Redo2, Highlighter,
    SlidersHorizontal, Eye, Upload, FileText, BarChart3, MessageSquare, Cloud, AlignLeft as FeedbackIcon,
    Sparkles, Image as ImageIcon, Columns, Heading1, Heading2, Check
  } from 'lucide-svelte';
  import ZoomableImageViewer from '$lib/components/ZoomableImageViewer.svelte';
  import { getPageImageUrl } from '$lib/api';
  import { theme } from '$lib/theme';

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

  // Dynamic responsive font size helper for slide titles and long questions
  function getFitTitleStyle(text: string, type: 'title' | 'question' = 'title'): string {
    const len = (text || '').trim().length;
    if (!len) return '';
    if (type === 'question') {
      if (len < 30) return 'font-size: clamp(1.35rem, 3vw, 2.2rem); line-height: 1.15; word-break: break-word; overflow-wrap: anywhere;';
      if (len < 70) return 'font-size: clamp(1.1rem, 2.4vw, 1.8rem); line-height: 1.18; word-break: break-word; overflow-wrap: anywhere;';
      if (len < 120) return 'font-size: clamp(0.95rem, 1.9vw, 1.4rem); line-height: 1.24; word-break: break-word; overflow-wrap: anywhere;';
      return 'font-size: clamp(0.82rem, 1.55vw, 1.1rem); line-height: 1.28; word-break: break-word; overflow-wrap: anywhere;';
    } else {
      if (len < 24) return 'font-size: clamp(1.8rem, 4vw, 3rem); line-height: 1.1; word-break: break-word; overflow-wrap: anywhere;';
      if (len < 56) return 'font-size: clamp(1.35rem, 2.9vw, 2.2rem); line-height: 1.15; word-break: break-word; overflow-wrap: anywhere;';
      if (len < 110) return 'font-size: clamp(1.05rem, 2vw, 1.55rem); line-height: 1.22; word-break: break-word; overflow-wrap: anywhere;';
      return 'font-size: clamp(0.85rem, 1.55vw, 1.1rem); line-height: 1.28; word-break: break-word; overflow-wrap: anywhere;';
    }
  }

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
    } else if (activeType === 'POLL') {
      cj.question = localQuestion;
      cj.options = localOptions.filter(o => o.trim() !== '');
    } else if (activeType === 'QNA' || activeType === 'WORD_CLOUD' || activeType === 'FEEDBACK') {
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

  const isDirty = $derived.by(() => {
    if (!activeSlide) return false;
    if (savePending) return true;
    const cj = activeSlide.content_json || {};
    if (activeType === 'CONTENT') {
      return localTitle !== (cj.title || '') || localSubtitle !== (cj.subtitle || '') || localBody !== (cj.body || '') || localBody2 !== (cj.body2 || '');
    }
    if (activeType === 'POLL') {
      const cleaned = localOptions.map((o) => o.trim()).filter(Boolean);
      return localQuestion.trim() !== (cj.question || '') || JSON.stringify(cleaned) !== JSON.stringify(cj.options || []);
    }
    if (activeType === 'QNA' || activeType === 'WORD_CLOUD' || activeType === 'FEEDBACK') {
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
            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-2 py-1">Presentation Layouts</div>
            <button onclick={() => { onCreateSlide('CONTENT', 'title'); showAddMenu = false; }} class="deck-menu-item"><Heading1 class="w-3.5 h-3.5 text-purple-500" /> Title Slide</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'title_content'); showAddMenu = false; }} class="deck-menu-item"><FileText class="w-3.5 h-3.5 text-purple-500" /> Title & Content</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'two_column'); showAddMenu = false; }} class="deck-menu-item"><Columns class="w-3.5 h-3.5 text-purple-500" /> Two Columns</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'section'); showAddMenu = false; }} class="deck-menu-item"><Sparkles class="w-3.5 h-3.5 text-purple-500" /> Section Header</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'image_text'); showAddMenu = false; }} class="deck-menu-item"><ImageIcon class="w-3.5 h-3.5 text-purple-500" /> Image & Text</button>
            <button onclick={() => { onCreateSlide('CONTENT', 'blank'); showAddMenu = false; }} class="deck-menu-item"><Layout class="w-3.5 h-3.5 text-purple-500" /> Blank Canvas</button>
            
            <div class="h-px bg-slate-200 dark:bg-slate-800 my-1"></div>
            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-2 py-1">Interactive Elements</div>
            <button onclick={() => { onCreateSlide('POLL'); showAddMenu = false; }} class="deck-menu-item"><BarChart3 class="w-3.5 h-3.5 text-emerald-500" /> Poll Slide</button>
            <button onclick={() => { onCreateSlide('QNA'); showAddMenu = false; }} class="deck-menu-item"><MessageSquare class="w-3.5 h-3.5 text-cyan-500" /> Q&A Slide</button>
            <button onclick={() => { onCreateSlide('WORD_CLOUD'); showAddMenu = false; }} class="deck-menu-item"><Cloud class="w-3.5 h-3.5 text-amber-500" /> Word Cloud</button>
            <button onclick={() => { onCreateSlide('FEEDBACK'); showAddMenu = false; }} class="deck-menu-item"><FeedbackIcon class="w-3.5 h-3.5 text-rose-500" /> Feedback Slide</button>
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
              <button onclick={() => changeLayout('title_content')} class="deck-menu-item">Title & Content</button>
              <button onclick={() => changeLayout('two_column')} class="deck-menu-item">Two Columns</button>
              <button onclick={() => changeLayout('section')} class="deck-menu-item">Section Header</button>
              <button onclick={() => changeLayout('image_text')} class="deck-menu-item">Image & Text</button>
              <button onclick={() => changeLayout('blank')} class="deck-menu-item">Blank</button>
            </div>
          {/if}
        </div>
      {/if}
    </div>

    <!-- Center Group: Rich Text Formatting Tools -->
    {#if activeType === 'CONTENT'}
      <div class="flex items-center gap-1 bg-slate-100 dark:bg-slate-950/70 p-1 rounded-lg border border-slate-200 dark:border-slate-800 overflow-x-auto">
        
        <!-- Text Styles -->
        <button onclick={() => toggleBlock('h1')} class="deck-btn text-xs font-bold" title="Heading 1">H1</button>
        <button onclick={() => toggleBlock('h2')} class="deck-btn text-xs font-bold" title="Heading 2">H2</button>
        <button onclick={() => toggleBlock('p')} class="deck-btn text-xs font-semibold" title="Paragraph">¶</button>

        <div class="h-3.5 w-px bg-slate-200 dark:bg-slate-800"></div>

        <!-- Font Family & Size -->
        <div class="relative">
          <button onclick={() => showFontFamily = !showFontFamily} class="deck-btn text-xs gap-1" title="Font Family">
            <Type class="w-3.5 h-3.5" />
          </button>
          {#if showFontFamily}
            <div class="absolute top-full left-0 mt-1 z-50 w-40 p-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-xl">
              {#each FONT_FAMILIES as f}
                <button onclick={() => applyFontFamily(f.value)} class="deck-menu-item text-xs" style="font-family:{f.value}">{f.label}</button>
              {/each}
            </div>
          {/if}
        </div>

        <div class="relative">
          <button onclick={() => showFontSize = !showFontSize} class="deck-btn text-xs font-bold" title="Font Size">Aa</button>
          {#if showFontSize}
            <div class="absolute top-full left-0 mt-1 z-50 w-24 p-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-xl">
              {#each FONT_SIZES as s}
                <button onclick={() => applyFontSize(s)} class="deck-menu-item text-xs font-mono">{s}</button>
              {/each}
            </div>
          {/if}
        </div>

        <div class="h-3.5 w-px bg-slate-200 dark:bg-slate-800"></div>

        <!-- Inline formatting -->
        <button onclick={() => exec('bold')} class="deck-btn" title="Bold (Ctrl+B)"><Bold class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('italic')} class="deck-btn" title="Italic (Ctrl+I)"><Italic class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('underline')} class="deck-btn" title="Underline (Ctrl+U)"><Underline class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('strikeThrough')} class="deck-btn" title="Strikethrough"><Strikethrough class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('insertHTML', '<code style="font-family:monospace;background:rgba(139,92,246,0.18);padding:0.1em 0.3em;border-radius:4px">' + (window.getSelection()?.toString() || '​') + '</code>')} class="deck-btn" title="Inline Code"><Code class="w-3.5 h-3.5" /></button>

        <div class="h-3.5 w-px bg-slate-200 dark:bg-slate-800"></div>

        <!-- Colors -->
        <div class="relative">
          <button onclick={() => showColorPicker = !showColorPicker} class="deck-btn text-xs font-extrabold underline decoration-purple-500" title="Text Color">A</button>
          {#if showColorPicker}
            <div class="absolute top-full left-0 mt-1 z-50 p-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-xl grid grid-cols-5 gap-1.5 w-40">
              {#each TEXT_COLORS as c}
                <button onclick={() => applyColor(c)} class="w-5 h-5 rounded border border-slate-300 dark:border-slate-600 hover:scale-110 transition" style="background:{c}"></button>
              {/each}
            </div>
          {/if}
        </div>

        <div class="relative">
          <button onclick={() => showHighlightPicker = !showHighlightPicker} class="deck-btn" title="Highlight Background"><Highlighter class="w-3.5 h-3.5 text-amber-500" /></button>
          {#if showHighlightPicker}
            <div class="absolute top-full left-0 mt-1 z-50 p-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-xl grid grid-cols-5 gap-1.5 w-40">
              {#each HIGHLIGHT_COLORS as c}
                <button onclick={() => applyHighlight(c)} class="w-5 h-5 rounded border border-slate-300 dark:border-slate-600 hover:scale-110 transition" style="background:{c}"></button>
              {/each}
            </div>
          {/if}
        </div>

        <div class="h-3.5 w-px bg-slate-200 dark:bg-slate-800"></div>

        <!-- Alignment -->
        <button onclick={() => exec('justifyLeft')} class="deck-btn" title="Align Left"><AlignLeft class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('justifyCenter')} class="deck-btn" title="Align Center"><AlignCenter class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('justifyRight')} class="deck-btn" title="Align Right"><AlignRight class="w-3.5 h-3.5" /></button>

        <div class="h-3.5 w-px bg-slate-200 dark:bg-slate-800"></div>

        <!-- Lists & Links -->
        <button onclick={() => exec('insertUnorderedList')} class="deck-btn" title="Bullet List"><List class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('insertOrderedList')} class="deck-btn" title="Numbered List"><ListOrdered class="w-3.5 h-3.5" /></button>
        <button onclick={insertLink} class="deck-btn" title="Insert Link"><Link class="w-3.5 h-3.5" /></button>
        <button onclick={() => exec('removeFormat')} class="deck-btn text-red-500" title="Clear Formatting"><Eraser class="w-3.5 h-3.5" /></button>

      </div>
    {/if}

    <!-- Right Group: Save State & Contextual Properties Toggle -->
    <div class="flex items-center gap-2 ml-auto">
      <button onclick={() => void saveActiveSlideContent()} class="btn-primary text-xs px-3 py-1.5" title="Save current slide">Save</button>
      {#if saveState === 'saving'}
        <span class="text-xs text-purple-500 font-mono animate-pulse">Saving…</span>
      {:else if saveState === 'saved'}
        <span class="text-xs text-emerald-500 font-mono flex items-center gap-1"><Check class="w-3 h-3" /> Saved</span>
      {/if}

      <button
        onclick={() => showProperties = !showProperties}
        class="deck-btn text-xs px-2.5 py-1 border border-slate-200 dark:border-slate-700 {showProperties ? 'bg-purple-100 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 border-purple-400 dark:border-purple-600/50' : 'bg-slate-100 dark:bg-slate-800'}"
        title="Toggle Properties Panel"
      >
        <SlidersHorizontal class="w-3.5 h-3.5" />
      </button>
    </div>

  </header>

  <!-- MAIN DECK EDITOR BODY: LEFT NAV | CENTER CANVAS | RIGHT PROPERTIES -->
  <div class="flex-1 flex overflow-hidden relative">

    <!-- LEFT SLIDE NAVIGATOR -->
    <aside class="w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex flex-col flex-shrink-0 select-none transition-colors">
      <div class="p-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
        <span class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Slides ({slides.length})</span>
        <label class="cursor-pointer text-[11px] font-semibold text-purple-600 dark:text-purple-400 hover:underline flex items-center gap-1">
          <Upload class="w-3 h-3" />
          <span>Upload File</span>
          <input type="file" accept=".pdf,.ppt,.pptx" class="hidden" onchange={handleFileUploadChange} />
        </label>
      </div>

      <!-- Slide Thumbnails Scroll Area -->
      <div class="flex-1 overflow-y-auto p-3 space-y-3">
        {#each slides as slide, index (slide.id)}
          {@const isActive = slide.id === activeSlideId}
          {@const stype = slide.type?.toUpperCase()}
          {@const cj = slide.content_json || {}}
          
          <div
            draggable="true"
            ondragstart={() => handleDragStart(index)}
            ondragover={(e) => e.preventDefault()}
            ondrop={() => handleDrop(index)}
            onclick={() => onSelectSlide(slide.id)}
            role="button"
            tabindex="0"
            onkeydown={(e) => { if (e.key === 'Enter') onSelectSlide(slide.id); }}
            class="group relative flex items-start gap-2 p-2 rounded-xl border transition-all cursor-pointer {isActive ? 'bg-purple-50 dark:bg-purple-950/40 border-purple-500 shadow-md ring-1 ring-purple-500/30' : 'bg-slate-50 dark:bg-slate-950/60 border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'}"
          >
            <!-- Drag Handle & Slide Number -->
            <div class="flex flex-col items-center gap-1 shrink-0 text-slate-400 dark:text-slate-500 group-hover:text-slate-600 dark:group-hover:text-slate-300">
              <GripVertical class="w-3.5 h-3.5 cursor-grab active:cursor-grabbing" />
              <span class="font-mono text-[10px] font-bold">{index + 1}</span>
            </div>

            <!-- Slide Thumbnail Preview -->
            <div class="flex-1 min-w-0 bg-white dark:bg-slate-900 rounded-lg p-2 aspect-[16/9] border border-slate-200 dark:border-slate-800 flex flex-col justify-between overflow-hidden text-[10px] shadow-sm">
              {#if stype === 'CONTENT'}
                <div class="font-bold truncate text-slate-800 dark:text-slate-200">{cj.title || 'Untitled Slide'}</div>
                <div class="text-slate-500 dark:text-slate-400 line-clamp-2 leading-tight text-[9px]">{cj.subtitle || cj.body?.replace(/<[^>]*>/g, '') || ''}</div>
              {:else}
                <div class="flex items-center gap-1 font-semibold text-purple-600 dark:text-purple-400 uppercase tracking-wider text-[9px]">
                  {#if stype === 'POLL'}<BarChart3 class="w-3 h-3 text-emerald-500" /> Poll
                  {:else if stype === 'QNA'}<MessageSquare class="w-3 h-3 text-cyan-500" /> Q&A
                  {:else if stype === 'WORD_CLOUD'}<Cloud class="w-3 h-3 text-amber-500" /> Word Cloud
                  {:else}<FeedbackIcon class="w-3 h-3 text-rose-500" /> Feedback
                  {/if}
                </div>
                <div class="font-medium text-slate-700 dark:text-slate-300 truncate">{cj.question || cj.prompt || 'Interactive prompt'}</div>
              {/if}
            </div>

            <!-- Slide Actions Hover Overlay -->
            <div class="absolute right-2 top-2 opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity bg-white dark:bg-slate-900 p-1 rounded-md border border-slate-200 dark:border-slate-700 shadow-md">
              {#if onDuplicateSlide}
                <button onclick={(e) => { e.stopPropagation(); onDuplicateSlide(slide.id); }} class="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white p-0.5" title="Duplicate"><Copy class="w-3 h-3" /></button>
              {/if}
              <button onclick={(e) => { e.stopPropagation(); onDeleteSlide(slide.id); }} class="text-slate-500 hover:text-red-500 p-0.5" title="Delete"><Trash2 class="w-3 h-3" /></button>
            </div>
          </div>
        {/each}
      </div>
    </aside>

    <!-- CENTER SLIDE CANVAS STAGE -->
    <main class="flex-1 bg-slate-100 dark:bg-slate-950 flex flex-col items-center justify-center p-4 sm:p-8 overflow-y-auto relative select-text transition-colors">
      
      {#if !activeSlide}
        <div class="text-center text-slate-400 dark:text-slate-500">No slide selected. Click "New Slide" to get started.</div>
      {:else}

        <!-- 16:9 Presentation Slide Card -->
        <div
          class="deck-canvas-card relative w-full max-w-5xl aspect-[16/9] rounded-2xl shadow-2xl transition-all border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 flex flex-col p-8 sm:p-14 overflow-hidden"
        >
          {#if activeType === 'CONTENT'}

            <!-- TITLE SLIDE LAYOUT -->
            {#if activeLayout === 'title'}
              <div class="flex-1 flex flex-col items-center justify-center text-center space-y-4 max-w-3xl mx-auto w-full my-auto">
                <textarea
                  rows="2"
                  bind:value={localTitle}
                  oninput={() => debouncedSave()}
                  placeholder="Click to add slide title"
                  class="w-full font-extrabold bg-transparent text-center outline-none border-b border-transparent hover:border-purple-400/50 focus:border-purple-500 transition px-2 py-1 placeholder-slate-400 dark:placeholder-slate-600 resize-none"
                  style={getFitTitleStyle(localTitle, 'title')}
                ></textarea>
                <input
                  type="text"
                  bind:value={localSubtitle}
                  oninput={() => debouncedSave()}
                  placeholder="Click to add subtitle or presenter name"
                  class="w-full text-xl sm:text-2xl font-medium opacity-80 bg-transparent text-center outline-none border-b border-transparent hover:border-purple-400/50 focus:border-purple-500 transition px-2 py-1 placeholder-slate-400 dark:placeholder-slate-600"
                />
              </div>

            <!-- SECTION HEADER LAYOUT -->
            {:else if activeLayout === 'section'}
              <div class="flex-1 flex flex-col items-center justify-center text-center p-8 rounded-2xl bg-purple-500/10 border border-purple-500/20 my-auto w-full">
                <textarea
                  rows="2"
                  bind:value={localTitle}
                  oninput={() => debouncedSave()}
                  placeholder="Section Title"
                  class="w-full font-black tracking-tight text-purple-600 dark:text-purple-400 bg-transparent text-center outline-none border-b border-transparent hover:border-purple-400 focus:border-purple-500 transition px-2 py-1 placeholder-purple-400/50 resize-none"
                  style={getFitTitleStyle(localTitle, 'title')}
                ></textarea>
                <input
                  type="text"
                  bind:value={localSubtitle}
                  oninput={() => debouncedSave()}
                  placeholder="Section summary or key takeaway"
                  class="w-full text-lg sm:text-xl font-medium opacity-80 bg-transparent text-center outline-none border-b border-transparent hover:border-purple-400 focus:border-purple-500 transition px-2 py-1 mt-4 placeholder-slate-400 dark:placeholder-slate-600"
                />
              </div>

            <!-- TWO COLUMNS LAYOUT -->
            {:else if activeLayout === 'two_column'}
              <div class="flex-1 flex flex-col space-y-4 h-full">
                <input
                  type="text"
                  bind:value={localTitle}
                  oninput={() => debouncedSave()}
                  placeholder="Slide Title"
                  class="w-full font-bold bg-transparent outline-none border-b border-transparent hover:border-purple-400/50 focus:border-purple-500 transition px-2 py-1 placeholder-slate-400 dark:placeholder-slate-600"
                  style={getFitTitleStyle(localTitle, 'title')}
                />
                <div class="flex-1 grid grid-cols-2 gap-6 overflow-hidden">
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

            <!-- IMAGE & TEXT LAYOUT -->
            {:else if activeLayout === 'image_text'}
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
                      <input type="file" accept=".pdf,.ppt,.pptx" class="hidden" onchange={handleFileUploadChange} />
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

            <!-- DEFAULT TITLE & CONTENT LAYOUT -->
            {:else}
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
            {/if}

          {:else}
            <!-- INTERACTIVE SLIDE CANVAS (POLL / QNA / WORD CLOUD / FEEDBACK) -->
            <div class="flex-1 flex flex-col items-center justify-center text-center max-w-3xl mx-auto space-y-5 w-full h-full overflow-hidden">
              
              <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                {#if activeType === 'POLL'}<BarChart3 class="w-4 h-4 text-emerald-500" /> Interactive Poll
                {:else if activeType === 'QNA'}<MessageSquare class="w-4 h-4 text-cyan-500" /> Interactive Q&A
                {:else if activeType === 'WORD_CLOUD'}<Cloud class="w-4 h-4 text-amber-500" /> Word Cloud
                {:else}<FeedbackIcon class="w-4 h-4 text-rose-500" /> Audience Feedback
                {/if}
              </div>

              {#if activeType === 'POLL'}
                <textarea
                  rows="2"
                  bind:value={localQuestion}
                  oninput={() => debouncedSave()}
                  placeholder="Type your poll question here…"
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
              {:else}
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
              {/if}

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
          <div class="space-y-2 border-t border-slate-200 dark:border-slate-800 pt-3">
            <span class="text-[10px] font-bold uppercase text-slate-400">Media & Attachments</span>
            {#if activeSlide.content_json?.file_url || activeSlide.content_json?.has_file}
              <div class="text-xs text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-950 p-3 rounded-lg border border-slate-200 dark:border-slate-800 space-y-2">
                <div class="font-mono truncate">Page {activeSlide.content_json?.file_page || 1} of {activeSlide.content_json?.total_pages || 1}</div>
                <label class="cursor-pointer inline-block text-purple-600 dark:text-purple-400 hover:underline">
                  Replace slide file
                  <input type="file" accept=".pdf,.ppt,.pptx" class="hidden" onchange={handleFileUploadChange} />
                </label>
              </div>
            {:else}
              <label class="flex flex-col items-center justify-center p-4 rounded-xl border border-dashed border-slate-300 dark:border-slate-700 hover:border-purple-500 cursor-pointer text-xs text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition">
                <Upload class="w-5 h-5 mb-1 text-purple-500" />
                <span>Upload PDF / PPTX slide</span>
                <input type="file" accept=".pdf,.ppt,.pptx" class="hidden" onchange={handleFileUploadChange} />
              </label>
            {/if}
          </div>

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
