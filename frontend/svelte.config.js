import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      fallback: 'index.html',
      pages: '/tmp/claude-1000/-home-ubuntu-rforum/ab968de9-0b74-45d6-9560-85baa2a8bac0/scratchpad/build-debug',
      assets: '/tmp/claude-1000/-home-ubuntu-rforum/ab968de9-0b74-45d6-9560-85baa2a8bac0/scratchpad/build-debug'
    })
  }
};

export default config;
