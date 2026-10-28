<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import QRCode from 'qrcode';

  interface Props {
    data?: string;
    size?: number;
    errorCorrectionLevel?: 'L' | 'M' | 'Q' | 'H';
    /** Accessible name for the code (screen readers can't read the image). */
    label?: string;
  }

  let { data = '', size = 300, errorCorrectionLevel = 'H', label = 'QR code' }: Props = $props();

  let canvas: HTMLCanvasElement | undefined;
  let svgContainer: HTMLDivElement | undefined;

  const generateQR = async () => {
    if (!data || !svgContainer) return;

    try {
      // Clear previous content
      svgContainer.innerHTML = '';

      // Generate QR code as SVG
      const svg = await QRCode.toString(data, {
        type: 'image/svg+xml',
        width: size,
        margin: 2,
        color: {
          dark: '#000000',
          light: '#ffffff'
        },
        errorCorrectionLevel
      });

      // Insert SVG directly
      svgContainer.innerHTML = svg;
    } catch (error) {
      console.error('Error generating QR code:', error);
    }
  };

  onMount(generateQR);

  // Regenerate when data changes
  $effect(() => {
    untrack(() => {
      if (data) {
        generateQR();
      }
    });
  });
</script>

<!-- max-width + aspect-ratio: shrinks with a narrow phone/projector viewport
     instead of overflowing it, and stays square. -->
<div
  bind:this={svgContainer}
  class="qr-code flex items-center justify-center"
  role="img"
  aria-label={label}
  style="width: {size}px; max-width: 100%; aspect-ratio: 1 / 1;"
></div>

<style>
  /* Scoped to this component's container — a bare :global(div > svg) also
     stretched every other SVG (icons, rich-text content) in the app. */
  .qr-code > :global(svg) {
    width: 100%;
    height: 100%;
    max-width: 100%;
    max-height: 100%;
  }
</style>
