<template>
  <div class="glass-card p-4">
    <div class="flex items-center gap-2 mb-4">
      <div class="w-1 h-3 bg-accent-cyan rounded-full"></div>
      <span class="text-xs font-semibold text-gray-300 uppercase tracking-widest">Generation Pipeline</span>
      <span v-if="!loading" class="ml-auto text-xs text-gray-600">
        {{ result.candidates.length }} candidates
      </span>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="space-y-2">
      <PipelineStageSkeleton v-for="i in 4" :key="i" :step="i" />
    </div>

    <!-- Pipeline steps -->
    <div v-else class="relative space-y-1">

      <!-- Stage 1: Candidates -->
      <PipelineStage
        label="01"
        title="Candidates"
        subtitle="DSL + Constrained Generation"
        color="purple"
      >
        <div class="flex gap-2 mt-2 overflow-x-auto pb-1">
          <div
            v-for="(c, i) in result.candidates.slice(0, 3)"
            :key="i"
            class="flex-shrink-0 bg-white/[0.03] rounded px-3 py-1.5 text-xs border border-white/[0.06] max-w-[200px]"
          >
            <div class="flex items-center justify-between mb-1">
              <span class="text-gray-600">#{{ i + 1 }}</span>
              <span class="text-accent-purple font-semibold">{{ c.score.toFixed(2) }}</span>
            </div>
            <p class="text-gray-500 truncate">{{ c.text.slice(0, 60) }}</p>
          </div>
        </div>
      </PipelineStage>

      <!-- Arrow -->
      <div class="flex justify-center">
        <svg width="12" height="16" viewBox="0 0 12 16" fill="none" class="text-gray-700">
          <path d="M6 0v12M1 8l5 5 5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>

      <!-- Stage 2: Hook Optimization -->
      <PipelineStage
        label="02"
        title="Hook Optimization"
        subtitle="Multi-variant + Scoring"
        color="cyan"
      >
        <div class="mt-2 flex items-center gap-2">
          <div class="bg-accent-cyan/10 border border-accent-cyan/30 rounded px-3 py-1.5 text-xs max-w-[300px]">
            <span class="text-gray-500 mr-2">Best Hook:</span>
            <span class="text-cyan-200">{{ result.optimized_hook }}</span>
          </div>
          <span class="text-xs text-gray-700">
            {{ result.optimized_score.toFixed(2) }}
          </span>
        </div>
      </PipelineStage>

      <!-- Arrow -->
      <div class="flex justify-center">
        <svg width="12" height="16" viewBox="0 0 12 16" fill="none" class="text-gray-700">
          <path d="M6 0v12M1 8l5 5 5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>

      <!-- Stage 3: Beam Search Refine -->
      <PipelineStage
        label="03"
        title="Beam Search Refine"
        subtitle="LLM Ops Space Search"
        color="green"
      >
        <div class="mt-2 space-y-1">
          <div
            v-for="step in (result.explanation?.optimization_steps || [])"
            :key="step.step"
            class="flex items-center gap-2 text-xs"
          >
            <span class="text-gray-700 w-4">↳</span>
            <span class="bg-accent-green/10 border border-accent-green/30 rounded px-2 py-0.5 text-green-300">
              {{ step.applied_op || '—' }}
            </span>
            <span class="text-gray-600">
              {{ step.issues?.length ? `[${step.issues.join(', ')}]` : '' }}
            </span>
          </div>
          <div v-if="!result.explanation?.optimization_steps?.length" class="text-xs text-gray-700">
            No refine steps
          </div>
        </div>
      </PipelineStage>

      <!-- Arrow -->
      <div class="flex justify-center">
        <svg width="12" height="16" viewBox="0 0 12 16" fill="none" class="text-gray-700">
          <path d="M6 0v12M1 8l5 5 5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>

      <!-- Stage 4: Final Output -->
      <PipelineStage
        label="04"
        title="Final Output"
        subtitle="Score = Objective − Style Penalty"
        color="yellow"
        :score="result.optimized_score"
        :delta="result.delta"
      >
        <p class="mt-2 text-gray-400 text-xs leading-relaxed max-h-20 overflow-y-auto">
          {{ result.optimized_text.slice(0, 200) }}{{ result.optimized_text.length > 200 ? '...' : '' }}
        </p>
      </PipelineStage>

    </div>
  </div>
</template>

<script setup>
import PipelineStage from './PipelineStage.vue'
import PipelineStageSkeleton from './PipelineStageSkeleton.vue'

defineProps({
  result: Object,
  loading: Boolean,
})
</script>
