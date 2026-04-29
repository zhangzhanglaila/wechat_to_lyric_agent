<template>
  <div>
    <p class="text-xs text-text-tertiary mb-2 uppercase tracking-wider font-medium">{{ title }}</p>
    <div class="space-y-1.5">
      <div v-for="(val, key) in filteredDetails" :key="key"
           class="flex items-center gap-2 text-xs">
        <span class="text-text-tertiary w-28 truncate">{{ key.replace(/_/g, ' ') }}</span>
        <div class="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            class="h-full rounded-full"
            :class="barColor"
            :style="{ width: `${val * 100}%` }"
          ></div>
        </div>
        <span class="w-8 text-right" :class="val >= 0.6 ? 'text-green-500' : val >= 0.3 ? 'text-yellow-500' : 'text-red-500'">
          {{ val.toFixed(2) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: String,
  details: Object,
  color: { type: String, default: 'pink' },
})

const colorMap = {
  pink: 'bg-bilibili-pink',
  blue: 'bg-bilibili-blue',
  purple: 'bg-bilibili-purple',
  gray: 'bg-gray-400',
}
const barColor = colorMap[props.color] || colorMap.pink

const filteredDetails = computed(() => {
  if (!props.details) return {}
  return Object.fromEntries(
    Object.entries(props.details).filter(([k]) => k !== 'total')
  )
})
</script>
