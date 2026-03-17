<script lang="ts">
  import { onMount } from 'svelte';
  import { getSessionByCode, updateSession } from '$lib/api';

  let code = $state('');
  let session: any = $state(null);
  let loading = $state(true);
  let error = $state('');
  let moderatorName = $state('');
  let speakerInput = $state('');
  let speakerNames = $state<string[]>([]);
  let saving = $state(false);

  const shareLinks = $derived.by(() => {
    if (typeof window === 'undefined' || !code) return null;
    const origin = window.location.origin;
    return {
      guest: `${origin}/session/${code}`,
      screen: `${origin}/screen/${code}`,
      embed: `${origin}/embed`
    };
  });

  onMount(async () => {
    code = typeof window !== 'undefined'
      ? (window.location.pathname.split('/').pop() || '').toUpperCase()
      : '';

    try {
      session = await getSessionByCode(code);
      moderatorName = session.moderator_name || '';
      speakerNames = Array.isArray(session.speaker_names) ? [...session.speaker_names] : [];
    } catch (e: any) {
      error = e.message || 'Could not load moderator view';
      if (e?.message?.toLowerCase().includes('credentials')) {
        window.location.href = '/login';
      }
    } finally {
      loading = false;
    }
  });

  function addSpeaker() {
    const name = speakerInput.trim();
    if (!name) return;
    if (speakerNames.some((s) => s.toLowerCase() === name.toLowerCase())) {
      speakerInput = '';
      return;
    }
    speakerNames = [...speakerNames, name];
    speakerInput = '';
  }

  function removeSpeaker(index: number) {
    speakerNames = speakerNames.filter((_, i) => i !== index);
  }

  async function saveSetup() {
    if (!session) return;
    saving = true;
    try {
      session = await updateSession(session.id, {
        moderator_name: moderatorName.trim() || null,
        speaker_names: speakerNames
      });
      moderatorName = session.moderator_name || '';
      speakerNames = Array.isArray(session.speaker_names) ? [...session.speaker_names] : [];
    } finally {
      saving = false;
    }
  }

  async function toggleLive() {
    if (!session) return;
    session = await updateSession(session.id, { is_live: !session.is_live });
  }

  function copyText(value: string) {
    navigator.clipboard.writeText(value);
  }
</script>

<svelte:head>
  <title>Moderator View - Rforum</title>
</svelte:head>

<main class="max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6 sm:py-7">
  {#if loading}
    <div class="card text-center text-surface-400 py-20">Loading moderator view...</div>
  {:else if error}
    <div class="card text-center text-red-500 py-10 px-6">{error}</div>
  {:else}
    <div class="flex items-center justify-between gap-3 mb-6">
      <div>
        <h1 class="text-3xl font-heading font-bold tracking-wide">Moderator View</h1>
        <p class="text-sm text-surface-500 mt-1.5">Session code: <span class="font-mono">{session.unique_code}</span></p>
      </div>
      <button class={session.is_live ? 'btn-live' : 'btn-secondary'} onclick={toggleLive}>
        {session.is_live ? 'Live' : 'Go Live'}
      </button>
    </div>

    <section class="card mb-5">
      <h2 class="font-heading font-semibold mb-3">Moderator Setup</h2>
      <div class="grid gap-3">
        <label>
          <span class="text-xs uppercase tracking-widest text-surface-500">Moderator Name</span>
          <input class="input-field mt-1" bind:value={moderatorName} placeholder="Moderator name" />
        </label>

        <label>
          <span class="text-xs uppercase tracking-widest text-surface-500">Guest Speakers / Panelists</span>
          <div class="flex gap-2 mt-1">
            <input
              class="input-field"
              bind:value={speakerInput}
              placeholder="Add speaker name"
              onkeydown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  addSpeaker();
                }
              }}
            />
            <button type="button" class="btn-secondary" onclick={addSpeaker}>Add</button>
          </div>
        </label>

        {#if speakerNames.length > 0}
          <div class="flex flex-wrap gap-2">
            {#each speakerNames as speaker, index (speaker + index)}
              <span class="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-surface-200 text-xs">
                {speaker}
                <button type="button" class="text-surface-500 hover:text-danger" onclick={() => removeSpeaker(index)}>x</button>
              </span>
            {/each}
          </div>
        {/if}

        <div>
          <button type="button" class="btn-primary" onclick={saveSetup} disabled={saving}>
            {saving ? 'Saving...' : 'Save setup'}
          </button>
        </div>
      </div>
    </section>

    <section class="card">
      <h2 class="font-heading font-semibold mb-3">Share Links</h2>
      {#if shareLinks}
        <div class="space-y-2 text-sm">
          <div class="flex gap-2 items-center">
            <span class="w-20 text-surface-500">Guest</span>
            <input class="input-field text-xs" readonly value={shareLinks.guest} />
            <button class="btn-secondary" onclick={() => copyText(shareLinks.guest)}>Copy</button>
          </div>
          <div class="flex gap-2 items-center">
            <span class="w-20 text-surface-500">Screen</span>
            <input class="input-field text-xs" readonly value={shareLinks.screen} />
            <button class="btn-secondary" onclick={() => copyText(shareLinks.screen)}>Copy</button>
          </div>
          <div class="flex gap-2 items-center">
            <span class="w-20 text-surface-500">Embed</span>
            <input class="input-field text-xs" readonly value={shareLinks.embed} />
            <button class="btn-secondary" onclick={() => copyText(shareLinks.embed)}>Copy</button>
          </div>
        </div>
      {/if}
    </section>
  {/if}
</main>
