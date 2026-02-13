import adapter from '@sveltejs/adapter-node'; // Keep only node
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    // adapter-node will produce the /build folder used in the Dockerfile
    adapter: adapter()
  }
};

export default config;