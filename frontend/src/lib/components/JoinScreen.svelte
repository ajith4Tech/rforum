<script lang="ts">
  import { Orbit } from 'lucide-svelte';
  import QRCode from './QRCode.svelte';
  import { theme } from '$lib/theme';

  interface Props {
    sessionCode?: string;
    sessionTitle?: string;
    joinUrl?: string;
    onStartSession?: (() => void) | undefined;
    isStarting?: boolean;
    isModerator?: boolean;
  }

  let { sessionCode = '', sessionTitle = '', joinUrl = '', onStartSession = undefined, isStarting = false, isModerator = false }: Props = $props();
</script>

<div class="min-h-screen flex flex-col font-sans overflow-hidden {$theme === 'dark' ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-900'}">
  <header class="flex items-center justify-center px-4 py-4 flex-shrink-0 border-b {$theme === 'dark' ? 'border-slate-800' : 'border-slate-200'}">
    <div class="flex items-center gap-2.5">
      <Orbit class="w-6 md:w-7 h-6 md:h-7 text-brand-500" />
      <span class="font-heading font-bold text-lg md:text-xl tracking-wide {$theme === 'dark' ? 'text-slate-200' : 'text-slate-800'}">Rforum</span>
    </div>
  </header>

  <main class="flex-1 flex flex-col items-center justify-center px-4 md:px-8 py-6 md:py-10 gap-8 md:gap-10">
    <img src="/logo-mascot.webp" alt="Tech Good Community" class="w-16 h-auto md:w-20 opacity-80" />

    <div class="flex flex-col items-center gap-6 md:gap-8 max-w-2xl w-full">
      <div class="text-center space-y-2 md:space-y-3">
        <h1 class="text-3xl md:text-4xl lg:text-5xl font-heading font-bold leading-tight {$theme === 'dark' ? 'text-white' : 'text-slate-900'}">
          {sessionTitle || 'Session Waiting to Start'}
        </h1>
        <p class="text-lg md:text-xl {$theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}">
          Get ready for an interactive session
        </p>
      </div>

      <div class="flex flex-col items-center gap-4 md:gap-6 w-full">
        <div class="p-8 md:p-12 rounded-3xl border {$theme === 'dark' ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200 shadow-sm'}">
          <div class="bg-white p-6 md:p-8 rounded-2xl">
            <QRCode data={joinUrl} size={300} errorCorrectionLevel="H" />
          </div>
        </div>

        <div class="text-center space-y-2 {$theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}">
          <p class="font-semibold {$theme === 'dark' ? 'text-slate-200' : 'text-slate-800'}">Scan to join now</p>
          <p class="text-sm md:text-base">Use your phone camera to scan the QR code</p>
        </div>
      </div>

      <div class="w-full text-center space-y-3">
        <p class="text-xs md:text-sm uppercase tracking-widest {$theme === 'dark' ? 'text-slate-500' : 'text-slate-400'}">Session Code</p>
        <div class="font-mono text-4xl md:text-5xl font-bold tracking-[0.25em] text-brand-500">
          {sessionCode}
        </div>
      </div>

      <div class="w-full border-t pt-6 md:pt-8 {$theme === 'dark' ? 'border-slate-800' : 'border-slate-200'}">
        <p class="text-xs md:text-sm uppercase tracking-widest mb-3 text-center {$theme === 'dark' ? 'text-slate-500' : 'text-slate-400'}">Can't scan?</p>
        <div class="rounded-xl p-4 md:p-6 text-center space-y-2 border {$theme === 'dark' ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}">
          <p class="text-sm md:text-base {$theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}">Visit on your phone:</p>
          <p class="font-mono text-sm md:text-base text-brand-500 break-all">{joinUrl}</p>
        </div>
      </div>

      {#if isModerator && onStartSession}
        <button
          onclick={onStartSession}
          disabled={isStarting}
          class="w-full mt-2 md:mt-4 px-6 md:px-8 py-3 md:py-4 bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/50 text-white font-semibold rounded-xl transition-all duration-200 text-base md:text-lg"
        >
          {isStarting ? 'Starting Session...' : 'Start Session'}
        </button>
      {/if}
    </div>
  </main>

  <footer class="flex items-center justify-center px-4 py-3 border-t flex-shrink-0 text-xs md:text-sm {$theme === 'dark' ? 'border-slate-800 text-slate-500' : 'border-slate-200 text-slate-400'}">
    <span>Rforum@2026</span>
  </footer>
</div>
