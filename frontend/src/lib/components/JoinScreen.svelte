<script lang="ts">
  import { Orbit } from 'lucide-svelte';
  import QRCode from './QRCode.svelte';

  interface Props {
    sessionCode?: string;
    sessionTitle?: string;
    joinUrl?: string;
    onStartSession?: (() => void) | undefined;
    isStarting?: boolean;
    isModerator?: boolean;
    /** Shown under the Start button when starting the session failed. */
    startError?: string;
  }

  let { sessionCode = '', sessionTitle = '', joinUrl = '', onStartSession = undefined, isStarting = false, isModerator = false, startError = '' }: Props = $props();
</script>

<div class="min-h-screen flex flex-col font-sans overflow-x-hidden bg-surface-50 text-surface-900 dark:bg-surface-950 dark:text-surface-100">
  <header class="flex items-center justify-center px-4 py-4 flex-shrink-0 border-b border-surface-200 dark:border-surface-800">
    <div class="flex items-center gap-2.5">
      <Orbit class="w-6 md:w-7 h-6 md:h-7 text-brand-600 dark:text-brand-400" />
      <span class="font-heading font-bold text-lg md:text-xl tracking-wide text-surface-800 dark:text-surface-200">Rforum</span>
    </div>
  </header>

  <main class="flex-1 flex flex-col items-center justify-center px-4 md:px-8 py-6 md:py-10 gap-8 md:gap-10">
    <img src="/logo-mascot.webp" alt="Tech Good Community" width="80" height="100" class="w-16 h-auto md:w-20 opacity-80" />

    <div class="flex flex-col items-center gap-6 md:gap-8 max-w-2xl w-full">
      <div class="text-center space-y-2 md:space-y-3">
        <h1 class="text-3xl md:text-4xl lg:text-5xl font-heading font-bold leading-tight break-words text-surface-900 dark:text-white">
          {sessionTitle || 'Session Waiting to Start'}
        </h1>
        <p class="text-lg md:text-xl text-surface-600 dark:text-surface-400">
          Get ready for an interactive session
        </p>
      </div>

      <div class="flex flex-col items-center gap-4 md:gap-6 w-full">
        <!-- Padding steps down on phones so the 300px QR never overflows. -->
        <div class="max-w-full p-4 sm:p-8 md:p-12 rounded-3xl border bg-white border-surface-200 shadow-sm dark:bg-surface-900 dark:border-surface-800 dark:shadow-none">
          <div class="bg-white p-3 sm:p-6 md:p-8 rounded-2xl">
            <QRCode data={joinUrl} size={300} errorCorrectionLevel="H" label="QR code to join this session" />
          </div>
        </div>

        <div class="text-center space-y-2 text-surface-600 dark:text-surface-400">
          <p class="font-semibold text-surface-800 dark:text-surface-200">Scan to join now</p>
          <p class="text-sm md:text-base">Use your phone camera to scan the QR code</p>
        </div>
      </div>

      <div class="w-full text-center space-y-3">
        <p class="text-xs md:text-sm uppercase tracking-widest text-surface-600 dark:text-surface-400">Session Code</p>
        <div class="font-mono text-4xl md:text-5xl font-bold tracking-[0.25em] break-all text-brand-700 dark:text-brand-300">
          {sessionCode}
        </div>
      </div>

      <div class="w-full border-t pt-6 md:pt-8 border-surface-200 dark:border-surface-800">
        <p class="text-xs md:text-sm uppercase tracking-widest mb-3 text-center text-surface-600 dark:text-surface-400">Can't scan?</p>
        <div class="rounded-xl p-4 md:p-6 text-center space-y-2 border bg-white border-surface-200 dark:bg-surface-900 dark:border-surface-800">
          <p class="text-sm md:text-base text-surface-600 dark:text-surface-400">Visit on your phone:</p>
          <p class="font-mono text-sm md:text-base text-brand-700 dark:text-brand-300 break-all">{joinUrl}</p>
        </div>
      </div>

      {#if isModerator && onStartSession}
        <div class="w-full mt-2 md:mt-4 space-y-3">
          <button
            type="button"
            onclick={onStartSession}
            disabled={isStarting}
            aria-busy={isStarting}
            class="btn-primary w-full px-6 md:px-8 py-3 md:py-4 text-base md:text-lg"
          >
            {isStarting ? 'Starting Session...' : 'Start Session'}
          </button>
          {#if startError}
            <p class="rounded-xl border border-red-300 bg-red-50 px-4 py-2.5 text-center text-sm text-red-700 break-words dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300" role="alert">
              {startError}
            </p>
          {/if}
        </div>
      {/if}
    </div>
  </main>

  <footer class="flex items-center justify-center px-4 py-3 border-t flex-shrink-0 text-xs md:text-sm border-surface-200 text-surface-600 dark:border-surface-800 dark:text-surface-400">
    <span>Rforum@2026</span>
  </footer>
</div>
