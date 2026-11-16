<script lang="ts">
  // A number that glides to its new value and briefly tints green/red in the direction of the change.
  import { onDestroy } from 'svelte';
  export let value: number | null = null;
  export let format: (v: number) => string = v => String(v);
  export let tint = true;
  let shown: number | null = null;
  let dir = 0;
  let raf = 0, timer: ReturnType<typeof setTimeout>;
  const reduce = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  $: animate(value);
  function animate(target: number | null) {
    if (target == null || !isFinite(target)) { shown = null; return; }
    if (shown == null || reduce) { shown = target; return; }
    const from = shown, t0 = performance.now(), dur = 380;
    if (target !== from) { dir = target > from ? 1 : -1; clearTimeout(timer); timer = setTimeout(() => (dir = 0), 700); }
    cancelAnimationFrame(raf);
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      shown = from + (target - from) * e;
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  }
  onDestroy(() => { cancelAnimationFrame(raf); clearTimeout(timer); });
</script>
<span class="roll num" class:u={tint && dir > 0} class:d={tint && dir < 0}>{shown == null ? '—' : format(shown)}</span>
<style>
  .roll { transition: color .6s ease; }
  .u { color: var(--up); } .d { color: var(--down); }
</style>
