<script lang="ts">
  import { X } from 'lucide-svelte';
  import QRCode from './QRCode.svelte';

  interface Props {
    isOpen?: boolean;
    sessionCode?: string;
    joinUrl?: string;
    sessionTitle?: string;
  }

  let { isOpen = $bindable(false), sessionCode = '', joinUrl = '', sessionTitle = '' }: Props = $props();

  function closeModal() {
    isOpen = false;
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      closeModal();
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if isOpen}
  <!-- Fullscreen Modal Overlay -->
  <div
    class="fixed inset-0 z-50 bg-black/95 backdrop-blur-sm flex flex-col items-center justify-center p-4 md:p-8"
    role="dialog"
    aria-label="QR Code for joining session"
  >
    <!-- Close Button -->
    <button
      on:click={closeModal}
      class="absolute top-4 right-4 md:top-8 md:right-8 p-2 hover:bg-white/10 rounded-lg transition-colors"
      aria-label="Close modal"
    >
      <X class="w-6 h-6 md:w-8 md:h-8 text-white/80 hover:text-white" />
    </button>

    <!-- Modal Content -->
    <div class="flex flex-col items-center gap-8 md:gap-12 max-w-2xl w-full">
      <!-- Header -->
      <div class="text-center space-y-2 md:space-y-3">
        <h1 class="text-3xl md:text-4xl lg:text-5xl font-heading font-bold text-white">
          Join the Session
        </h1>
        {#if sessionTitle}
          <p class="text-lg md:text-xl text-white/70">{sessionTitle}</p>
        {/if}
      </div>

      <!-- QR Code Container -->
      <div class="flex flex-col items-center gap-6 md:gap-8">
        <div class="bg-white p-6 md:p-8 rounded-2xl shadow-2xl">
          <QRCode data={joinUrl} size={320} errorCorrectionLevel="H" />
        </div>

        <!-- Scan Instructions -->
        <div class="text-center space-y-3 text-white/70 text-sm md:text-base">
          <p class="text-white/90 font-semibold">📱 Use your phone camera to scan</p>
          <p>Point your device at the QR code above to join the session</p>
        </div>
      </div>

      <!-- Session Code / Manual Join -->
      <div class="w-full border-t border-white/10 pt-6 md:pt-8">
        <p class="text-white/40 text-xs md:text-sm uppercase tracking-widest mb-3">Or join manually with code:</p>
        <div class="bg-white/5 border border-white/10 rounded-xl p-4 md:p-6 text-center">
          <p class="font-mono text-2xl md:text-4xl font-bold text-brand-400 tracking-[0.2em] md:tracking-[0.3em]">
            {sessionCode}
          </p>
          <p class="text-white/50 text-xs md:text-sm mt-2">Visit: <span class="font-semibold text-white/70">{joinUrl}</span></p>
        </div>
      </div>

      <!-- Bottom Instructions -->
      <div class="w-full text-center space-y-2 text-white/50 text-xs md:text-sm">
        <p>Press <kbd class="bg-white/10 px-2 py-1 rounded text-white/70">ESC</kbd> to close</p>
      </div>
    </div>
  </div>
{/if}

<style>
  :global(kbd) {
    display: inline-block;
    margin: 0 2px;
  }
</style>
