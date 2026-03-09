<script lang="ts">
  import { page } from '$app/stores';
  import { theme, toggleTheme } from '$lib/theme';
  import { changePassword } from '$lib/api';
  import { Orbit, Moon, Sun, LogOut, ChevronDown, User, Lock } from 'lucide-svelte';

  let {
    authenticated = false,
    onLogout = () => {}
  }: {
    authenticated?: boolean;
    onLogout?: () => void;
  } = $props();

  let profileOpen = $state(false);
  let showChangePwd = $state(false);
  let currentPwd = $state('');
  let newPwd = $state('');
  let pwdError = $state('');
  let pwdSuccess = $state('');
  let pwdLoading = $state(false);

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

  function openChangePwd() {
    profileOpen = false;
    currentPwd = '';
    newPwd = '';
    pwdError = '';
    pwdSuccess = '';
    showChangePwd = true;
  }

  async function handleChangePwd(e: Event) {
    e.preventDefault();
    pwdError = '';
    pwdSuccess = '';
    pwdLoading = true;
    try {
      await changePassword(currentPwd, newPwd);
      pwdSuccess = 'Password updated successfully';
      currentPwd = '';
      newPwd = '';
      setTimeout(() => { showChangePwd = false; pwdSuccess = ''; }, 1500);
    } catch (err: any) {
      pwdError = err?.message || 'Could not update password';
    } finally {
      pwdLoading = false;
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
          <div class="absolute right-0 mt-2 w-52 card rounded-xl shadow-lg py-1 animate-fade-in">
            <button
              onclick={openChangePwd}
              class="flex items-center gap-2 w-full px-4 py-2.5 text-sm text-surface-400 hover:text-surface-100 hover:bg-surface-800 transition"
            >
              <Lock class="w-4 h-4" />
              Change Password
            </button>
            <div class="my-1 border-t border-surface-800"></div>
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
    {/if}
  </div>
</nav>

<!-- Change Password Modal -->
{#if showChangePwd}
  <div
    class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50"
    onclick={(e) => { if (e.target === e.currentTarget) showChangePwd = false; }}
    role="dialog"
    aria-modal="true"
  >
    <div class="card w-full max-w-sm shadow-2xl animate-fade-in">
      <div class="flex items-center justify-between mb-5">
        <h2 class="text-lg font-heading font-bold tracking-wide">Change Password</h2>
        <button onclick={() => showChangePwd = false} class="btn-secondary px-3 py-1.5 text-xs">Close</button>
      </div>
      <form onsubmit={handleChangePwd} class="space-y-4">
        <div class="relative">
          <Lock class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400" />
          <input
            type="password"
            bind:value={currentPwd}
            placeholder="Current password"
            class="input-field pl-10"
            required
            minlength="1"
          />
        </div>
        <div class="relative">
          <Lock class="absolute left-3.5 top-3.5 w-4 h-4 text-surface-400" />
          <input
            type="password"
            bind:value={newPwd}
            placeholder="New password (min 6 chars)"
            class="input-field pl-10"
            required
            minlength="6"
          />
        </div>
        {#if pwdError}
          <p class="text-danger text-sm">{pwdError}</p>
        {/if}
        {#if pwdSuccess}
          <p class="text-emerald-500 text-sm">{pwdSuccess}</p>
        {/if}
        <div class="flex gap-2 pt-1">
          <button type="button" onclick={() => showChangePwd = false} class="btn-secondary flex-1 text-sm">Cancel</button>
          <button type="submit" class="btn-primary flex-1 text-sm" disabled={pwdLoading}>
            {pwdLoading ? 'Updating…' : 'Update'}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}
