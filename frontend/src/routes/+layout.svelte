<script>
  import '../app.css';

  let { children } = $props();
</script>

<div class="min-h-screen bg-surface-950">
  {@render children()}
</div>
