<script lang="ts">
  import {
    getSession, updateSession, sendScreenControl, createSlide, updateSlide, deleteSlide, listResponses,
    getSessionPresentation, uploadPresentation, replacePresentation, regeneratePresentation,
    insertTimelineItem, updateTimelineItem, deleteTimelineItem, reorderTimelineItems, activateTimelineItem,
    attachPresentation, detachPresentation, deletePresentation, uploadSlideFile
  } from '$lib/api';
  import { page } from '$app/stores';
  import { RforumWebSocket } from '$lib/ws';
  import type { ConnectionStatus as WsStatus } from '$lib/ws';
  import { token } from '$lib/stores';
  import { get } from 'svelte/store';
  import { onMount, onDestroy } from 'svelte';
  import { beforeNavigate, goto } from '$app/navigation';
  import Modal from '$lib/components/Modal.svelte';
  import {
    NotebookPen,
    UserRound,
    Users
  } from 'lucide-svelte';
  import PresentationWorkspace from '$lib/components/timeline/PresentationWorkspace.svelte';
  import PresentationEmptyState from '$lib/components/timeline/PresentationEmptyState.svelte';
  import DeckEditor from '$lib/components/DeckEditor.svelte';
  import DeckView from '$lib/components/DeckView.svelte';
  import { upsertTimelineItemFromWs } from '$lib/timelineTypes';
  import { UndoManager, type IdBox } from '$lib/undoManager';
  import { mergeResponsesById, responsesForSlide } from '$lib/fitTitle';

  const sessionId = $derived($page.params.sessionId);

  let session: any = $state(null);
  let slides: any[] = $state([]);
  let activeSlideId: string | null = $state(null);
  let slideResponses: any[] = $state([]);
  let ws: RforumWebSocket | null = $state(null);
  let wsStatus: WsStatus = $state('disconnected');
  let loading = $state(true);
  const editorMode = $derived($page.url.searchParams.get('mode') === 'editor');
  let errorMessage = $state('');
  let contentTitle = $state('');
  let contentBody = $state('');
  let contentFile: FileList | null = $state(null);
  let pollQuestion = $state('');
  let pollOptions = $state<string[]>([]);
  let qnaPrompt = $state('');
  let feedbackPrompt = $state('');
  let wordCloudPrompt = $state('');
  let editingSlideId = $state<string | null>(null);
  let moderatorNotes = $state('');
  let moderatorName = $state('');
  let speakerNameInput = $state('');
  let speakerNames = $state<string[]>([]);
  let savingModeratorSetup = $state(false);
  let notesSavedFlash = $state(false);
  let notesSaveTimer: ReturnType<typeof setTimeout> | null = null;
  let screenCommandFlash = $state('');
  let screenCommandTimer: ReturnType<typeof setTimeout> | null = null;
  let deckEditorDirty = $state(false);
  let deckEditorSave: null | (() => Promise<void>) = null;
  let startNativeEditor = $state(false);
  let previewItemId = $state<string | null>(null);
  let lastWsStatus: WsStatus = 'disconnected';
  let leavePromptOpen = $state(false);
  let leavePromptTitle = $state('');
  let leavePromptDescription = $state('');
  let pendingLeaveUrl = $state('');
  let bypassLeaveGuard = false;
  const activeSlide = $derived(getActiveSlide());
  const activeType = $derived(activeSlide?.type?.toUpperCase());

  // ── Presentation Timeline (additive — only used when session.presentation_id is set) ──
  let presentation: any = $state(null);
  let timeline: any = $state(null);
  let timelineResponses: any[] = $state([]);
  let saveState: 'idle' | 'saving' | 'saved' = $state('idle');
  let saveStateTimeout: ReturnType<typeof setTimeout> | null = null;

  async function withSaveState<T>(fn: () => Promise<T>): Promise<T> {
    saveState = 'saving';
    if (saveStateTimeout) clearTimeout(saveStateTimeout);
    try {
      const result = await fn();
      saveState = 'saved';
      saveStateTimeout = setTimeout(() => { saveState = 'idle'; }, 2000);
      return result;
    } catch (err) {
      saveState = 'idle';
      saveError = err instanceof Error ? err.message : 'Save failed';
      saveErrorTimeout && clearTimeout(saveErrorTimeout);
      saveErrorTimeout = setTimeout(() => { saveError = ''; }, 4000);
      throw err;
    }
  }

  // ── Undo / Redo (works across both the legacy slide editor and the
  // presentation-timeline editor — only one is ever active per session) ──
  const undoManager = new UndoManager();
  let canUndo = $state(false);
  let canRedo = $state(false);
  let undoRedoBusy = $state(false);
  let undoRedoLabel = $state('');
  undoManager.onChange = () => {
    canUndo = undoManager.canUndo;
    canRedo = undoManager.canRedo;
    undoRedoBusy = undoManager.isBusy;
  };

  async function performUndo() {
    if (!canUndo || undoRedoBusy) return;
    undoRedoLabel = 'Undoing…';
    try {
      await undoManager.undo();
    } catch (err) {
      saveError = err instanceof Error ? err.message : 'Undo failed';
      saveErrorTimeout && clearTimeout(saveErrorTimeout);
      saveErrorTimeout = setTimeout(() => { saveError = ''; }, 4000);
    } finally {
      undoRedoLabel = '';
    }
  }

  async function performRedo() {
    if (!canRedo || undoRedoBusy) return;
    undoRedoLabel = 'Redoing…';
    try {
      await undoManager.redo();
    } catch (err) {
      saveError = err instanceof Error ? err.message : 'Redo failed';
      saveErrorTimeout && clearTimeout(saveErrorTimeout);
      saveErrorTimeout = setTimeout(() => { saveError = ''; }, 4000);
    } finally {
      undoRedoLabel = '';
    }
  }

  // ── Unsaved-changes tracking (buffered edit forms use an explicit Save
  // button, not autosave-on-keystroke — so a form can be genuinely "dirty") ──
  let timelineFormDirty = $state(false);
  const legacyFormDirty = $derived.by(() => {
    if (!editingSlideId) return false;
    const active = getActiveSlide();
    if (!active) return false;
    const cj = active.content_json || {};
    switch (activeType) {
      case 'POLL': {
        const cleanedOptions = pollOptions.map((o) => o.trim()).filter(Boolean);
        return pollQuestion.trim() !== (cj.question || '') || JSON.stringify(cleanedOptions) !== JSON.stringify(cj.options || []);
      }
      case 'QNA':
        return qnaPrompt.trim() !== (cj.prompt || '');
      case 'FEEDBACK':
        return feedbackPrompt.trim() !== (cj.prompt || '');
      case 'WORD_CLOUD':
        return wordCloudPrompt.trim() !== (cj.prompt || '');
      case 'CONTENT':
        return contentTitle !== (cj.title || '') || contentBody !== (cj.body || '');
      default:
        return false;
    }
  });
  const hasUnsavedChanges = $derived(deckEditorDirty || legacyFormDirty);
  let saveError = $state('');
  let saveErrorTimeout: ReturnType<typeof setTimeout> | null = null;

  beforeNavigate((nav) => {
    if (bypassLeaveGuard) return;
    if (hasUnsavedChanges && nav.to?.url) {
      pendingLeaveUrl = nav.to.url.pathname + nav.to.url.search + nav.to.url.hash;
      leavePromptTitle = 'Unsaved changes';
      leavePromptDescription = 'Save your changes before leaving Edit Deck?';
      leavePromptOpen = true;
      nav.cancel();
    }
  });

  function handleBeforeUnload(e: BeforeUnloadEvent) {
    if (!hasUnsavedChanges) return;
    e.preventDefault();
    e.returnValue = '';
  }

  /** Same unsaved-changes gate as beforeNavigate/beforeunload above, but for
   * switching the active slide/timeline item in place — that also discards
   * an unsaved buffered edit (the {#key activeItem.id} remount and the
   * content-sync $effect both reset the edit buffers), so it needs the same
   * confirmation prompt as leaving the page entirely. */
  function confirmDiscardUnsavedChanges(): boolean {
    if (!hasUnsavedChanges) return true;
    return confirm('You have unsaved changes. Switch slides anyway?');
  }

  $effect(() => {
    const active = getActiveSlide();
    // Skip re-syncing the edit buffers while the moderator is actively
    // editing this same slide — otherwise any unrelated reassignment of
    // `slides` (e.g. a WS page_change event, or another moderator's edit
    // broadcast) re-runs this effect and silently overwrites in-progress,
    // unsaved keystrokes with the last-saved content_json.
    if (active && editingSlideId === active.id) return;
    if (active?.type?.toUpperCase() === 'CONTENT') {
      contentTitle = active.content_json?.title ?? '';
      contentBody = active.content_json?.body ?? '';
    }
    if (active?.type?.toUpperCase() === 'POLL') {
      pollQuestion = active.content_json?.question ?? '';
      pollOptions = active.content_json?.options ? [...active.content_json.options] : [];
    }
    if (active?.type?.toUpperCase() === 'QNA') {
      qnaPrompt = active.content_json?.prompt ?? '';
    }
    if (active?.type?.toUpperCase() === 'FEEDBACK') {
      feedbackPrompt = active.content_json?.prompt ?? '';
    }
    if (active?.type?.toUpperCase() === 'WORD_CLOUD') {
      wordCloudPrompt = active.content_json?.prompt ?? '';
    }
  });

  onMount(async () => {
    try {
      session = await getSession(sessionId);

      slides = session.slides || [];
      session.qr_visible = session.qr_visible ?? true;
      moderatorName = session.moderator_name || '';
      speakerNames = Array.isArray(session.speaker_names) ? [...session.speaker_names] : [];

      const active = slides.find((s: any) => s.is_active);
      if (active) {
        activeSlideId = active.id;
        previewItemId = active.id;
        await loadResponses(active.id);
      } else if (slides[0]?.id) {
        previewItemId = slides[0].id;
        await loadResponses(slides[0].id);
      }

      if (session.presentation_id) {
        await loadPresentationData();
      }

      // Load moderator notes for this session
      const savedNotes = localStorage.getItem(`rforum_notes_${sessionId}`);
      if (savedNotes !== null) moderatorNotes = savedNotes;

      // Connect WebSocket — pass our JWT so the server recognizes us as this
      // session's moderator (required to send slide_change/page_change/session_update)
      ws = new RforumWebSocket(session.unique_code, { token: get(token) || undefined });
      ws.onStatusChange((s) => {
        const wasReconnecting = wsStatus === 'reconnecting' || lastWsStatus === 'reconnecting';
        lastWsStatus = s;
        wsStatus = s;
        if (s === 'connected' && wasReconnecting) void refetchRelevantResponses();
      });
      ws.onMessage(handleWsMessage);
      ws.connect();
    } catch (error) {
      errorMessage = error?.message || 'Failed to load session. Please try again later.';
    } finally {
      loading = false;
    }
  });

  onDestroy(() => {
    if (notesSaveTimer) clearTimeout(notesSaveTimer);
    if (saveStateTimeout) clearTimeout(saveStateTimeout);
    if (saveErrorTimeout) clearTimeout(saveErrorTimeout);
    if (screenCommandTimer) clearTimeout(screenCommandTimer);
    ws?.disconnect();
  });

  function handleNotesInput(e: Event) {
    moderatorNotes = (e.currentTarget as HTMLTextAreaElement).value;
    if (notesSaveTimer) clearTimeout(notesSaveTimer);
    notesSaveTimer = setTimeout(() => {
      localStorage.setItem(`rforum_notes_${sessionId}`, moderatorNotes);
      notesSavedFlash = true;
      setTimeout(() => { notesSavedFlash = false; }, 1500);
    }, 600);
  }

  function handleWsMessage(msg: any) {
    // Presentation-timeline activation — distinct payload shape from the legacy
    // slide_change (timeline_item_id instead of slide_id), same event name per design.
    if (msg.event === 'slide_change' && msg.data?.timeline_item_id !== undefined) {
      if (timeline) {
        timeline = {
          ...timeline,
          active_timeline_item_id: msg.data.timeline_item_id,
          items: upsertTimelineItemFromWs(timeline.items || [], msg.data)
        };
      }
      if (msg.data.slide) {
        if (!previewItemId || previewItemId === msg.data.timeline_item_id) {
          loadTimelineResponses(msg.data.slide.id);
        }
      } else if (!previewItemId || previewItemId === msg.data.timeline_item_id) {
        timelineResponses = [];
      }
      return;
    }
    if (msg.event === 'new_response') {
      const relevantSlideId = currentPreviewSlideId();
      if (!msg.data?.id || (msg.data.slide_id && relevantSlideId && msg.data.slide_id !== relevantSlideId)) {
        return;
      }
      if (session?.presentation_id) {
        timelineResponses = mergeResponsesById(timelineResponses, [msg.data]);
      } else {
        slideResponses = mergeResponsesById(slideResponses, [msg.data]);
      }
    } else if (msg.event === 'upvote') {
      slideResponses = slideResponses.map((r) =>
        r.id === msg.data.id ? { ...r, upvotes: msg.data.upvotes } : r
      );
      timelineResponses = timelineResponses.map((r) =>
        r.id === msg.data.id ? { ...r, upvotes: msg.data.upvotes } : r
      );
    } else if (msg.event === 'page_change') {
      const active = getActiveSlide();
      if (active && msg.data?.slide_id === active.id) {
        slides = slides.map((s) =>
          s.id === active.id
            ? { ...s, content_json: { ...s.content_json, file_page: msg.data.file_page, total_pages: msg.data.total_pages ?? s.content_json?.total_pages } }
            : s
        );
      }
    } else if (msg.event === 'session_update') {
      if (session && msg.data?.is_live !== undefined) {
        session = { ...session, is_live: msg.data.is_live };
      }
      if (session && msg.data?.qr_visible !== undefined) {
        session = { ...session, qr_visible: msg.data.qr_visible };
      }
    } else if (msg.event === 'clear_responses') {
      const clearedId = msg.data?.slide_id;
      if (!clearedId) return;
      slideResponses = slideResponses.filter((r) => r.slide_id !== clearedId);
      timelineResponses = timelineResponses.filter((r) => r.slide_id !== clearedId);
    }
  }

  async function saveDeckEditor() {
    if (deckEditorSave) {
      await deckEditorSave();
    }
  }

  function requestNavigation(url: string) {
    if (hasUnsavedChanges) {
      pendingLeaveUrl = url;
      leavePromptTitle = 'Unsaved changes';
      leavePromptDescription = 'Save your changes before leaving Edit Deck?';
      leavePromptOpen = true;
      return;
    }
    goto(url);
  }

  async function handleLeavePromptDiscard() {
    if (!pendingLeaveUrl) {
      leavePromptOpen = false;
      return;
    }
    bypassLeaveGuard = true;
    leavePromptOpen = false;
    const target = pendingLeaveUrl;
    pendingLeaveUrl = '';
    try {
      await goto(target);
    } finally {
      bypassLeaveGuard = false;
    }
  }

  function handleLeavePromptCancel() {
    leavePromptOpen = false;
    pendingLeaveUrl = '';
  }

  async function handleLeavePromptSave() {
    if (!pendingLeaveUrl) {
      leavePromptOpen = false;
      return;
    }
    try {
      await saveDeckEditor();
    } catch {
      return;
    }
    bypassLeaveGuard = true;
    leavePromptOpen = false;
    const target = pendingLeaveUrl;
    pendingLeaveUrl = '';
    try {
      await goto(target);
    } finally {
      bypassLeaveGuard = false;
    }
  }

  async function loadResponses(slideId: string) {
    slideResponses = responsesForSlide(await listResponses(slideId), slideId);
  }

  function currentPreviewSlideId(): string | null {
    if (session?.presentation_id) {
      const itemId = previewItemId || timeline?.active_timeline_item_id;
      const item = (timeline?.items || []).find((i: any) => i.id === itemId);
      return item?.slide?.id ?? null;
    }
    return previewItemId || activeSlideId;
  }

  async function refetchRelevantResponses() {
    const slideId = currentPreviewSlideId();
    if (!slideId) return;
    try {
      const fetched = responsesForSlide(await listResponses(slideId), slideId);
      if (session?.presentation_id) timelineResponses = fetched;
      else slideResponses = fetched;
    } catch {
      // Keep existing in-memory responses if the refetch fails after reconnect.
    }
  }

  async function inspectDeckItem(itemId: string) {
    previewItemId = itemId;
    if (session?.presentation_id) {
      const item = (timeline?.items || []).find((i: any) => i.id === itemId);
      if (item?.slide?.id) await loadTimelineResponses(item.slide.id);
      else timelineResponses = [];
      return;
    }
    await loadResponses(itemId);
  }

  function openPresentation() {
    if (session?.unique_code) window.open('/screen/' + session.unique_code, '_blank', 'noopener,noreferrer');
  }

  async function startPresentation(itemId: string | null = null) {
    const targetId = itemId || previewItemId || timeline?.active_timeline_item_id || activeSlideId;
    if (targetId) {
      if (session?.presentation_id) await activatePresentationItem(targetId);
      else await activateSlide(targetId);
    }
    openPresentation();
    if (!session?.is_live) {
      await toggleLive();
    }
  }

  async function toggleLive() {
    session = await updateSession(sessionId, { is_live: !session.is_live });
    ws?.send('session_update', { is_live: session.is_live });
  }

  function notifyLocalPresentationScreen(action: "refresh" | "toggle_qr", commandId: string) {
    if (!session?.unique_code) return;
    try {
      localStorage.setItem(
        "rforum_screen_control_" + session.unique_code,
        JSON.stringify({ action, command_id: commandId, sentAt: Date.now() })
      );
    } catch {
      // The authenticated API delivery below remains available when storage is blocked.
    }
  }

  async function refreshPresentationScreen() {
    if (!session?.unique_code) return;
    console.log('[dashboard] sending screen_control refresh', { session: session.unique_code });
    screenCommandFlash = 'Refreshing screen';
    if (screenCommandTimer) clearTimeout(screenCommandTimer);
    const commandId = crypto.randomUUID();
    notifyLocalPresentationScreen("refresh", commandId);
    try {
      await sendScreenControl(sessionId, "refresh", commandId);
    } catch (error) {
      console.warn("[dashboard] HTTP screen refresh failed; falling back to WebSocket", error);
      ws?.send("screen_control", { action: "refresh", command_id: commandId });
    }
    screenCommandTimer = setTimeout(() => { screenCommandFlash = ''; }, 1500);
  }

  async function maximizePresentationQr() {
    if (!session?.unique_code) return;
    console.log('[dashboard] sending screen_control toggle_qr', { session: session.unique_code });
    screenCommandFlash = 'Maximizing QR';
    if (screenCommandTimer) clearTimeout(screenCommandTimer);
    const commandId = crypto.randomUUID();
    notifyLocalPresentationScreen("toggle_qr", commandId);
    try {
      await sendScreenControl(sessionId, "toggle_qr", commandId);
    } catch (error) {
      console.warn("[dashboard] HTTP QR toggle failed; falling back to WebSocket", error);
      ws?.send("screen_control", { action: "toggle_qr", command_id: commandId });
    }
    screenCommandTimer = setTimeout(() => { screenCommandFlash = ''; }, 1500);
  }

  function addSpeakerName() {
    const name = speakerNameInput.trim();
    if (!name) return;
    if (speakerNames.some((item) => item.toLowerCase() === name.toLowerCase())) {
      speakerNameInput = '';
      return;
    }
    speakerNames = [...speakerNames, name];
    speakerNameInput = '';
  }

  function removeSpeakerName(index: number) {
    speakerNames = speakerNames.filter((_, i) => i !== index);
  }

  async function saveModeratorSetup() {
    savingModeratorSetup = true;
    try {
      session = await updateSession(sessionId, {
        moderator_name: moderatorName.trim() || null,
        speaker_names: speakerNames
      });
      moderatorName = session.moderator_name || '';
      speakerNames = Array.isArray(session.speaker_names) ? [...session.speaker_names] : [];
    } finally {
      savingModeratorSetup = false;
    }
  }

  async function addSlide(type: string) {
    // Optimistic: add a temporary slide immediately
    const tempId = `temp-${Date.now()}`;
    const tempSlide = { id: tempId, type, order: slides.length, content_json: getDefaultContent(type), is_active: false, _temp: true };
    slides = [...slides, tempSlide];
    try {
      const slide = await createSlide(sessionId, {
        type,
        order: tempSlide.order,
        content_json: tempSlide.content_json
      });
      slides = slides.map((s) => s.id === tempId ? slide : s);
      await selectSlide(slide.id);
      pushCreatedSlideUndo(slide, slides.length - 1, 'Add slide');
    } catch {
      // Revert on failure
      slides = slides.filter((s) => s.id !== tempId);
    }
  }

  async function duplicateSlide(slideId: string) {
    const source = slides.find((s) => s.id === slideId);
    if (!source) return;
    const index = slides.indexOf(source);
    try {
      const slide = await createSlide(sessionId, {
        type: source.type,
        order: source.order ?? index,
        content_json: { ...source.content_json }
      });
      slides = [...slides.slice(0, index + 1), slide, ...slides.slice(index + 1)];
      await selectSlide(slide.id);
      pushCreatedSlideUndo(slide, index + 1, 'Duplicate slide');
    } catch (err) {
      saveError = err instanceof Error ? err.message : 'Duplicate failed';
      saveErrorTimeout && clearTimeout(saveErrorTimeout);
      saveErrorTimeout = setTimeout(() => { saveError = ''; }, 4000);
    }
  }

  /** Shared undo/redo entry for anything that CREATES a slide (Add, Duplicate).
   * Undo deletes it; redo re-creates it (under a new id, tracked via `box`
   * so a later undo-of-undo keeps deleting/recreating the right row) at the
   * same array position it was originally created at. */
  function pushCreatedSlideUndo(createdSlide: any, index: number, label: string) {
    const box: IdBox = { id: createdSlide.id };
    const snapshot = { type: createdSlide.type, order: createdSlide.order, content_json: { ...createdSlide.content_json } };
    undoManager.push({
      label,
      undo: async () => {
        await deleteSlide(sessionId, box.id);
        slides = slides.filter((s) => s.id !== box.id);
        if (activeSlideId === box.id) { activeSlideId = null; slideResponses = []; }
      },
      redo: async () => {
        const recreated = await createSlide(sessionId, snapshot);
        box.id = recreated.id;
        const insertAt = Math.min(index, slides.length);
        slides = [...slides.slice(0, insertAt), recreated, ...slides.slice(insertAt)];
        await selectSlide(recreated.id);
      }
    });
  }

  /** Shared undo/redo entry for DELETING a slide — undo re-creates it (new
   * id, tracked via `box`) at the same array position; redo deletes it again. */
  function pushDeletedSlideUndo(deletedSlide: any, index: number, label: string) {
    const box: IdBox = { id: deletedSlide.id };
    const snapshot = { type: deletedSlide.type, order: deletedSlide.order, content_json: { ...deletedSlide.content_json } };
    undoManager.push({
      label,
      undo: async () => {
        const recreated = await createSlide(sessionId, snapshot);
        box.id = recreated.id;
        const insertAt = Math.min(index, slides.length);
        slides = [...slides.slice(0, insertAt), recreated, ...slides.slice(insertAt)];
      },
      redo: async () => {
        await deleteSlide(sessionId, box.id);
        slides = slides.filter((s) => s.id !== box.id);
        if (activeSlideId === box.id) { activeSlideId = null; slideResponses = []; }
      }
    });
  }

  function getDefaultContent(type: string): object {
    switch (type) {
      case 'POLL':
        return { question: 'Your question?', options: ['Option A', 'Option B', 'Option C'] };
      case 'QNA':
        return { prompt: 'Ask me anything!' };
      case 'FEEDBACK':
        return { prompt: 'Share your thoughts...' };
      case 'CONTENT':
        return { title: 'New Slide', body: '<p>Start typing your content here.</p>', layout: 'title_content' };
      case 'WORD_CLOUD':
        return { prompt: 'What comes to mind?' };
      default:
        return {};
    }
  }

  async function selectSlide(slideId: string) {
    if (slideId !== activeSlideId && !confirmDiscardUnsavedChanges()) return;
    activeSlideId = slideId;
    previewItemId = slideId;
    void loadResponses(slideId);
  }

  async function activateSlide(slideId: string) {
    if (slideId !== activeSlideId && !confirmDiscardUnsavedChanges()) return;
    await updateSlide(sessionId, slideId, { is_active: true });
    slides = slides.map((s) => ({ ...s, is_active: s.id === slideId }));
    activeSlideId = slideId;
    previewItemId = slideId;
    void loadResponses(slideId);
  }

  function startEditing(slideId: string) {
    editingSlideId = slideId;
  }

  function stopEditing() {
    editingSlideId = null;
  }

  function flushLegacyEdit() {
    switch (activeType) {
      case 'POLL': savePollSlide(); break;
      case 'QNA': saveQnaSlide(); break;
      case 'FEEDBACK': saveFeedbackSlide(); break;
      case 'WORD_CLOUD': saveWordCloudSlide(); break;
      case 'CONTENT': saveContentSlide(); break;
    }
  }

  function isTypingTarget(el: EventTarget | null): boolean {
    const t = el as HTMLElement | null;
    return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
  }

  function flashSavedIndicator() {
    saveState = 'saved';
    if (saveStateTimeout) clearTimeout(saveStateTimeout);
    saveStateTimeout = setTimeout(() => { saveState = 'idle'; }, 1200);
  }

  /** Global shortcuts: Ctrl/Cmd+Z (undo), Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y (redo),
   * Ctrl/Cmd+S (flush the legacy editor's buffered form — the timeline editor's
   * InteractionView flushes its own). Delete/Backspace and Arrow navigation for
   * the legacy editor mirror what PresentationWorkspace already does for the
   * timeline editor. Native undo/redo inside a focused text field is left alone. */
  function handleGlobalKeydown(e: KeyboardEvent) {
    const mod = e.ctrlKey || e.metaKey;
    const key = e.key.toLowerCase();

    if (mod && key === 'z' && !e.shiftKey) {
      if (isTypingTarget(e.target)) return;
      e.preventDefault();
      performUndo();
      return;
    }
    if (mod && ((key === 'z' && e.shiftKey) || key === 'y')) {
      if (isTypingTarget(e.target)) return;
      e.preventDefault();
      performRedo();
      return;
    }
    if (mod && key === 's') {
      e.preventDefault();
      if (!session?.presentation_id) {
        if (editingSlideId) flushLegacyEdit();
        else flashSavedIndicator();
      }
      return;
    }
    if (mod || session?.presentation_id) return; // timeline mode owns its own Delete/Arrow handling
    if (isTypingTarget(e.target)) return;
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (editingSlideId || !activeSlideId) return;
      removeSlide(activeSlideId);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      goToContentSlide('prev');
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      goToContentSlide('next');
    }
  }

  async function removeSlide(slideId: string) {
    if (!confirm('Delete this slide?')) return;
    // Optimistic removal
    const removedSlide = slides.find((s) => s.id === slideId);
    const removedIndex = slides.indexOf(removedSlide);
    slides = slides.filter((s) => s.id !== slideId);
    if (activeSlideId === slideId) {
      activeSlideId = null;
      slideResponses = [];
    }
    try {
      await deleteSlide(sessionId, slideId);
      pushDeletedSlideUndo(removedSlide, removedIndex, 'Delete slide');
    } catch {
      // Revert on failure
      slides = [...slides.slice(0, removedIndex), removedSlide, ...slides.slice(removedIndex)];
    }
  }

  async function reorderSlideIds(orderedIds: string[]) {
    const byId = new Map(slides.map((s) => [s.id, s]));
    const newSlides = orderedIds.map((id) => byId.get(id)).filter(Boolean) as any[];
    slides = newSlides;
    const updates = newSlides.map((slide, idx) => ({ ...slide, order: idx }));
    for (let i = 0; i < updates.length; i++) {
      await updateSlide(sessionId, updates[i].id, { order: i });
    }
    slides = updates;
  }

  async function reorderSlides(draggedSlideId: string, newIndex: number) {
    const draggedSlide = slides.find((s) => s.id === draggedSlideId);
    if (!draggedSlide) return;

    const currentIndex = slides.indexOf(draggedSlide);
    if (currentIndex === newIndex) return;
    const previousOrderIds = slides.map((s) => s.id);

    // Optimistic reordering
    const newSlides = slides.filter((s) => s.id !== draggedSlideId);
    newSlides.splice(newIndex, 0, draggedSlide);
    slides = newSlides;
    const nextOrderIds = newSlides.map((s) => s.id);

    // Send updates to backend
    try {
      const updates = newSlides.map((slide, idx) => ({ ...slide, order: idx }));
      for (let i = 0; i < updates.length; i++) {
        await updateSlide(sessionId, updates[i].id, { order: i });
      }
      slides = updates;
      undoManager.push({
        label: 'Reorder slides',
        undo: async () => { await reorderSlideIds(previousOrderIds); },
        redo: async () => { await reorderSlideIds(nextOrderIds); }
      });
    } catch {
      // Revert on failure
      const originalIndex = currentIndex;
      const reverted = slides.filter((s) => s.id !== draggedSlideId);
      reverted.splice(originalIndex, 0, draggedSlide);
      slides = reverted;
    }
  }

  function moveSlide(slideId: string, delta: number) {
    const ids = slides.map((s) => s.id);
    const idx = ids.indexOf(slideId);
    const newIdx = idx + delta;
    if (idx === -1 || newIdx < 0 || newIdx >= ids.length) return;
    reorderSlides(slideId, newIdx);
  }

  function getActiveSlide() {
    return slides.find((s) => s.id === activeSlideId);
  }

  function getContentSlideIds() {
    return slides
      .filter((s) => s.type?.toUpperCase() === 'CONTENT')
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      .map((s) => s.id);
  }

  async function saveContentSlide() {
    const active = getActiveSlide();
    if (!active) return;
    const prevContentJson = { ...active.content_json };
    const nextContentJson = { ...active.content_json, title: contentTitle, body: contentBody };
    await withSaveState(async () => {
      const updated = await updateSlide(sessionId, active.id, { content_json: nextContentJson });
      slides = slides.map((s) => (s.id === active.id ? updated : s));
      ws?.send('slide_change', { slide_id: active.id, slide: updated, activation: false });
    });
    pushSlideContentUndo(active.id, prevContentJson, nextContentJson, 'Edit content slide');
    stopEditing();
  }


  async function uploadContentFile() {
    const active = getActiveSlide();
    if (!active || !contentFile || contentFile.length === 0) return;
    let updated;
    try {
      updated = await uploadSlideFile(sessionId, active.id, contentFile[0]);
    } catch {
      alert('Failed to upload file');
      return;
    }
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    contentFile = null;
    ws?.send('slide_change', { slide_id: active.id, slide: updated, activation: false });
  }

  async function changeContentPage(delta: number) {
    const active = getActiveSlide();
    if (!active) return;
    const current = active.content_json?.file_page || 1;
    const total = active.content_json?.total_pages;
    let next = Math.max(1, current + delta);
    if (total) next = Math.min(next, total);
    slides = slides.map((s) =>
      s.id === active.id
        ? { ...s, content_json: { ...s.content_json, file_page: next } }
        : s
    );
    try {
      const updated = await updateSlide(sessionId, active.id, {
        content_json: {
          ...active.content_json,
          file_page: next
        }
      });
      slides = slides.map((s) => (s.id === active.id ? updated : s));
      ws?.send('page_change', { slide_id: active.id, file_page: next, total_pages: updated.content_json?.total_pages });
    } catch {
      // Revert optimistic update on failure
      slides = slides.map((s) =>
        s.id === active.id
          ? { ...s, content_json: { ...s.content_json, file_page: current } }
          : s
      );
    }
  }

  function addPollOption() {
    pollOptions = [...pollOptions, ''];
  }

  function updatePollOption(index: number, value: string) {
    pollOptions = pollOptions.map((opt, i) => (i === index ? value : opt));
  }

  function removePollOption(index: number) {
    pollOptions = pollOptions.filter((_, i) => i !== index);
  }

  /** Shared undo/redo entry for a content_json edit on a legacy slide — the
   * id never changes for an update, so no IdBox is needed here. */
  function pushSlideContentUndo(slideId: string, prevContentJson: any, nextContentJson: any, label: string) {
    async function apply(contentJson: any) {
      const updated = await updateSlide(sessionId, slideId, { content_json: contentJson });
      slides = slides.map((s) => (s.id === slideId ? updated : s));
      ws?.send('slide_change', { slide_id: slideId, slide: updated, activation: false });
    }
    undoManager.push({
      label,
      undo: async () => { await apply(prevContentJson); },
      redo: async () => { await apply(nextContentJson); }
    });
  }

  async function savePollSlide() {
    const active = getActiveSlide();
    if (!active) return;
    const cleanedOptions = pollOptions.map((opt) => opt.trim()).filter(Boolean);
    if (!pollQuestion.trim() || cleanedOptions.length < 2) {
      alert('Provide a question and at least two options.');
      return;
    }
    const prevContentJson = { ...active.content_json };
    const nextContentJson = { ...active.content_json, question: pollQuestion.trim(), options: cleanedOptions };
    const updated = await updateSlide(sessionId, active.id, { content_json: nextContentJson });
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    ws?.send('slide_change', { slide_id: active.id, slide: updated, activation: false });
    pushSlideContentUndo(active.id, prevContentJson, nextContentJson, 'Edit poll');
  }

  async function saveQnaSlide() {
    const active = getActiveSlide();
    if (!active) return;
    const prevContentJson = { ...active.content_json };
    const nextContentJson = { ...active.content_json, prompt: qnaPrompt.trim() };
    const updated = await updateSlide(sessionId, active.id, { content_json: nextContentJson });
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    ws?.send('slide_change', { slide_id: active.id, slide: updated, activation: false });
    pushSlideContentUndo(active.id, prevContentJson, nextContentJson, 'Edit Q&A prompt');
  }

  async function saveFeedbackSlide() {
    const active = getActiveSlide();
    if (!active) return;
    const prevContentJson = { ...active.content_json };
    const nextContentJson = { ...active.content_json, prompt: feedbackPrompt.trim() };
    const updated = await updateSlide(sessionId, active.id, { content_json: nextContentJson });
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    ws?.send('slide_change', { slide_id: active.id, slide: updated, activation: false });
    pushSlideContentUndo(active.id, prevContentJson, nextContentJson, 'Edit feedback prompt');
  }

  async function saveWordCloudSlide() {
    const active = getActiveSlide();
    if (!active) return;
    const prevContentJson = { ...active.content_json };
    const nextContentJson = { ...active.content_json, prompt: wordCloudPrompt.trim() };
    const updated = await updateSlide(sessionId, active.id, { content_json: nextContentJson });
    slides = slides.map((s) => (s.id === active.id ? updated : s));
    ws?.send('slide_change', { slide_id: active.id, slide: updated, activation: false });
    pushSlideContentUndo(active.id, prevContentJson, nextContentJson, 'Edit word cloud prompt');
  }

  function getWordCloudData() {
    const freq: Record<string, number> = {};
    for (const r of slideResponses) {
      const word = r.value?.trim().toLowerCase();
      if (word) freq[word] = (freq[word] || 0) + 1;
    }
    const entries = Object.entries(freq).sort((a, b) => b[1] - a[1]);
    const maxCount = entries[0]?.[1] || 1;
    return entries.map(([word, count]) => ({
      word,
      count,
      size: Math.max(0.75, (count / maxCount) * 2.5)
    }));
  }

  async function goToContentSlide(direction: 'next' | 'prev') {
    const ordered = [...slides].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    const ids = ordered.map((s) => s.id);
    if (ids.length === 0) return;
    const currentIndex = ids.indexOf(activeSlideId || '');
    const base = currentIndex === -1 ? 0 : currentIndex;
    const nextIndex = direction === 'next'
      ? Math.min(base + 1, ids.length - 1)
      : Math.max(base - 1, 0);
    const nextId = ids[nextIndex];
    if (nextId && nextId !== activeSlideId) {
      await selectSlide(nextId);
    }
  }

  function getPollResults(slide: any) {
    const options: string[] = slide.content_json?.options || [];
    const counts: Record<string, number> = {};
    options.forEach((opt) => (counts[opt] = 0));
    slideResponses.forEach((r) => {
      if (counts[r.value] !== undefined) counts[r.value]++;
    });
    const total = slideResponses.length || 1;
    return options.map((opt) => ({
      label: opt,
      count: counts[opt],
      percent: Math.round((counts[opt] / total) * 100)
    }));
  }

  // ── Presentation Timeline handlers ────────────────────
  async function loadPresentationData() {
    const data = await getSessionPresentation(sessionId);
    presentation = data.presentation;
    timeline = data.timeline;
    const activeItem = (timeline?.items || []).find((i: any) => i.id === timeline?.active_timeline_item_id);
    previewItemId = activeItem?.id || timeline?.items?.[0]?.id || previewItemId;
    if (activeItem?.slide) {
      await loadTimelineResponses(activeItem.slide.id);
    } else {
      const preview = (timeline?.items || []).find((i: any) => i.id === previewItemId);
      if (preview?.slide) await loadTimelineResponses(preview.slide.id);
      else timelineResponses = [];
    }
  }

  async function loadTimelineResponses(slideId: string) {
    timelineResponses = responsesForSlide(await listResponses(slideId), slideId);
  }

  async function handleUploadPresentation(file: File) {
    const result = await uploadPresentation(sessionId, file);
    presentation = result.presentation;
    timeline = result.timeline;
    return result;
  }

  function handleUploadDone(result: any) {
    session = { ...session, presentation_id: result.presentation.id };
    requestNavigation(`/dashboard/${sessionId}`);
  }

  async function handleAttachExistingPresentation(presentationId: string) {
    await withSaveState(async () => {
      const result = await attachPresentation(sessionId, presentationId);
      presentation = result.presentation;
      timeline = result.timeline;
      session = { ...session, presentation_id: presentation.id };
      requestNavigation(`/dashboard/${sessionId}`);
    });
  }

  async function handleDetachPresentation() {
    // API call only — deliberately does not touch session/presentation/timeline
    // state, so the Details Panel can stay open and re-fetch in place.
    await detachPresentation(sessionId);
  }

  async function handleDeletePresentation(presentationId: string) {
    await deletePresentation(presentationId);
  }

  function handlePresentationDetailsClosedAfterChange() {
    // A detach or delete happened while the Details Panel was open — now that
    // it's closed, fall back to the empty state (Upload / Choose Existing).
    session = { ...session, presentation_id: null };
    presentation = null;
    timeline = null;
    timelineResponses = [];
  }

  async function handleReplacePresentation(file: File) {
    await withSaveState(async () => {
      const result = await replacePresentation(sessionId, file);
      presentation = result.presentation;
      timeline = result.timeline;
      timelineResponses = [];
    });
  }

  async function handleRegeneratePresentation() {
    await withSaveState(async () => {
      presentation = await regeneratePresentation(sessionId);
    });
  }

  async function activatePresentationItem(itemId: string) {
    if (itemId !== timeline?.active_timeline_item_id && !confirmDiscardUnsavedChanges()) return;
    const item = await activateTimelineItem(sessionId, itemId);
    timeline = {
      ...timeline,
      active_timeline_item_id: itemId,
      items: timeline.items.map((i: any) => (i.id === item.id ? item : i))
    };
    previewItemId = itemId;
    if (item.slide) {
      await loadTimelineResponses(item.slide.id);
    } else {
      timelineResponses = [];
    }
  }

  function navigateTimeline(direction: 'prev' | 'next') {
    const ids = [...(timeline?.items || [])].sort((a: any, b: any) => a.order - b.order).map((i: any) => i.id);
    if (ids.length === 0) return;
    const currentIndex = ids.indexOf(timeline?.active_timeline_item_id);
    const base = currentIndex === -1 ? 0 : currentIndex;
    const nextIndex = direction === 'next' ? Math.min(base + 1, ids.length - 1) : Math.max(base - 1, 0);
    const nextId = ids[nextIndex];
    if (nextId && nextId !== timeline?.active_timeline_item_id) {
      activatePresentationItem(nextId);
    }
  }

  /** Shared undo/redo entry for CREATING a timeline item (insert, duplicate).
   * Undo deletes it; redo re-inserts at the same logical position (tracked
   * via `box` so a later undo-of-undo keeps deleting/recreating the right row). */
  function pushCreatedTimelineItemUndo(createdItem: any, position: number, label: string) {
    const box: IdBox = { id: createdItem.id };
    const snapshot = { item_type: createdItem.item_type, content_json: { ...(createdItem.slide?.content_json || {}) } };
    undoManager.push({
      label,
      undo: async () => {
        await withSaveState(async () => {
          await deleteTimelineItem(sessionId, box.id);
          await loadPresentationData();
        });
      },
      redo: async () => {
        await withSaveState(async () => {
          const created = await insertTimelineItem(sessionId, snapshot.item_type, position, snapshot.content_json);
          box.id = created.id;
          await loadPresentationData();
        });
      }
    });
  }

  async function handleInsertTimelineItem(itemType: string, position: number) {
    await withSaveState(async () => {
      const created = await insertTimelineItem(sessionId, itemType, position);
      await loadPresentationData();
      pushCreatedTimelineItemUndo(created, position, 'Insert interaction');
    });
  }

  async function handleUpdateTimelineItemContent(itemId: string, contentJson: Record<string, unknown>) {
    const item = (timeline?.items || []).find((i: any) => i.id === itemId);
    const prevContentJson = { ...(item?.slide?.content_json || {}) };
    async function apply(cj: Record<string, unknown>) {
      await withSaveState(async () => {
        const updated = await updateTimelineItem(sessionId, itemId, cj);
        timeline = { ...timeline, items: timeline.items.map((i: any) => (i.id === updated.id ? updated : i)) };
      });
    }
    await apply(contentJson);
    undoManager.push({
      label: 'Edit interaction',
      undo: async () => { await apply(prevContentJson); },
      redo: async () => { await apply(contentJson); }
    });
  }

  async function handleDeleteTimelineItem(itemId: string) {
    // Confirmation is now handled inline in TimelineSidebar (Yes/Cancel row) —
    // by the time this fires the moderator has already confirmed.
    const item = (timeline?.items || []).find((i: any) => i.id === itemId);
    if (!item) return;
    const snapshot = { item_type: item.item_type, order: item.order, content_json: { ...(item.slide?.content_json || {}) } };
    const box: IdBox = { id: itemId };
    await withSaveState(async () => {
      await deleteTimelineItem(sessionId, box.id);
      await loadPresentationData();
    });
    undoManager.push({
      label: 'Delete interaction',
      undo: async () => {
        await withSaveState(async () => {
          const created = await insertTimelineItem(sessionId, snapshot.item_type, snapshot.order, snapshot.content_json);
          box.id = created.id;
          await loadPresentationData();
        });
      },
      redo: async () => {
        await withSaveState(async () => {
          await deleteTimelineItem(sessionId, box.id);
          await loadPresentationData();
        });
      }
    });
  }

  async function handleDuplicateTimelineItem(itemId: string) {
    const item = (timeline?.items || []).find((i: any) => i.id === itemId);
    if (!item || item.item_type === 'PAGE' || !item.slide) return;
    const position = item.order + 1;
    await withSaveState(async () => {
      const created = await insertTimelineItem(sessionId, item.item_type, position, item.slide.content_json || {});
      await loadPresentationData();
      pushCreatedTimelineItemUndo(created, position, 'Duplicate interaction');
    });
  }

  async function handleReorderTimelineItems(itemIds: string[]) {
    const previousOrderIds = [...(timeline?.items || [])].sort((a: any, b: any) => a.order - b.order).map((i: any) => i.id);
    await withSaveState(async () => {
      timeline = await reorderTimelineItems(sessionId, itemIds);
    });
    undoManager.push({
      label: 'Reorder timeline',
      undo: async () => { await withSaveState(async () => { timeline = await reorderTimelineItems(sessionId, previousOrderIds); }); },
      redo: async () => { await withSaveState(async () => { timeline = await reorderTimelineItems(sessionId, itemIds); }); }
    });
  }

</script>

<svelte:head>
  <title>Manage Session – Rforum</title>
</svelte:head>

<svelte:window onkeydown={handleGlobalKeydown} onbeforeunload={handleBeforeUnload} />

<div>
  <!-- Sub-header with session actions -->
  <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5 px-4 sm:px-6 lg:px-8 py-2.5 border-b border-surface-200 backdrop-blur-sm">
      <button
        onclick={() => requestNavigation('/dashboard')}
      class="text-sm font-medium text-surface-500 hover:text-surface-100 transition"
    >&larr; Back to dashboard</button>
    <div class="flex items-center justify-between sm:justify-end gap-3 w-full sm:w-auto">
      <span class="sr-only" role="status" aria-live="polite">{undoRedoLabel}</span>
      {#if hasUnsavedChanges}
        <span class="text-xs text-amber-500 font-medium" role="status">Unsaved changes</span>
      {/if}
      {#if canUndo || canRedo}
        <div class="flex items-center rounded-lg border border-surface-200 dark:border-surface-800 overflow-hidden text-xs font-medium">
          <button
            onclick={performUndo}
            disabled={!canUndo || undoRedoBusy}
            aria-label="Undo"
            title="Undo (Ctrl+Z)"
            class="px-2.5 py-1.5 text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800 transition disabled:opacity-30 disabled:pointer-events-none"
          >↶ Undo</button>
          <button
            onclick={performRedo}
            disabled={!canRedo || undoRedoBusy}
            aria-label="Redo"
            title="Redo (Ctrl+Shift+Z)"
            class="px-2.5 py-1.5 border-l border-surface-200 dark:border-surface-800 text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800 transition disabled:opacity-30 disabled:pointer-events-none"
          >↷ Redo</button>
        </div>
      {/if}
      {#if editorMode}<button class="btn-secondary" onclick={() => requestNavigation(`/dashboard/${sessionId}`)}>Back to deck</button>{/if}
      <span class="text-sm text-surface-400 font-mono">{session?.unique_code}</span>
    </div>
  </div>

  <main class="flex-1 px-4 sm:px-6 py-6 sm:py-7">
    {#if saveError}
      <div class="mb-4 px-4 py-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-500 flex items-center justify-between gap-3" role="alert">
        <span>{saveError}</span>
        <button class="text-red-500/70 hover:text-red-500" onclick={() => (saveError = '')} aria-label="Dismiss">&times;</button>
      </div>
    {/if}
    {#if loading}
      <div class="animate-pulse space-y-5" aria-busy="true" aria-label="Loading session">
        <div class="grid grid-cols-12 gap-5">
          <div class="col-span-12 lg:col-span-3 space-y-4">
            <div class="h-32 rounded-2xl bg-surface-200 dark:bg-surface-800"></div>
            <div class="h-40 rounded-2xl bg-surface-200 dark:bg-surface-800"></div>
          </div>
          <div class="col-span-12 lg:col-span-9">
            <div class="h-96 rounded-2xl bg-surface-200 dark:bg-surface-800"></div>
          </div>
        </div>
      </div>
    {:else if errorMessage}
      <div class="card text-center text-red-500 py-10 px-6">{errorMessage}</div>
    {:else if !editorMode}
      <DeckView
        {session}
        {presentation}
        {timeline}
        {slides}
        {activeSlideId}
        responses={session?.presentation_id ? timelineResponses : slideResponses}
        {wsStatus}
        onSelect={inspectDeckItem}
        onEdit={() => requestNavigation(`/dashboard/${sessionId}?mode=editor`)}
        onPresent={startPresentation}
        onToggleLive={toggleLive}
        onRefreshPresentation={refreshPresentationScreen}
        onMaximizeQr={maximizePresentationQr}
      />
    {:else if session?.presentation_id}
        <PresentationWorkspace
          {session}
          {presentation}
          {timeline}
          responses={timelineResponses}
          {wsStatus}
          {saveState}
          {canUndo}
          {canRedo}
          onToggleLive={toggleLive}
          onActivateItem={activatePresentationItem}
          onNavigate={navigateTimeline}
          onInsertItem={handleInsertTimelineItem}
          onUpdateItemContent={handleUpdateTimelineItemContent}
          onDeleteItem={handleDeleteTimelineItem}
          onDuplicateItem={handleDuplicateTimelineItem}
          onReorderItems={handleReorderTimelineItems}
          onReplace={handleReplacePresentation}
          onRegenerate={handleRegeneratePresentation}
          onDetach={handleDetachPresentation}
          onDeletePresentation={handleDeletePresentation}
          onDetailsClosedAfterChange={handlePresentationDetailsClosedAfterChange}
          onDirtyChange={(dirty) => (timelineFormDirty = dirty)}
          onSelectItem={inspectDeckItem}
          onUndo={performUndo}
          onRedo={performRedo}
        />
    {:else if slides.length > 0 || startNativeEditor}
        <div class="h-[calc(100vh-140px)] min-h-[600px] w-full">
          <DeckEditor
            {sessionId}
            {slides}
            {activeSlideId}
            {saveState}
            {canUndo}
            {canRedo}
            onSaveReady={(save) => (deckEditorSave = save)}
            onDirtyChange={(dirty) => (deckEditorDirty = dirty)}
            onSelectSlide={(id) => selectSlide(id)}
            onCreateSlide={async (type, layout) => {
              try {
                const defaultContent = getDefaultContent(type);
                const finalContent = {
                  ...defaultContent,
                  layout: layout || (type === 'CONTENT' ? 'title_content' : 'interactive')
                };
                await withSaveState(async () => {
                  const newSlide = await createSlide(sessionId, {
                    type,
                    order: slides.length,
                    content_json: finalContent
                  });
                  slides = [...slides, newSlide];
                  await selectSlide(newSlide.id);
                  pushCreatedSlideUndo(newSlide, slides.length - 1, 'Add slide');
                });
              } catch (err) {
                console.error('Failed to create slide:', err);
              }
            }}
            onUpdateSlideContent={async (slideId, contentJson) => {
              try {
                await withSaveState(async () => {
                  const updated = await updateSlide(sessionId, slideId, { content_json: contentJson });
                  slides = slides.map((s) => (s.id === slideId ? updated : s));
                  ws?.send('slide_change', { slide_id: slideId, slide: updated, activation: false });
                });
              } catch (err) {
                console.error('Failed to update slide content:', err);
              }
            }}
            onDeleteSlide={(slideId) => removeSlide(slideId)}
            onDuplicateSlide={(slideId) => duplicateSlide(slideId)}
            onReorderSlides={(slideIds) => reorderSlideIds(slideIds)}
            onUploadFile={async (slideId, file) => {
              try {
                await withSaveState(async () => {
                  const updated = await uploadSlideFile(sessionId, slideId, file);
                  slides = slides.map((s) => (s.id === slideId ? { ...s, ...updated } : s));
                });
              } catch (err) {
                console.error('Failed to upload file:', err);
              }
            }}
            onUndo={performUndo}
            onRedo={performRedo}
          />
        </div>
    {:else}
        <PresentationEmptyState
          eventId={session?.event_id ?? null}
          onUpload={handleUploadPresentation}
          onUploadDone={handleUploadDone}
          onAttach={handleAttachExistingPresentation}
        />
        <div class="mt-4 text-center">
          <button class="btn-secondary" type="button" onclick={() => (startNativeEditor = true)}>Create slides</button>
        </div>
    {/if}

    <Modal open={leavePromptOpen} onClose={handleLeavePromptCancel} ariaLabel={leavePromptTitle} maxWidth="max-w-md">
      <div class="p-6">
        <h2 class="text-lg font-heading font-bold text-slate-900 dark:text-white">{leavePromptTitle}</h2>
        <p class="mt-2 text-sm text-slate-500 dark:text-slate-400">{leavePromptDescription}</p>
        <div class="mt-5 flex flex-col gap-2 sm:flex-row">
          <button class="btn-primary flex-1" onclick={handleLeavePromptSave}>Save</button>
          <button class="btn-secondary flex-1" onclick={handleLeavePromptDiscard}>Discard</button>
          <button class="btn-secondary flex-1" onclick={handleLeavePromptCancel}>Cancel</button>
        </div>
      </div>
    </Modal>

    {#if screenCommandFlash}
      <div class="fixed bottom-4 right-4 z-50 rounded-xl border border-brand-200 bg-white px-4 py-2 text-sm font-medium text-brand-700 shadow-lg dark:border-brand-500/30 dark:bg-slate-950 dark:text-brand-300">
        {screenCommandFlash}
      </div>
    {/if}

    <!-- Moderator Setup -->
    {#if !loading && !errorMessage && editorMode}
      <div class="card mt-6 mx-0">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <Users class="w-4 h-4 text-brand-500" />
            <h2 class="font-heading font-semibold text-sm uppercase tracking-widest text-surface-500">Moderator Setup</h2>
          </div>
        </div>
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="block sm:col-span-2">
            <span class="text-xs text-surface-500 uppercase tracking-widest">Moderator Name</span>
            <input
              class="input-field mt-1"
              type="text"
              bind:value={moderatorName}
              placeholder="Who is moderating this session?"
            />
          </label>
          <label class="block sm:col-span-2">
            <span class="text-xs text-surface-500 uppercase tracking-widest">Guest Speakers / Panelists</span>
            <div class="flex gap-2 mt-1">
              <input
                class="input-field"
                type="text"
                bind:value={speakerNameInput}
                onkeydown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    addSpeakerName();
                  }
                }}
                placeholder="Add speaker name"
              />
              <button type="button" class="btn-secondary" onclick={addSpeakerName}>Add</button>
            </div>
          </label>
          {#if speakerNames.length > 0}
            <div class="sm:col-span-2 flex flex-wrap gap-2">
              {#each speakerNames as speaker, index (speaker + index)}
                <span class="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-surface-200 text-xs">
                  <UserRound class="w-3 h-3" />
                  {speaker}
                  <button type="button" class="text-surface-500 hover:text-danger" onclick={() => removeSpeakerName(index)}>x</button>
                </span>
              {/each}
            </div>
          {/if}
          <div class="sm:col-span-2">
            <button type="button" class="btn-primary" onclick={saveModeratorSetup} disabled={savingModeratorSetup}>
              {savingModeratorSetup ? 'Saving...' : 'Save moderator setup'}
            </button>
          </div>
        </div>
      </div>
    {/if}

    <!-- Moderator Notes -->
    {#if !loading && !errorMessage}
      <div class="card mt-6 mx-0">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <NotebookPen class="w-4 h-4 text-brand-500" />
            <h2 class="font-heading font-semibold text-sm uppercase tracking-widest text-surface-500">Moderator Notes</h2>
          </div>
          <span class="text-xs transition-opacity duration-300 {notesSavedFlash ? 'text-emerald-500 opacity-100' : 'opacity-0'}">Saved</span>
        </div>
        <textarea
          class="input-field w-full resize-y text-sm"
          rows="5"
          placeholder="Jot down notes for this session — talking points, reminders, cues… Only you can see this."
          value={moderatorNotes}
          oninput={handleNotesInput}
        ></textarea>
      </div>
    {/if}
  </main>
</div>
