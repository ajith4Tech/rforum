<script lang="ts">
  import { page } from '$app/stores';
  import { theme, toggleTheme } from '$lib/theme';
  import { changePassword } from '$lib/api';
  import { isSuperAdmin, currentUser } from '$lib/stores';
  import { Orbit, Moon, Sun, LogOut, ChevronDown, User, Lock, Info, Shield, Zap, Users, BarChart3, MessageSquare, LogIn, UserPlus, BookOpen, CalendarDays, Presentation, Radio, Layers, BarChart2, MessageCircleQuestion, Star, Cloud, Monitor } from 'lucide-svelte';

  let {
    authenticated = false,
    onLogout = () => {}
  }: {
    authenticated?: boolean;
    onLogout?: () => void;
  } = $props();

  let profileOpen = $state(false);
  let moderatorOpen = $state(false);
  let menuOpen = $state(false);
  let showAbout = $state(false);
  let showUserGuide = $state(false);
  let guideSection = $state(0);

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
    if (!target.closest('[data-menu]')) menuOpen = false;
  }

  function openChangePwd() {
    menuOpen = false;
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

<nav class="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-4 sm:px-6 md:px-8 py-2.5 border-b backdrop-blur-md nav-bg">
  <div class="flex items-center gap-3 sm:gap-6">
    <a href={authenticated ? '/dashboard' : '/'} class="flex items-center gap-2">
      <Orbit class="w-7 h-7 text-brand-500 flex-shrink-0" />
      <span class="text-xl sm:text-2xl font-heading font-bold tracking-wide">Rforum</span>
    </a>

    {#if authenticated}
      <div class="hidden md:flex items-center gap-1">
        {#each navLinks as link}
          <a
            href={link.href}
            class="px-3 py-1.5 rounded-lg text-base font-bold transition {isActive(link.href)
              ? 'text-brand-500 bg-brand-500/10'
              : 'text-surface-500 hover:text-surface-200 hover:bg-surface-800'}"
          >
            {link.label}
          </a>
        {/each}
        {#if $isSuperAdmin}
          <a
            href="/dashboard/admin"
            class="px-3 py-1.5 rounded-lg text-base font-bold transition flex items-center gap-1.5 {isActive('/dashboard/admin')
              ? 'text-rose-500 bg-rose-500/10'
              : 'text-surface-500 hover:text-rose-400 hover:bg-rose-500/10'}"
          >
            <Shield class="w-3.5 h-3.5" />
            Admin
          </a>
        {/if}
      </div>
    {/if}
  </div>

  <div class="flex items-center gap-2 sm:gap-3">
    <!-- Unified menu -->
    <div class="relative" data-menu>
      <button
        onclick={() => menuOpen = !menuOpen}
        class="btn-secondary flex items-center gap-2 px-2.5 py-1.5"
      >
        {#if $isSuperAdmin}
          <Shield class="w-4 h-4 text-rose-500" />
        {:else}
          <User class="w-4 h-4" />
        {/if}
        <ChevronDown class="w-3 h-3 text-surface-400 transition-transform {menuOpen ? 'rotate-180' : ''}" />
      </button>

      {#if menuOpen}
        <div class="absolute right-0 mt-3 w-[min(20rem,calc(100vw-2rem))] rounded-2xl shadow-2xl border border-surface-200 dark:border-surface-700/60 bg-white dark:bg-surface-900 overflow-hidden animate-fade-in">
          {#if authenticated && $currentUser}
            <div class="px-4 py-3 border-b border-surface-200 dark:border-surface-700/60">
              <p class="text-xs font-semibold text-surface-900 dark:text-surface-100 truncate">{$currentUser.email}</p>
              <div class="flex items-center gap-1.5 mt-1">
                {#if $isSuperAdmin}
                  <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-rose-500/10 text-rose-500">
                    <Shield class="w-3 h-3" /> Super Admin
                  </span>
                {:else}
                  <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-surface-100 dark:bg-surface-800 text-surface-500">
                    <User class="w-3 h-3" /> Moderator
                  </span>
                {/if}
                {#if $currentUser && !$currentUser.is_active}
                  <span class="px-2 py-0.5 rounded-full text-xs font-bold bg-amber-500/10 text-amber-500">Disabled</span>
                {/if}
              </div>
            </div>
          {/if}

          {#if authenticated}
            <div class="md:hidden px-2 py-2 border-b border-surface-200 dark:border-surface-700/60">
              {#each navLinks as link}
                <a
                  href={link.href}
                  onclick={() => menuOpen = false}
                  class="flex items-center px-3 py-2.5 rounded-xl text-sm font-semibold transition {isActive(link.href)
                    ? 'text-brand-500 bg-brand-500/10'
                    : 'text-surface-700 dark:text-surface-200 hover:bg-surface-100 dark:hover:bg-surface-800'}"
                >
                  {link.label}
                </a>
              {/each}
              {#if $isSuperAdmin}
                <a
                  href="/dashboard/admin"
                  onclick={() => menuOpen = false}
                  class="mt-1 flex items-center gap-2 px-3 py-2.5 rounded-xl text-sm font-semibold transition {isActive('/dashboard/admin')
                    ? 'text-rose-500 bg-rose-500/10'
                    : 'text-surface-700 dark:text-surface-200 hover:bg-rose-50 dark:hover:bg-rose-500/10'}"
                >
                  <Shield class="w-3.5 h-3.5" />
                  Admin
                </a>
              {/if}
            </div>
          {/if}

          <div class="px-2 py-1.5 space-y-0.5">
            <button
              onclick={() => { menuOpen = false; showAbout = true; }}
              class="flex items-center gap-3 w-full px-3 py-2 rounded-xl text-sm font-semibold text-surface-700 dark:text-surface-200 hover:bg-surface-100 dark:hover:bg-surface-800 transition"
            >
              <Info class="w-5 h-5 flex-shrink-0 text-brand-500" />
              About
            </button>
            <button
              onclick={toggleTheme}
              class="flex items-center gap-3 w-full px-3 py-2 rounded-xl text-sm font-semibold text-surface-700 dark:text-surface-200 hover:bg-surface-100 dark:hover:bg-surface-800 transition"
            >
              {#if $theme === 'dark'}
                <Sun class="w-5 h-5 flex-shrink-0 text-amber-400" />
                Light Mode
              {:else}
                <Moon class="w-5 h-5 flex-shrink-0 text-indigo-400" />
                Dark Mode
              {/if}
            </button>

            {#if authenticated}
              <button
                onclick={() => { menuOpen = false; showUserGuide = true; guideSection = 0; }}
                class="flex items-center gap-3 w-full px-3 py-2 rounded-xl text-sm font-semibold text-surface-700 dark:text-surface-200 hover:bg-surface-100 dark:hover:bg-surface-800 transition"
              >
                <BookOpen class="w-5 h-5 flex-shrink-0 text-emerald-500" />
                User Guide
              </button>
              <button
                onclick={openChangePwd}
                class="flex items-center gap-3 w-full px-3 py-2 rounded-xl text-sm font-semibold text-surface-700 dark:text-surface-200 hover:bg-surface-100 dark:hover:bg-surface-800 transition"
              >
                <Lock class="w-5 h-5 flex-shrink-0 text-surface-400" />
                Reset Password
              </button>
            {:else}
              <a
                href="/login"
                onclick={() => menuOpen = false}
                class="flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold text-surface-700 dark:text-surface-200 hover:bg-surface-100 dark:hover:bg-surface-800 transition"
              >
                <LogIn class="w-5 h-5 flex-shrink-0 text-brand-500" />
                Moderator Login
              </a>
            {/if}
          </div>

          {#if authenticated}
            <div class="px-2 pb-2">
              <div class="border-t border-surface-200 dark:border-surface-700/60 mt-1 mb-2"></div>
              <button
                onclick={() => { menuOpen = false; onLogout(); }}
                class="flex items-center gap-3 w-full px-3 py-2 rounded-xl text-sm font-semibold text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10 transition"
              >
                <LogOut class="w-5 h-5 flex-shrink-0" />
                Log out
              </button>
            </div>
          {/if}
        </div>
      {/if}
    </div>
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

<!-- User Guide Modal -->
{#if showUserGuide}
  <div
    class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 z-50"
    onclick={(e) => { if (e.target === e.currentTarget) showUserGuide = false; }}
    role="dialog"
    aria-modal="true"
  >
    <div class="card w-full max-w-2xl shadow-2xl animate-fade-in flex flex-col" style="max-height: 88vh;">

      <div class="flex items-center justify-between mb-6 flex-shrink-0">
        <h2 class="text-2xl font-heading font-bold tracking-wide text-surface-900 dark:text-surface-100">Moderator User Guide</h2>
        <button onclick={() => showUserGuide = false} class="btn-secondary px-3 py-1.5 text-sm">Close</button>
      </div>

      <div class="overflow-y-auto flex-1 space-y-8 pr-1">

        <!-- Typical Workflow -->
        <section>
          <h3 class="text-lg font-heading font-semibold tracking-wide text-surface-900 dark:text-surface-100 mb-3">Typical Workflow</h3>
          <ol class="space-y-2">
            {#each [
              'Create an Event — set a title, date, and optional description.',
              'Create one or more Sessions under that Event.',
              'Add Slides to each Session — choose Poll, Q&A, Feedback, Word Cloud, or Content.',
              'Go Live — toggle Go Live on the session to activate the join code.',
              'Share the join code with participants (e.g. ABCD-1234). They open rforum.t4gc.in and enter it.',
              'Open the Presenter Screen in a new tab and project it to your audience.',
              'Activate slides one by one from the session dashboard as you present.',
              'Toggle Go Live off to end the session when finished.',
            ] as step, i}
              <li class="flex items-start gap-3 text-base font-heading text-surface-900 dark:text-surface-100">
                <span class="font-bold flex-shrink-0 w-5">{i + 1}.</span>
                <span>{step}</span>
              </li>
            {/each}
          </ol>
        </section>

        <hr class="border-surface-200 dark:border-surface-800" />

        <!-- Key Concepts -->
        <section>
          <h3 class="text-lg font-heading font-semibold tracking-wide text-surface-900 dark:text-surface-100 mb-3">Key Concepts</h3>
          <dl class="space-y-3">
            {#each [
              { term: 'Event', def: 'A named occasion (e.g. a conference or lecture day) that groups one or more sessions.' },
              { term: 'Session', def: 'A single interactive presentation slot. Has its own unique join code and a set of slides.' },
              { term: 'Slide', def: 'One interactive element inside a session. Can be a Poll, Q&A, Feedback form, Word Cloud, or static Content.' },
              { term: 'Join Code', def: 'An 8-character code (e.g. ABCD-1234) participants enter to connect to a live session.' },
              { term: 'Presenter Screen', def: 'A full-screen view at /screen/[code] intended to be projected to your audience.' },
            ] as item}
              <div class="flex gap-3 text-base font-heading text-surface-900 dark:text-surface-100">
                <dt class="font-semibold flex-shrink-0 w-36">{item.term}</dt>
                <dd>{item.def}</dd>
              </div>
            {/each}
          </dl>
        </section>

        <hr class="border-surface-200 dark:border-surface-800" />

        <!-- Slide Types -->
        <section>
          <h3 class="text-lg font-heading font-semibold tracking-wide text-surface-900 dark:text-surface-100 mb-3">Slide Types</h3>
          <dl class="space-y-3">
            {#each [
              { term: 'Poll',       def: 'Multiple-choice question. Results show as a live bar chart on the presenter screen.' },
              { term: 'Q&A',        def: 'Audience submits open questions. Others can upvote so the best ones rise to the top.' },
              { term: 'Feedback',   def: 'Collects written responses with an optional star rating.' },
              { term: 'Word Cloud', def: 'Participants submit words or short phrases shown as a real-time word cloud.' },
              { term: 'Content',    def: 'A static display slide — title, body, or bullet points. No audience input.' },
            ] as item}
              <div class="flex gap-3 text-base font-heading text-surface-900 dark:text-surface-100">
                <dt class="font-semibold flex-shrink-0 w-36">{item.term}</dt>
                <dd>{item.def}</dd>
              </div>
            {/each}
          </dl>
        </section>

        <hr class="border-surface-200 dark:border-surface-800" />

        <!-- Managing a Session -->
        <section>
          <h3 class="text-lg font-heading font-semibold tracking-wide text-surface-900 dark:text-surface-100 mb-3">Managing a Session</h3>
          <ul class="space-y-2">
            {#each [
              'Add slides from the session detail page — click Add Slide and pick a type.',
              'Use the order arrows on each slide card to reorder them.',
              'Only one slide can be active at a time. Click Activate on a slide to push it live.',
              'The active slide is instantly shown to all connected participants.',
              'Copy the join URL from the session page to share a direct link.',
              'Session data and all responses are always saved. View them any time from Analytics.',
            ] as item}
              <li class="flex items-start gap-3 text-base font-heading text-surface-900 dark:text-surface-100">
                <span class="flex-shrink-0 mt-1.5 w-1.5 h-1.5 rounded-full bg-surface-400 dark:bg-surface-500"></span>
                <span>{item}</span>
              </li>
            {/each}
          </ul>
        </section>

        <hr class="border-surface-200 dark:border-surface-800" />

        <!-- Presenter Screen -->
        <section>
          <h3 class="text-lg font-heading font-semibold tracking-wide text-surface-900 dark:text-surface-100 mb-3">Presenter Screen</h3>
          <ul class="space-y-2">
            {#each [
              'Click Open Screen on the session page — it opens /screen/[code] in a new tab.',
              'Put that tab in full-screen (F11) and project or share it to your display.',
              'The screen updates automatically as participants respond — no refresh needed.',
              'Keep the session dashboard open on a separate device to control which slide is active.',
              'The join code is always visible on screen so latecomers can join at any point.',
            ] as item}
              <li class="flex items-start gap-3 text-base font-heading text-surface-900 dark:text-surface-100">
                <span class="flex-shrink-0 mt-1.5 w-1.5 h-1.5 rounded-full bg-surface-400 dark:bg-surface-500"></span>
                <span>{item}</span>
              </li>
            {/each}
          </ul>
        </section>

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
