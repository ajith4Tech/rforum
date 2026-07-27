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
  }

  let { sessionCode = '', sessionTitle = '', joinUrl = '', onStartSession = undefined, isStarting = false, isModerator = false }: Props = $props();
</script>

<div class="min-h-screen flex flex-col bg-gradient-to-br from-gray-950 via-slate-900 to-gray-950 text-white font-sans overflow-hidden">
  <!-- Header -->
  <header class="flex items-center justify-center px-4 py-6 flex-shrink-0 border-b border-white/10">
    <div class="flex items-center gap-2.5">
      <Orbit class="w-6 md:w-7 h-6 md:h-7 text-brand-400" />
      <span class="font-heading font-bold text-lg md:text-xl tracking-wide text-white/80">Rforum</span>
    </div>
  </header>

  <!-- Main Content -->
  <main class="flex-1 flex flex-col items-center justify-center px-4 md:px-8 py-8 md:py-12 gap-8 md:gap-12">
    <!-- Centered Logo -->
    <img src="/logo-mascot.webp" alt="Tech Good Community" class="w-20 h-auto md:w-28 opacity-90" />

    <!-- Content Container -->
    <div class="flex flex-col items-center gap-6 md:gap-8 max-w-2xl w-full">
      <!-- Title Section -->
      <div class="text-center space-y-2 md:space-y-4">
        <h1 class="text-3xl md:text-4xl lg:text-5xl font-heading font-bold text-white leading-tight">
          {sessionTitle || 'Session Waiting to Start'}
        </h1>
        <p class="text-lg md:text-xl text-white/60">
          Get ready for an interactive session
        </p>
      </div>

      <!-- QR Code Section -->
      <div class="flex flex-col items-center gap-4 md:gap-6 w-full">
        <div class="bg-white/5 border border-white/20 p-8 md:p-12 rounded-3xl backdrop-blur-sm">
          <div class="bg-white p-6 md:p-8 rounded-2xl">
            <QRCode data={joinUrl} size={300} errorCorrectionLevel="H" />
          </div>
        </div>

        <!-- Instructions -->
        <div class="text-center space-y-2 text-white/70">
          <p class="text-white/90 font-semibold">📱 Scan to join now</p>
          <p class="text-sm md:text-base">Use your phone camera to scan the QR code</p>
        </div>
      </div>

      <!-- Session Code -->
      <div class="w-full text-center space-y-3">
        <p class="text-white/40 text-xs md:text-sm uppercase tracking-widest">Session Code</p>
        <div class="font-mono text-4xl md:text-5xl font-bold tracking-[0.25em] text-brand-400">
          {sessionCode}
        </div>
      </div>

      <!-- Manual Join Instructions -->
      <div class="w-full border-t border-white/10 pt-6 md:pt-8">
        <p class="text-white/40 text-xs md:text-sm uppercase tracking-widest mb-3 text-center">Can't scan?</p>
        <div class="bg-white/5 border border-white/10 rounded-xl p-4 md:p-6 text-center space-y-2">
          <p class="text-white/70 text-sm md:text-base">Visit on your phone:</p>
          <p class="font-mono text-sm md:text-base text-brand-400 break-all">{joinUrl}</p>
        </div>
      </div>

      <!-- Moderator Controls -->
      {#if isModerator && onStartSession}
        <button
          onclick={onStartSession}
          disabled={isStarting}
          class="w-full mt-4 md:mt-6 px-6 md:px-8 py-3 md:py-4 bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/50 text-white font-semibold rounded-xl transition-all duration-200 text-base md:text-lg"
        >
          {isStarting ? 'Starting Session...' : '▶ Start Session'}
        </button>
      {/if}
    </div>
  </main>

  <!-- Footer -->
  <footer class="flex items-center justify-center px-4 py-3 border-t border-white/10 flex-shrink-0 text-white/40 text-xs md:text-sm">
    <span>Rforum@2026</span>
  </footer>
</div>
