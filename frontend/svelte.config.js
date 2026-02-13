import adapter from '@sveltejs/adapter-node'; // Ensure ONLY node adapter is used
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter() // This produces the 'build/' folder for your Dockerfile
  }
};

export default config;