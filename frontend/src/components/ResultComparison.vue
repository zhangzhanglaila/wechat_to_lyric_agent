<template>
  <div class="bg-white rounded-2xl shadow-card p-5 border border-border-light">
    <div class="flex items-center gap-2 mb-4">
      <div class="w-1 h-3 bg-bilibili-pink rounded-full"></div>
      <span class="text-xs font-semibold text-text-secondary uppercase tracking-widest">Baseline vs Optimized</span>
      <span
        class="ml-auto text-xs px-2 py-0.5 rounded-full font-semibold"
        :class="result.delta > 0 ? 'bg-green-50 text-green-600 border border-green-200' : 'bg-red-50 text-red-500 border border-red-200'"
      >
        Δ {{ result.delta > 0 ? '+' : '' }}{{ result.delta.toFixed(2) }}
      </span>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">

      <!-- Baseline -->
      <div class="border border-border-light rounded-xl overflow-hidden">
        <div class="px-4 py-2.5 border-b border-border-light flex items-center justify-between bg-gray-50/50">
          <span class="text-xs text-text-secondary font-medium">Baseline</span>
          <div class="flex items-center gap-2">
            <ScoreBar :score="result.baseline_score" color="gray" />
            <span class="text-xs font-bold" :class="scoreColor(result.baseline_score)">
              {{ result.baseline_score.toFixed(2) }}
            </span>
          </div>
        </div>
        <div class="p-4">
          <p class="text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
            {{ result.baseline_text }}
          </p>
          <div v-if="result.baseline_hook" class="mt-3 pt-3 border-t border-border-light">
            <span class="text-xs text-text-tertiary">Hook: </span>
            <span class="text-xs text-text-secondary">{{ result.baseline_hook }}</span>
          </div>
        </div>
      </div>

      <!-- Optimized -->
      <div class="border border-bilibili-pink/30 rounded-xl overflow-hidden bg-bilibili-pink/5">
        <div class="px-4 py-2.5 border-b border-bilibili-pink/20 flex items-center justify-between bg-bilibili-pink/5">
          <div class="flex items-center gap-2">
            <span class="text-xs text-bilibili-pink font-medium">Optimized</span>
            <span class="text-xs text-text-tertiary">(full pipeline)</span>
          </div>
          <div class="flex items-center gap-2">
            <ScoreBar :score="result.optimized_score" color="pink" />
            <span class="text-xs font-bold text-bilibili-pink">
              {{ result.optimized_score.toFixed(2) }}
            </span>
          </div>
        </div>
        <div class="p-4">
          <p class="text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
            {{ result.optimized_text }}
          </p>
          <div v-if="result.optimized_hook" class="mt-3 pt-3 border-t border-border-light">
            <span class="text-xs text-text-tertiary">Hook: </span>
            <span class="text-xs text-bilibili-pink font-medium">{{ result.optimized_hook }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Score Details -->
    <div class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
      <ScoreDetails title="Baseline Details" :details="result.baseline_score_details" color="gray" />
      <ScoreDetails title="Optimized Details" :details="result.optimized_score_details" color="pink" />
    </div>
  </div>
</template>

<script setup>
import ScoreBar from './ScoreBar.vue'
import ScoreDetails from './ScoreDetails.vue'

defineProps({ result: Object })

function scoreColor(s) {
  if (s >= 0.7) return 'text-green-500'
  if (s >= 0.5) return 'text-yellow-500'
  return 'text-red-500'
}
</script>
