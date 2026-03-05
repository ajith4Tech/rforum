<script lang="ts">
  let { published = false } = $props();
</script>

{#if published}
  <span class="bg-green-500/10 text-green-400 px-2 py-1 rounded-md text-xs font-medium">
    Published
  </span>
{:else}
  <span class="bg-yellow-500/10 text-yellow-400 px-2 py-1 rounded-md text-xs font-medium">
    Draft
  </span>
{/if}
