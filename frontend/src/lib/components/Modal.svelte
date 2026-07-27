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
  let previouslyFocused: HTMLElement | null = null;

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
    } else if (e.key === 'Tab') {
      // Simple focus trap: cycle within the dialog's focusable elements.
      const focusable = dialogEl?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
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
    const focusTarget = dialogEl?.querySelector<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    (focusTarget ?? dialogEl)?.focus();

    return () => {
      previouslyFocused?.focus();
    };
  });
</script>

{#if open}
  <div
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
          class="absolute top-3 right-3 p-1.5 rounded-lg text-surface-400 hover:text-surface-200 hover:bg-surface-800/60 transition z-10"
          aria-label="Close"
        >
          <X class="w-4 h-4" />
        </button>
      {/if}
      {@render children()}
    </div>
  </div>
{/if}
