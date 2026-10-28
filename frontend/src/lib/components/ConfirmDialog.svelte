<script lang="ts">
  import Modal from './Modal.svelte';
  import { AlertTriangle, Info } from 'lucide-svelte';
  import type { Snippet } from 'svelte';

  let {
    open,
    tone = 'danger',
    title,
    description,
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
    loading = false,
    onConfirm,
    onCancel,
    children
  }: {
    open: boolean;
    tone?: 'danger' | 'warning' | 'info';
    title: string;
    description: string;
    confirmLabel?: string;
    cancelLabel?: string;
    loading?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
    children?: Snippet;
  } = $props();

  // Button fills keep ≥ 4.5:1 with their label: white on the raw `danger`
  // (red-500, ~3.8:1) and `warning` (amber-500, ~2.1:1) tokens did not, so the
  // danger button uses red-600 and the warning button a dark label on amber.
  const toneClasses: Record<string, { icon: string; button: string }> = {
    danger: { icon: 'bg-danger/10 text-red-600 dark:text-red-400', button: 'bg-red-600 text-white enabled:hover:bg-red-700' },
    warning: { icon: 'bg-warning/10 text-amber-600 dark:text-amber-400', button: 'bg-amber-400 text-amber-950 enabled:hover:bg-amber-300' },
    info: { icon: 'bg-brand-500/10 text-brand-600 dark:text-brand-400', button: 'bg-brand-600 text-white enabled:hover:bg-brand-700' }
  };

  // While the action is in flight, Escape / backdrop click must not dismiss
  // the dialog any more than the (disabled) Cancel button can.
  function handleClose() {
    if (!loading) onCancel();
  }
</script>

<Modal {open} onClose={handleClose} maxWidth="max-w-sm" ariaLabel={title} showCloseButton={false}>
  <div class="p-6">
    <div class="flex items-center gap-3 mb-4">
      <div class="w-10 h-10 flex items-center justify-center rounded-xl flex-shrink-0 {toneClasses[tone].icon}">
        {#if tone === 'info'}
          <Info class="w-5 h-5" />
        {:else}
          <AlertTriangle class="w-5 h-5" />
        {/if}
      </div>
      <div>
        <h2 class="text-base font-heading font-bold">{title}</h2>
        <p class="text-xs text-surface-500">{description}</p>
      </div>
    </div>

    {#if children}
      <div class="mb-4">
        {@render children()}
      </div>
    {/if}

    <div class="flex gap-3">
      <button onclick={onCancel} class="btn-secondary flex-1 text-sm" disabled={loading}>{cancelLabel}</button>
      <button
        onclick={onConfirm}
        disabled={loading}
        aria-busy={loading}
        class="flex-1 px-4 py-2 rounded-xl font-semibold text-sm transition-colors disabled:opacity-60 disabled:cursor-wait {toneClasses[tone].button}"
      >
        {loading ? 'Working…' : confirmLabel}
      </button>
    </div>
  </div>
</Modal>
