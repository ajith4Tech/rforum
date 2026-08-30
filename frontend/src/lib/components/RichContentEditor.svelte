<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import {
    Bold, Italic, Underline, Strikethrough, AlignLeft, AlignCenter, AlignRight,
    AlignJustify, List, ListOrdered, Link, Code, Eraser, Undo2, Redo2,
    Type, Highlighter, ChevronDown, Presentation, MonitorPlay, Sparkles, Sun, Moon
  } from 'lucide-svelte';

  let {
    value = '',
    placeholder = 'Click here to add slide text, headings, or bullet points…',
    onchange,
    class: className = ''
  }: {
    value?: string;
    placeholder?: string;
    onchange?: (html: string) => void;
    class?: string;
  } = $props();

  let editorEl: HTMLDivElement | null = $state(null);
  let initialized = false;
  let wordCount = $state(0);
  let charCount = $state(0);
  let slideTheme = $state<'dark' | 'light'>('dark');

  // ── toolbar dropdowns ───────────────────────────────────────────────────
  let showColorPicker = $state(false);
  let showHighlightPicker = $state(false);
  let showFontSize = $state(false);
  let showFontFamily = $state(false);

  const TEXT_COLORS = [
    '#ffffff', '#f8fafc', '#cbd5e1', '#64748b', '#0f172a',
    '#ef4444', '#f97316', '#f59e0b', '#84cc16', '#10b981',
    '#06b6d4', '#3b82f6', '#6366f1', '#a855f7', '#ec4899',
  ];
  const HIGHLIGHT_COLORS = [
    '#fef08a', '#bbf7d0', '#bae6fd', '#e9d5ff', '#fecaca',
    '#fed7aa', '#d9f99d', '#f5d0fe', '#334155', 'transparent',
  ];
  const FONT_SIZES = ['14px','16px','18px','22px','26px','32px','40px','48px','56px'];
  const FONT_FAMILIES = [
    { label: 'Inter (Sans)', value: 'Inter, system-ui, sans-serif' },
    { label: 'Glacial (Modern)', value: "'Glacial Indifference', Inter, sans-serif" },
    { label: 'JetBrains (Mono)', value: "'JetBrains Mono', monospace" },
    { label: 'Georgia (Serif)', value: 'Georgia, serif' },
  ];

  function updateCounts() {
    if (!editorEl) return;
    const txt = editorEl.innerText || '';
    charCount = txt.length;
    wordCount = txt.trim() ? txt.trim().split(/\s+/).length : 0;
  }

  // ── init / sync ────────────────────────────────────────────────────────
  onMount(() => {
    if (!editorEl) return;
    if (value && value.trim()) {
      editorEl.innerHTML = value;
    }
    updateCounts();
    initialized = true;
  });

  $effect(() => {
    if (!initialized || !editorEl) return;
    const current = editorEl.innerHTML;
    const isEmpty = !current || current === '<br>' || current === '<p><br></p>';
    const incomingEmpty = !value || value.trim() === '';
    if (isEmpty && incomingEmpty) return;
    if (current !== value) {
      editorEl.innerHTML = value || '';
      updateCounts();
    }
  });

  function handleInput() {
    if (!editorEl) return;
    updateCounts();
    onchange?.(editorEl.innerHTML);
  }

  function handleKeydown(e: KeyboardEvent) {
    const mod = e.ctrlKey || e.metaKey;
    if (mod) {
      switch (e.key.toLowerCase()) {
        case 'b': e.preventDefault(); exec('bold'); break;
        case 'i': e.preventDefault(); exec('italic'); break;
        case 'u': e.preventDefault(); exec('underline'); break;
        case 'z': if (!e.shiftKey) { e.preventDefault(); exec('undo'); } break;
        case 'y': e.preventDefault(); exec('redo'); break;
      }
      if (e.shiftKey && e.key.toLowerCase() === 'z') { e.preventDefault(); exec('redo'); }
    }
    if (e.key === 'Tab') {
      e.preventDefault();
      exec('insertHTML', e.shiftKey ? '' : '&nbsp;&nbsp;&nbsp;&nbsp;');
    }
  }

  function exec(cmd: string, value?: string) {
    editorEl?.focus();
    // eslint-disable-next-line @typescript-eslint/no-deprecated
    document.execCommand(cmd, false, value ?? undefined);
    handleInput();
  }

  function toggleBlock(tag: string) {
    exec('formatBlock', `<${tag}>`);
  }

  function insertLink() {
    const url = prompt('Enter URL:');
    if (url) exec('createLink', url);
  }

  function applyFontSize(size: string) {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
      exec('insertHTML', `<span style="font-size:${size}">&#8203;</span>`);
    } else {
      exec('insertHTML', `<span style="font-size:${size}">${sel.toString()}</span>`);
    }
    showFontSize = false;
  }

  function applyFontFamily(family: string) {
    exec('fontName', family);
    showFontFamily = false;
  }

  function applyColor(color: string) {
    exec('foreColor', color);
    showColorPicker = false;
  }

  function applyHighlight(color: string) {
    exec('hiliteColor', color);
    showHighlightPicker = false;
  }

  function closeDropdowns() {
    showColorPicker = false;
    showHighlightPicker = false;
    showFontSize = false;
    showFontFamily = false;
  }

  function handlePaste(e: ClipboardEvent) {
    e.preventDefault();
    const html = e.clipboardData?.getData('text/html');
    const text = e.clipboardData?.getData('text/plain');
    if (html) {
      const tmp = document.createElement('div');
      tmp.innerHTML = html;
      tmp.querySelectorAll('script,style,meta,link').forEach(n => n.remove());
      tmp.querySelectorAll('*').forEach(el => {
        Array.from(el.attributes).forEach(attr => {
          if (attr.name.startsWith('on') || attr.name === 'class') el.removeAttribute(attr.name);
        });
      });
      exec('insertHTML', tmp.innerHTML);
    } else if (text) {
      const escaped = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
      exec('insertHTML', escaped);
    }
  }

  function onWindowClick(e: MouseEvent) {
    const t = e.target as HTMLElement;
    if (!t.closest('.rce-dropdown-anchor')) closeDropdowns();
  }

  onMount(() => { window.addEventListener('click', onWindowClick); });
  onDestroy(() => { window.removeEventListener('click', onWindowClick); });
</script>

<!-- Presentation Content Editor -->
<div class="pres-workspace {className}">

  <!-- Top Presentation Control Bar -->
  <div class="pres-toolbar" onmousedown={(e) => e.preventDefault()} role="toolbar" aria-label="Slide Editor Toolbar">
    
    <!-- Left: Slide Mode & Ratio badge -->
    <div class="pres-toolbar-meta">
      <Presentation class="w-4 h-4 text-purple-400" />
      <span class="text-xs font-semibold text-slate-300 tracking-wide hidden sm:inline">Presentation Slide</span>
    </div>

    <div class="pres-sep"></div>

    <!-- Undo / Redo -->
    <div class="pres-group">
      <button class="pres-btn" onclick={() => exec('undo')} title="Undo (Ctrl+Z)"><Undo2 class="w-3.5 h-3.5" /></button>
      <button class="pres-btn" onclick={() => exec('redo')} title="Redo (Ctrl+Y)"><Redo2 class="w-3.5 h-3.5" /></button>
    </div>

    <div class="pres-sep"></div>

    <!-- Heading format -->
    <div class="pres-group">
      <button class="pres-btn font-bold text-xs" onclick={() => toggleBlock('h1')} title="Slide Title (H1)">H1</button>
      <button class="pres-btn font-bold text-xs" onclick={() => toggleBlock('h2')} title="Subtitle (H2)">H2</button>
      <button class="pres-btn font-bold text-xs" onclick={() => toggleBlock('h3')} title="Section (H3)">H3</button>
      <button class="pres-btn font-bold text-xs" onclick={() => toggleBlock('p')} title="Paragraph (Body)">¶</button>
    </div>

    <div class="pres-sep"></div>

    <!-- Font family dropdown -->
    <div class="pres-group rce-dropdown-anchor relative">
      <button
        class="pres-btn text-xs font-medium gap-1"
        onclick={() => { showFontFamily = !showFontFamily; showFontSize = showColorPicker = showHighlightPicker = false; }}
        title="Font Family"
      >
        <Type class="w-3.5 h-3.5" />
        <ChevronDown class="w-2.5 h-2.5 opacity-60" />
      </button>
      {#if showFontFamily}
        <div class="pres-dropdown" role="listbox">
          {#each FONT_FAMILIES as f}
            <button class="pres-dropdown-item" style="font-family:{f.value}" onclick={() => applyFontFamily(f.value)}>{f.label}</button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Font size dropdown -->
    <div class="pres-group rce-dropdown-anchor relative">
      <button
        class="pres-btn text-xs font-bold gap-1"
        onclick={() => { showFontSize = !showFontSize; showFontFamily = showColorPicker = showHighlightPicker = false; }}
        title="Font Size"
      >
        Aa <ChevronDown class="w-2.5 h-2.5 opacity-60" />
      </button>
      {#if showFontSize}
        <div class="pres-dropdown" role="listbox">
          {#each FONT_SIZES as size}
            <button class="pres-dropdown-item font-mono" style="font-size:{size}" onclick={() => applyFontSize(size)}>{size}</button>
          {/each}
        </div>
      {/if}
    </div>

    <div class="pres-sep"></div>

    <!-- Inline styling -->
    <div class="pres-group">
      <button class="pres-btn" onclick={() => exec('bold')} title="Bold (Ctrl+B)"><Bold class="w-3.5 h-3.5" /></button>
      <button class="pres-btn" onclick={() => exec('italic')} title="Italic (Ctrl+I)"><Italic class="w-3.5 h-3.5" /></button>
      <button class="pres-btn" onclick={() => exec('underline')} title="Underline (Ctrl+U)"><Underline class="w-3.5 h-3.5" /></button>
      <button class="pres-btn" onclick={() => exec('strikeThrough')} title="Strikethrough"><Strikethrough class="w-3.5 h-3.5" /></button>
      <button class="pres-btn" onclick={() => exec('insertHTML', '<code style="font-family:monospace;background:rgba(139,92,246,0.15);padding:0.1em 0.4em;border-radius:4px">' + (window.getSelection()?.toString() || '​') + '</code>')} title="Inline Code"><Code class="w-3.5 h-3.5" /></button>
    </div>

    <div class="pres-sep"></div>

    <!-- Colors -->
    <div class="pres-group">
      <div class="rce-dropdown-anchor relative">
        <button
          class="pres-btn font-bold text-xs gap-1"
          onclick={() => { showColorPicker = !showColorPicker; showHighlightPicker = showFontSize = showFontFamily = false; }}
          title="Text Color"
        >
          <span class="underline decoration-purple-400 font-extrabold text-sm">A</span>
          <ChevronDown class="w-2.5 h-2.5 opacity-60" />
        </button>
        {#if showColorPicker}
          <div class="pres-dropdown pres-color-grid">
            {#each TEXT_COLORS as col}
              <button class="pres-swatch" style="background:{col}" onclick={() => applyColor(col)} title={col}></button>
            {/each}
          </div>
        {/if}
      </div>

      <div class="rce-dropdown-anchor relative">
        <button
          class="pres-btn gap-1"
          onclick={() => { showHighlightPicker = !showHighlightPicker; showColorPicker = showFontSize = showFontFamily = false; }}
          title="Highlight Background"
        >
          <Highlighter class="w-3.5 h-3.5 text-amber-400" />
          <ChevronDown class="w-2.5 h-2.5 opacity-60" />
        </button>
        {#if showHighlightPicker}
          <div class="pres-dropdown pres-color-grid">
            {#each HIGHLIGHT_COLORS as col}
              <button class="pres-swatch {col === 'transparent' ? 'swatch-none' : ''}" style="background:{col}" onclick={() => applyHighlight(col)} title={col}></button>
            {/each}
          </div>
        {/if}
      </div>
    </div>

    <div class="pres-sep"></div>

    <!-- Alignment -->
    <div class="pres-group">
      <button class="pres-btn" onclick={() => exec('justifyLeft')} title="Align Left"><AlignLeft class="w-3.5 h-3.5" /></button>
      <button class="pres-btn" onclick={() => exec('justifyCenter')} title="Align Center"><AlignCenter class="w-3.5 h-3.5" /></button>
      <button class="pres-btn" onclick={() => exec('justifyRight')} title="Align Right"><AlignRight class="w-3.5 h-3.5" /></button>
      <button class="pres-btn" onclick={() => exec('justifyFull')} title="Justify"><AlignJustify class="w-3.5 h-3.5" /></button>
    </div>

    <div class="pres-sep"></div>

    <!-- Lists & Link -->
    <div class="pres-group">
      <button class="pres-btn" onclick={() => exec('insertUnorderedList')} title="Bullet List"><List class="w-3.5 h-3.5" /></button>
      <button class="pres-btn" onclick={() => exec('insertOrderedList')} title="Numbered List"><ListOrdered class="w-3.5 h-3.5" /></button>
      <button class="pres-btn" onclick={insertLink} title="Insert Link"><Link class="w-3.5 h-3.5" /></button>
      <button class="pres-btn" onclick={() => exec('removeFormat')} title="Clear Formatting"><Eraser class="w-3.5 h-3.5 text-red-400" /></button>
    </div>

    <!-- Right-aligned Slide Theme Preview Switcher -->
    <div class="ml-auto flex items-center gap-1.5 pl-2">
      <button
        class="pres-btn gap-1 text-[11px] font-semibold px-2 py-1 bg-white/5 hover:bg-white/10 rounded-md border border-white/10"
        onclick={() => slideTheme = slideTheme === 'dark' ? 'light' : 'dark'}
        title="Toggle Slide Preview Mode (Dark / Light Canvas)"
      >
        {#if slideTheme === 'dark'}
          <Moon class="w-3 h-3 text-purple-400" />
          <span>Dark Canvas</span>
        {:else}
          <Sun class="w-3 h-3 text-amber-400" />
          <span>Light Canvas</span>
        {/if}
      </button>
    </div>

  </div>

  <!-- Main Presentation Canvas Workbench (Centered 16:9 Slide Stage) -->
  <div class="pres-stage">
    
    <!-- 16:9 Presentation Slide Card -->
    <div class="pres-card {slideTheme === 'light' ? 'bg-white text-slate-900 border-slate-200' : 'bg-slate-950 text-white border-purple-500/20'}">
      
      <!-- Slide Canvas Header Badge -->
      <div class="pres-card-badge">
        <Sparkles class="w-3 h-3 text-purple-400" />
        <span>PRESENTATION SLIDE</span>
      </div>

      <!-- Contenteditable Slide Body -->
      <div
        bind:this={editorEl}
        class="pres-canvas prose max-w-none focus:outline-none {slideTheme === 'light' ? 'prose-slate' : 'prose-invert'}"
        contenteditable="true"
        role="textbox"
        aria-multiline="true"
        aria-label="Slide content canvas"
        data-placeholder={placeholder}
        oninput={handleInput}
        onkeydown={handleKeydown}
        onpaste={handlePaste}
        spellcheck="true"
      ></div>

      <!-- Slide Footer Bar: Word & Character counts -->
      <div class="pres-card-footer">
        <span class="font-mono text-[11px] opacity-40">{wordCount} words • {charCount} chars</span>
      </div>

    </div>

  </div>

</div>

<style>
  .pres-workspace {
    display: flex;
    flex-direction: column;
    width: 100%;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.1);
    background: #0b0d14;
    box-shadow: 0 8px 30px rgba(0,0,0,0.5);
  }

  .pres-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 3px;
    padding: 8px 12px;
    background: #141724;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }

  .pres-toolbar-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 2px 6px;
  }

  .pres-group {
    display: flex;
    align-items: center;
    gap: 2px;
  }

  .pres-sep {
    width: 1px;
    height: 18px;
    background: rgba(255,255,255,0.12);
    margin: 0 4px;
    flex-shrink: 0;
  }

  .pres-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 5px 7px;
    border-radius: 6px;
    border: none;
    background: transparent;
    color: #cbd5e1;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .pres-btn:hover {
    background: rgba(255,255,255,0.1);
    color: #ffffff;
  }

  .pres-dropdown {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    z-index: 250;
    background: #1a1d2e;
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 8px;
    padding: 6px;
    min-width: 130px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.5);
  }

  .pres-dropdown-item {
    display: block;
    width: 100%;
    text-align: left;
    padding: 6px 10px;
    border: none;
    background: transparent;
    color: #e2e8f0;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.12s ease;
  }
  .pres-dropdown-item:hover {
    background: #2d3248;
    color: #fff;
  }

  .pres-color-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    width: 160px;
    padding: 8px;
  }

  .pres-swatch {
    width: 24px;
    height: 24px;
    border-radius: 5px;
    border: 1px solid rgba(255,255,255,0.2);
    cursor: pointer;
    transition: transform 0.1s ease;
  }
  .pres-swatch:hover {
    transform: scale(1.2);
  }
  .swatch-none {
    background-image: linear-gradient(45deg, #ef4444 0%, #ef4444 45%, #eee 45%, #eee 55%, #ef4444 55%, #ef4444 100%) !important;
  }

  .pres-stage {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 24px;
    background: radial-gradient(circle at center, #171b2a 0%, #090b10 100%);
    min-height: 420px;
  }

  .pres-card {
    position: relative;
    width: 100%;
    max-width: 820px;
    min-height: 380px;
    aspect-ratio: 16 / 9;
    border-radius: 16px;
    border-width: 1px;
    box-shadow: 0 20px 50px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.05);
    display: flex;
    flex-direction: column;
    padding: 32px 36px;
    transition: all 0.3s ease;
  }

  .pres-card-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #a855f7;
    margin-bottom: 12px;
    user-select: none;
  }

  .pres-canvas {
    flex: 1;
    outline: none;
    line-height: 1.65;
    font-size: 18px;
    word-break: break-word;
  }

  .pres-canvas:empty::before {
    content: attr(data-placeholder);
    pointer-events: none;
    opacity: 0.35;
    font-style: italic;
  }

  .pres-card-footer {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    margin-top: 16px;
    padding-top: 8px;
    border-top: 1px dashed rgba(255,255,255,0.08);
  }

  :global(.pres-canvas h1) { font-size: 2.2em; font-weight: 800; margin: 0.4em 0 0.25em; line-height: 1.2; letter-spacing: -0.01em; }
  :global(.pres-canvas h2) { font-size: 1.6em; font-weight: 700; margin: 0.4em 0 0.2em; line-height: 1.25; }
  :global(.pres-canvas h3) { font-size: 1.25em; font-weight: 600; margin: 0.3em 0 0.15em; line-height: 1.3; }
  :global(.pres-canvas p)  { margin: 0.35em 0; }
  :global(.pres-canvas ul),
  :global(.pres-canvas ol) { padding-left: 1.5em; margin: 0.4em 0; }
  :global(.pres-canvas li) { margin: 0.2em 0; }
  :global(.pres-canvas a)  { color: #a855f7; text-decoration: underline; }
  :global(.pres-canvas code) { font-family: 'JetBrains Mono', monospace; font-size: 0.88em; }
</style>
