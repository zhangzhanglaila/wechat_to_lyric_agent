<template>
  <div class="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
    <div
      class="h-full rounded-full transition-all duration-500"
      :class="barColor"
      :style="{ width: `${score * 100}%` }"
    ></div>
  </div>
</template>

<script setup>
const props = defineProps({
  score: Number,
  color: { type: String, default: 'pink' },
})

const colorMap = {
  pink: 'bg-bilibili-pink',
  blue: 'bg-bilibili-blue',
  purple: 'bg-bilibili-purple',
  green: 'bg-green-500',
  gray: 'bg-gray-400',
}

const barColor = colorMap[props.color] || colorMap.pink
</script>
