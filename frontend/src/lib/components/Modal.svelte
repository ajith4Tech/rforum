<script module lang="ts">
  /** True while any modal dialog is open — page-level keyboard shortcuts
   * (slide navigation, delete, undo) must not act behind it. */
  export function isModalOpen(): boolean {
    return typeof document !== 'undefined' && document.querySelector('[role="dialog"][aria-modal="true"]') !== null;
  }
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';
  import { X } from 'lucide-svelte';

  let {
    open,
    onClose,
    ariaLabel,
    labelledBy,
    maxWidth = 'max-w-lg',
    showCloseButton = true,
    children
  }: {
    open: boolean;
    onClose: () => void;
    ariaLabel?: string;
    labelledBy?: string;
    maxWidth?: string;
    showCloseButton?: boolean;
    children: Snippet;
  } = $props();

  let dialogEl: HTMLDivElement | null = $state(null);
  let overlayEl: HTMLDivElement | null = $state(null);
  let previouslyFocused: HTMLElement | null = null;

  const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

  // While an element is fullscreen (e.g. the presentation workspace) the
  // browser paints only that element's subtree, so a dialog rendered anywhere
  // else would be invisible yet still hold focus. While open, the overlay is
  // moved into the fullscreen element, and back to where it was rendered when
  // fullscreen ends. It is the {#if open} block's only node, so Svelte still
  // removes it correctly on close wherever it currently sits.
  let homeParent: Node | null = null;
  let homeNextSibling: Node | null = null;
  function placeOverlay() {
    const el = overlayEl;
    if (!el) return;
    const fullscreen = document.fullscreenElement;
    if (fullscreen && !fullscreen.contains(el)) {
      if (!homeParent) {
        homeParent = el.parentNode;
        homeNextSibling = el.nextSibling;
      }
      fullscreen.appendChild(el);
    } else if (!fullscreen && homeParent && el.parentNode !== homeParent) {
      homeParent.insertBefore(el, homeNextSibling?.parentNode === homeParent ? homeNextSibling : null);
      homeParent = null;
      homeNextSibling = null;
    }
  }

  function focusIntoDialog() {
    const focusTarget = dialogEl?.querySelector<HTMLElement>(FOCUSABLE);
    (focusTarget ?? dialogEl)?.focus();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
    } else if (e.key === 'Tab') {
      // Simple focus trap: cycle within the dialog's focusable elements.
      const focusable = dialogEl?.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      // The dialog container itself (tabindex=-1) holds focus when it has no
      // focusable child or after a click on static content: Shift+Tab from it
      // would otherwise leave the dialog.
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === dialogEl)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  $effect(() => {
    if (!open) return;
    previouslyFocused = document.activeElement as HTMLElement | null;
    // Move first: re-parenting a focused element would drop its focus.
    placeOverlay();
    focusIntoDialog();

    function onFullscreenChange() {
      placeOverlay();
      if (!dialogEl?.contains(document.activeElement)) focusIntoDialog();
    }
    document.addEventListener('fullscreenchange', onFullscreenChange);

    return () => {
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      homeParent = null;
      homeNextSibling = null;
      previouslyFocused?.focus();
    };
  });
</script>

{#if open}
  <div
    bind:this={overlayEl}
    class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50"
    onclick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    onkeydown={handleKeydown}
    role="presentation"
  >
    <div
      bind:this={dialogEl}
      class="relative card w-full {maxWidth} shadow-2xl animate-fade-in max-h-[90vh] overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      aria-labelledby={labelledBy}
      tabindex="-1"
    >
      {#if showCloseButton}
        <button
          onclick={onClose}
          class="absolute top-3 right-3 p-1.5 rounded-lg text-surface-500 hover:text-surface-900 hover:bg-surface-100 dark:text-surface-400 dark:hover:text-surface-100 dark:hover:bg-surface-800 transition-colors z-10"
          aria-label="Close"
        >
          <X class="w-4 h-4" />
        </button>
      {/if}
      {@render children()}
    </div>
  </div>
{/if}
