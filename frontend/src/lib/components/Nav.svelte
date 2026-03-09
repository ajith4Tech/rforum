<script lang="ts">
  import { page } from '$app/stores';
  import { theme, toggleTheme } from '$lib/theme';
  import { Orbit, Moon, Sun, LogOut, ChevronDown, User } from 'lucide-svelte';

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

<nav class="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-8 py-3 border-b backdrop-blur-md nav-bg">
  <div class="flex items-center gap-8">
    <a href={authenticated ? '/dashboard' : '/'} class="flex items-center gap-2">
      <Orbit class="w-6 h-6 text-brand-500" />
      <span class="text-lg font-heading font-bold tracking-wide">Rforum</span>
    </a>

    {#if authenticated}
      <div class="hidden md:flex items-center gap-1">
        {#each navLinks as link}
          <a
            href={link.href}
            class="px-3 py-1.5 rounded-lg text-sm font-medium transition {isActive(link.href)
              ? 'text-brand-500 bg-brand-500/10'
              : 'text-surface-500 hover:text-surface-200 hover:bg-surface-800'}"
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
      class="btn-secondary p-2"
      title="Toggle theme"
    >
      {#if $theme === 'dark'}
        <Sun class="w-4 h-4" />
      {:else}
        <Moon class="w-4 h-4" />
      {/if}
    </button>

    {#if authenticated}
      <div class="relative" data-profile-menu>
        <button
          onclick={() => profileOpen = !profileOpen}
          class="btn-secondary flex items-center gap-2 px-3 py-2"
        >
          <User class="w-4 h-4" />
          <ChevronDown class="w-3 h-3 text-surface-400 transition-transform {profileOpen ? 'rotate-180' : ''}" />
        </button>

        {#if profileOpen}
          <div class="absolute right-0 mt-2 w-44 card rounded-xl shadow-lg py-1 animate-fade-in">
            <button
              onclick={() => { profileOpen = false; onLogout(); }}
              class="flex items-center gap-2 w-full px-4 py-2.5 text-sm text-surface-400 hover:text-surface-100 hover:bg-surface-800 transition"
            >
              <LogOut class="w-4 h-4" />
              Log out
            </button>
          </div>
        {/if}
      </div>
    {:else}
      <a href="/login" class="btn-secondary text-sm">Log in</a>
      <a href="/login?mode=register" class="btn-primary text-sm">Sign up</a>
    {/if}
  </div>
</nav>
