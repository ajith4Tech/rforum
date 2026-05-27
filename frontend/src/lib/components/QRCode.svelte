<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import QRCode from 'qrcode';

  interface Props {
    data?: string;
    size?: number;
    errorCorrectionLevel?: 'L' | 'M' | 'Q' | 'H';
  }

  let { data = '', size = 300, errorCorrectionLevel = 'H' }: Props = $props();

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

<div bind:this={svgContainer} class="flex items-center justify-center" style="width: {size}px; height: {size}px;"></div>

<style>
  :global(div > svg) {
    width: 100%;
    height: 100%;
    max-width: 100%;
    max-height: 100%;
  }
</style>
