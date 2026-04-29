<template>
  <div class="bg-white/[0.02] border border-white/[0.04] rounded-lg px-4 py-3 animate-pulse">
    <div class="flex items-center gap-3 mb-2">
      <div class="w-4 h-3 bg-white/[0.06] rounded"></div>
      <div class="h-3 bg-white/[0.08] rounded w-32"></div>
      <div class="ml-auto h-3 bg-white/[0.06] rounded w-16"></div>
    </div>
    <div class="h-8 bg-white/[0.04] rounded w-full"></div>
  </div>
</template>

<script setup>
defineProps({ step: Number })
</script>
