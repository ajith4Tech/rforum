<script lang="ts">
  import { Wifi, WifiOff, Loader2 } from 'lucide-svelte';
  import type { ConnectionStatus } from '$lib/ws';

  let {
    status = 'disconnected' as ConnectionStatus
  }: {
    status: ConnectionStatus;
  } = $props();

  const config: Record<ConnectionStatus, { label: string; color: string; icon: any }> = {
    connected: { label: 'Connected', color: 'text-emerald-700 dark:text-emerald-400', icon: Wifi },
    disconnected: { label: 'Disconnected', color: 'text-surface-600 dark:text-surface-400', icon: WifiOff },
    reconnecting: { label: 'Reconnecting', color: 'text-amber-700 dark:text-amber-400', icon: Loader2 },
    offline: { label: 'Offline', color: 'text-red-600 dark:text-red-400', icon: WifiOff }
  };

  const current = $derived(config[status]);
</script>

<div class="flex items-center gap-1.5" title={current.label} role="status">
  <span class="relative flex h-2 w-2" aria-hidden="true">
    {#if status === 'connected'}
      <span class="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping"></span>
    {/if}
    <span class="relative inline-flex h-2 w-2 rounded-full {status === 'connected' ? 'bg-emerald-500' : status === 'reconnecting' ? 'bg-amber-500' : status === 'offline' ? 'bg-red-500' : 'bg-surface-400'}"></span>
  </span>
  <span class="text-xs font-medium {current.color}">{current.label}</span>
</div>
