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

  const toneClasses: Record<string, { icon: string; button: string }> = {
    danger: { icon: 'bg-danger/10 text-danger', button: 'bg-danger text-white hover:opacity-90' },
    warning: { icon: 'bg-warning/10 text-warning', button: 'bg-warning text-white hover:opacity-90' },
    info: { icon: 'bg-brand-500/10 text-brand-500', button: 'bg-brand-600 text-white hover:opacity-90' }
  };
</script>

<Modal {open} onClose={onCancel} maxWidth="max-w-sm" ariaLabel={title}>
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
        class="flex-1 px-4 py-2 rounded-xl font-semibold text-sm transition disabled:opacity-40 {toneClasses[tone].button}"
      >
        {loading ? 'Working…' : confirmLabel}
      </button>
    </div>
  </div>
</Modal>
