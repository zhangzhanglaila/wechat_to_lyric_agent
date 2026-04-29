<template>
  <div class="bg-white/[0.02] border border-white/[0.06] rounded-lg px-4 py-3">
    <div class="flex items-center gap-3">
      <span class="text-xs font-mono text-gray-700">{{ label }}</span>
      <div class="flex-1">
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold" :class="titleColor">{{ title }}</span>
          <span class="text-xs text-gray-600">— {{ subtitle }}</span>
        </div>
      </div>
      <div v-if="score !== undefined" class="text-right">
        <span class="text-sm font-bold text-yellow-300">{{ score.toFixed(2) }}</span>
        <span v-if="delta !== undefined" class="ml-1 text-xs" :class="delta > 0 ? 'text-green-400' : 'text-red-400'">
          Δ{{ delta > 0 ? '+' : '' }}{{ delta.toFixed(2) }}
        </span>
      </div>
    </div>
    <slot />
  </div>
</template>

<script setup>
const props = defineProps({
  label: String,
  title: String,
  subtitle: String,
  color: { type: String, default: 'purple' },
  score: Number,
  delta: Number,
})

const colorMap = {
  purple: 'text-purple-300',
  cyan: 'text-cyan-300',
  green: 'text-green-300',
  yellow: 'text-yellow-300',
}

const titleColor = colorMap[props.color] || colorMap.purple
</script>
