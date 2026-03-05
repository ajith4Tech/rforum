<script lang="ts">
  import { Wifi, WifiOff, Loader2 } from 'lucide-svelte';
  import type { ConnectionStatus } from '$lib/ws';

  let {
    status = 'disconnected' as ConnectionStatus
  }: {
    status: ConnectionStatus;
  } = $props();

  const config: Record<ConnectionStatus, { label: string; color: string; icon: any }> = {
    connected: { label: 'Connected', color: 'text-emerald-500', icon: Wifi },
    disconnected: { label: 'Disconnected', color: 'text-slate-400', icon: WifiOff },
    reconnecting: { label: 'Reconnecting', color: 'text-amber-500', icon: Loader2 }
  };

  const current = $derived(config[status]);
</script>

<div class="flex items-center gap-1.5" title={current.label}>
  <span class="relative flex h-2 w-2">
    {#if status === 'connected'}
      <span class="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping"></span>
    {/if}
    <span class="relative inline-flex h-2 w-2 rounded-full {status === 'connected' ? 'bg-emerald-500' : status === 'reconnecting' ? 'bg-amber-500' : 'bg-slate-400'}"></span>
  </span>
  <span class="text-xs font-medium {current.color}">{current.label}</span>
</div>
