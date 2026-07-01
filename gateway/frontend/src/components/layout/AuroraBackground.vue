<script setup>
defineProps({
  fixed: { type: Boolean, default: true }
})
</script>

<template>
  <div class="aurora-background" :class="fixed ? 'aurora-background--fixed' : 'aurora-background--absolute'">
    <div class="aurora-blob aurora-blob-1" />
    <div class="aurora-blob aurora-blob-2" />
    <div class="aurora-blob aurora-blob-3" />
    <div class="aurora-shape aurora-shape-1" />
    <div class="aurora-shape aurora-shape-2" />
    <div class="aurora-shape aurora-shape-3" />
    <div class="aurora-line aurora-line-1" />
    <div class="aurora-line aurora-line-2" />
    <div class="aurora-noise-mid" />
    <div class="aurora-grid" />
  </div>
</template>

<style scoped>
.aurora-background {
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}
.aurora-background--fixed {
  position: fixed;
  inset: 0;
}
.aurora-background--absolute {
  position: absolute;
  inset: 0;
}
.aurora-noise-mid,
.aurora-grid {
  position: absolute;
  inset: 0;
}
.aurora-noise-mid {
  opacity: 0.04;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='400'%3E%3Cfilter id='n2'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.4' numOctaves='5' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n2)'/%3E%3C/svg%3E");
  background-size: 400px 400px;
}
.aurora-grid {
  background-image:
    linear-gradient(rgba(132, 204, 22, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(132, 204, 22, 0.04) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 80%);
  -webkit-mask-image: radial-gradient(ellipse at center, black 30%, transparent 80%);
}


</style>
