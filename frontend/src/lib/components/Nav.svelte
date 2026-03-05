<script lang="ts">
  import { page } from '$app/stores';
  import { theme, toggleTheme } from '$lib/theme';
  import { RadioTower, Moon, Sun, LogOut, ChevronDown, User } from 'lucide-svelte';

  let {
    authenticated = false,
    onLogout = () => {}
  }: {
    authenticated?: boolean;
    onLogout?: () => void;
  } = $props();

  let profileOpen = $state(false);

  const navLinks = [
    { label: 'Dashboard', href: '/dashboard' },
    { label: 'Events', href: '/dashboard/events' },
    { label: 'Sessions', href: '/dashboard/sessions' },
    { label: 'Analytics', href: '/dashboard/analytics' }
  ];

  function isActive(href: string): boolean {
    const path = $page.url.pathname;
    if (href === '/dashboard') return path === '/dashboard';
    return path.startsWith(href);
  }

  function handleClickOutside(event: MouseEvent) {
    const target = event.target as HTMLElement;
    if (!target.closest('[data-profile-menu]')) {
      profileOpen = false;
    }
  }
</script>

<svelte:window onclick={handleClickOutside} />

<nav class="sticky top-0 z-40 flex items-center justify-between px-8 py-3 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/80 backdrop-blur-md">
  <div class="flex items-center gap-8">
    <a href={authenticated ? '/dashboard' : '/'} class="flex items-center gap-2">
      <RadioTower class="w-6 h-6 text-purple-500" />
      <span class="text-lg font-bold text-slate-900 dark:text-white">Rforum</span>
    </a>

    {#if authenticated}
      <div class="hidden md:flex items-center gap-1">
        {#each navLinks as link}
          <a
            href={link.href}
            class="px-3 py-1.5 rounded-lg text-sm font-medium transition {isActive(link.href)
              ? 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-500/10'
              : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800'}"
          >
            {link.label}
          </a>
        {/each}
      </div>
    {/if}
  </div>

  <div class="flex items-center gap-3">
    <button
      onclick={toggleTheme}
      class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 p-2 rounded-lg transition active:scale-95"
      title="Toggle theme"
    >
      {#if $theme === 'dark'}
        <Sun class="w-4 h-4 text-slate-400" />
      {:else}
        <Moon class="w-4 h-4 text-slate-600" />
      {/if}
    </button>

    {#if authenticated}
      <div class="relative" data-profile-menu>
        <button
          onclick={() => profileOpen = !profileOpen}
          class="flex items-center gap-2 border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-2 rounded-lg transition active:scale-95"
        >
          <User class="w-4 h-4 text-slate-500 dark:text-slate-400" />
          <ChevronDown class="w-3 h-3 text-slate-400 transition-transform {profileOpen ? 'rotate-180' : ''}" />
        </button>

        {#if profileOpen}
          <div class="absolute right-0 mt-2 w-44 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg py-1 animate-fade-in">
            <button
              onclick={() => { profileOpen = false; onLogout(); }}
              class="flex items-center gap-2 w-full px-4 py-2.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            >
              <LogOut class="w-4 h-4" />
              Log out
            </button>
          </div>
        {/if}
      </div>
    {:else}
      <a href="/login" class="border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 px-4 py-2 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 transition">Log in</a>
      <a href="/login?mode=register" class="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-medium px-4 py-2 rounded-lg shadow-lg shadow-purple-500/20 transition active:scale-95 text-sm">Sign up</a>
    {/if}
  </div>
</nav>
