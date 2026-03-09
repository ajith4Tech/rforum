<script lang="ts">
  import { page } from '$app/stores';
  import { theme, toggleTheme } from '$lib/theme';
  import { changePassword } from '$lib/api';
  import { Orbit, Moon, Sun, LogOut, ChevronDown, User, Lock, Info, Shield, Zap, Users, BarChart3, MessageSquare, LogIn, UserPlus } from 'lucide-svelte';

  let {
    authenticated = false,
    onLogout = () => {}
  }: {
    authenticated?: boolean;
    onLogout?: () => void;
  } = $props();

  let profileOpen = $state(false);
  let moderatorOpen = $state(false);
  let showAbout = $state(false);
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

  const features = [
    { icon: Zap,           color: 'amber',   title: 'Live Interaction',   desc: 'Real-time polls, Q&A and feedback during live sessions.' },
    { icon: Users,         color: 'cyan',    title: 'Easy Join',          desc: 'Participants join instantly with a short session code.' },
    { icon: BarChart3,     color: 'emerald', title: 'Live Analytics',     desc: 'See poll results, word clouds and insights as they happen.' },
    { icon: MessageSquare, color: 'rose',    title: 'Multiple Formats',   desc: 'Polls, Q&A, feedback forms, word clouds and slides.' },
  ];

  const colorMap: Record<string, string> = {
    amber:   'bg-amber-500/10 text-amber-500',
    cyan:    'bg-cyan-500/10 text-cyan-500',
    emerald: 'bg-emerald-500/10 text-emerald-500',
    rose:    'bg-rose-500/10 text-rose-500',
  };

  function isActive(href: string): boolean {
    const path = $page.url.pathname;
    if (href === '/dashboard') return path === '/dashboard';
    return path.startsWith(href);
  }

  function handleClickOutside(event: MouseEvent) {
    const target = event.target as HTMLElement;
    if (!target.closest('[data-profile-menu]'))  profileOpen  = false;
    if (!target.closest('[data-moderator-menu]')) moderatorOpen = false;
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
      <Orbit class="w-7 h-7 text-brand-500 flex-shrink-0" />
      <span class="text-2xl font-heading font-bold tracking-wide">Rforum</span>
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

    <!-- About Rforum button (always visible) -->
    <button
      onclick={() => showAbout = true}
      class="btn-secondary flex items-center gap-2 text-sm px-3 py-2"
    >
      <Info class="w-4 h-4" />
      About
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
          <div class="absolute right-0 mt-2 w-48 card rounded-xl shadow-lg overflow-hidden animate-fade-in">
            <button
              onclick={openChangePwd}
              class="flex items-center gap-3 w-full px-4 py-3 text-sm font-medium text-surface-400 hover:text-surface-100 hover:bg-surface-800/70 transition"
            >
              <Lock class="w-4 h-4 flex-shrink-0" />
              Reset Password
            </button>
            <div class="border-t border-surface-800"></div>
            <button
              onclick={() => { profileOpen = false; onLogout(); }}
              class="flex items-center gap-3 w-full px-4 py-3 text-sm font-medium text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 transition"
            >
              <LogOut class="w-4 h-4 flex-shrink-0" />
              Log out
            </button>
          </div>
        {/if}
      </div>
    {:else}
      <!-- Moderator dropdown -->
      <div class="relative" data-moderator-menu>
        <button
          onclick={() => moderatorOpen = !moderatorOpen}
          class="btn-secondary flex items-center gap-2 text-sm px-3 py-2"
        >
          <Shield class="w-4 h-4" />
          Moderator
          <ChevronDown class="w-3 h-3 text-surface-400 transition-transform {moderatorOpen ? 'rotate-180' : ''}" />
        </button>

        {#if moderatorOpen}
          <div class="absolute right-0 mt-2 w-44 card rounded-xl shadow-lg py-1 animate-fade-in">
            <a
              href="/login"
              onclick={() => moderatorOpen = false}
              class="flex items-center gap-2 px-4 py-2.5 text-sm text-surface-400 hover:text-surface-100 hover:bg-surface-800 transition"
            >
              <LogIn class="w-4 h-4" />
              Log in
            </a>
            <div class="my-1 border-t border-surface-800"></div>
            <a
              href="/login?mode=register"
              onclick={() => moderatorOpen = false}
              class="flex items-center gap-2 px-4 py-2.5 text-sm text-surface-400 hover:text-surface-100 hover:bg-surface-800 transition"
            >
              <UserPlus class="w-4 h-4" />
              Sign up
            </a>
          </div>
        {/if}
      </div>
    {/if}
  </div>
</nav>

<!-- About Rforum Modal -->
{#if showAbout}
  <div
    class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50"
    onclick={(e) => { if (e.target === e.currentTarget) showAbout = false; }}
    role="dialog"
    aria-modal="true"
  >
    <div class="card w-full max-w-lg shadow-2xl animate-fade-in">
      <div class="flex items-center justify-between mb-6">
        <div class="flex items-center gap-2">
          <Orbit class="w-7 h-7 text-brand-500" />
          <h2 class="text-xl font-heading font-bold tracking-wide">Rforum</h2>
        </div>
        <button onclick={() => showAbout = false} class="btn-secondary px-3 py-1.5 text-xs">Close</button>
      </div>
      <p class="text-sm text-surface-400 mb-6 leading-relaxed">
        Rforum is a real-time audience engagement platform built for live events and presentations.
        Moderators create sessions with polls, Q&A, word clouds and slide content — guests join
        instantly with a short code from any device.
      </p>
      <div class="grid grid-cols-2 gap-4">
        {#each features as f}
          <div class="flex items-start gap-3">
            <div class="w-9 h-9 flex items-center justify-center rounded-xl {colorMap[f.color]} flex-shrink-0 mt-0.5">
              <f.icon class="w-4 h-4" />
            </div>
            <div>
              <p class="text-sm font-semibold">{f.title}</p>
              <p class="text-xs text-surface-500 mt-0.5 leading-relaxed">{f.desc}</p>
            </div>
          </div>
        {/each}
      </div>
    </div>
  </div>
{/if}

<!-- Reset Password Modal -->
{#if showChangePwd}
  <div
    class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50"
    onclick={(e) => { if (e.target === e.currentTarget) showChangePwd = false; }}
    role="dialog"
    aria-modal="true"
  >
    <div class="card w-full max-w-sm shadow-2xl animate-fade-in p-6">
      <!-- Modal header -->
      <div class="flex items-center gap-3 mb-1">
        <div class="w-9 h-9 flex items-center justify-center rounded-xl bg-brand-500/10 flex-shrink-0">
          <Lock class="w-4 h-4 text-brand-500" />
        </div>
        <div>
          <h2 class="text-base font-heading font-bold tracking-wide leading-tight">Reset Password</h2>
          <p class="text-xs text-surface-500">Update your account password</p>
        </div>
      </div>

      <div class="my-4 border-t border-surface-200 dark:border-surface-800"></div>

      <form onsubmit={handleChangePwd} class="space-y-3">
        <div>
          <label class="block text-xs font-medium text-surface-400 mb-1.5">Current password</label>
          <div class="relative">
            <Lock class="absolute left-3.5 top-3 w-4 h-4 text-surface-400" />
            <input
              type="password"
              bind:value={currentPwd}
              placeholder="Enter current password"
              class="input-field pl-10"
              required
              minlength="1"
            />
          </div>
        </div>
        <div>
          <label class="block text-xs font-medium text-surface-400 mb-1.5">New password</label>
          <div class="relative">
            <Lock class="absolute left-3.5 top-3 w-4 h-4 text-surface-400" />
            <input
              type="password"
              bind:value={newPwd}
              placeholder="Min 6 characters"
              class="input-field pl-10"
              required
              minlength="6"
            />
          </div>
        </div>

        {#if pwdError}
          <div class="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2">
            <p class="text-xs text-red-400">{pwdError}</p>
          </div>
        {/if}
        {#if pwdSuccess}
          <div class="rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-2">
            <p class="text-xs text-emerald-400">{pwdSuccess}</p>
          </div>
        {/if}

        <div class="flex gap-2 pt-2">
          <button type="button" onclick={() => showChangePwd = false} class="btn-secondary flex-1 text-sm py-2">Cancel</button>
          <button type="submit" class="btn-primary flex-1 text-sm py-2" disabled={pwdLoading}>
            {pwdLoading ? 'Saving…' : 'Save password'}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}
