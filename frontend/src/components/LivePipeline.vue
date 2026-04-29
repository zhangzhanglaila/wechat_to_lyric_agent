<template>
  <div class="bg-white rounded-2xl shadow-card p-4 border border-border-light">
    <div class="flex items-center gap-2 mb-4">
      <div class="w-1 h-3 bg-bilibili-blue rounded-full"></div>
      <span class="text-xs font-semibold text-text-secondary uppercase tracking-widest">
        Generation Pipeline
      </span>
      <span v-if="lastElapsed" class="ml-auto text-xs text-text-tertiary">
        ⏱ {{ lastElapsed }}s
      </span>
      <span v-if="isComplete" class="ml-auto text-xs text-green-500 font-medium">✓ 完成</span>
    </div>

    <!-- Steps list -->
    <div class="space-y-1.5">
      <div
        v-for="(evt, i) in steps"
        :key="i"
        class="flex items-center gap-3 px-3 py-2 rounded-lg text-xs transition-all"
        :class="stepClass(evt)"
      >
        <!-- Status icon -->
        <div class="flex-shrink-0 w-5 flex items-center justify-center">
          <span v-if="isDone(evt)" class="text-green-500">✓</span>
          <span v-else-if="isError(evt)" class="text-red-500">✗</span>
          <span v-else-if="isActive(evt)" class="text-bilibili-blue">
            <svg class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" stroke-dasharray="20 60" stroke-linecap="round"/>
            </svg>
          </span>
          <span v-else class="text-text-tertiary">○</span>
        </div>

        <!-- Step name -->
        <span class="font-mono font-semibold w-28 flex-shrink-0" :class="stepNameColor(evt)">
          {{ formatStepName(evt.step) }}
        </span>

        <!-- Message -->
        <span class="flex-1 text-text-tertiary">{{ evt.msg }}</span>

        <!-- Score badge -->
        <span v-if="evt.data?.score !== undefined" class="flex-shrink-0 text-bilibili-pink font-bold">
          {{ typeof evt.data.score === 'number' ? evt.data.score.toFixed(2) : evt.data.score }}
        </span>

        <!-- Elapsed -->
        <span v-if="evt.elapsed" class="flex-shrink-0 text-text-tertiary text-xs">
          {{ evt.elapsed }}s
        </span>

        <!-- Sub step badge -->
        <span v-if="evt.data?.op" class="flex-shrink-0 bg-bilibili-blue/10 border border-bilibili-blue/20 rounded px-1.5 py-0.5 text-bilibili-blue font-mono">
          {{ evt.data.op }}
        </span>
      </div>
    </div>

    <!-- Progress bar -->
    <div v-if="!isComplete && steps.length > 0" class="mt-3">
      <div class="h-1 bg-gray-100 rounded overflow-hidden">
        <div class="h-full bg-bilibili-blue/60 animate-pulse" style="width: 100%"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
})

const isDone = (evt) => evt.step === 'final' || (evt.step !== 'error' && !evt.step.includes('start') && !evt.step.includes('partial'))
const isError = (evt) => evt.step === 'error'
const isActive = (evt) => !isDone(evt) && !isError(evt)

const isComplete = computed(() => props.steps.some(e => e.step === 'final' || e.step === 'error'))

const lastElapsed = computed(() => {
  const last = props.steps[props.steps.length - 1]
  return last?.elapsed
})

const STEP_ORDER = [
  'prompt', 'llm', 'token',
  'parse', 'emotion', 'dsl', 'dsl_done',
  'candidates', 'candidate_partial',
  'rank',
  'refine_start',
  'refine_c1', 'refine_c1_step', 'refine_c1_done',
  'refine_c2', 'refine_c2_step', 'refine_c2_done',
  'done', 'final',
]

const stepClass = (evt) => {
  if (isDone(evt)) return 'bg-green-50 border border-green-200'
  if (isError(evt)) return 'bg-red-50 border border-red-200'
  if (isActive(evt)) return 'bg-bilibili-blue/5 border border-bilibili-blue/20'
  return 'bg-gray-50 border border-gray-100'
}

const stepNameColor = (evt) => {
  if (isError(evt)) return 'text-red-500'
  if (evt.step.includes('rank')) return 'text-bilibili-purple'
  if (evt.step.includes('refine')) return 'text-green-600'
  if (evt.step.includes('candidate')) return 'text-bilibili-blue'
  if (evt.step === 'done' || evt.step === 'final') return 'text-bilibili-pink'
  return 'text-text-secondary'
}

const formatStepName = (step) => {
  const map = {
    'parse': '01 Parse',
    'prompt': '01 Prompt',
    'llm': '02 LLM',
    'token': '02 Token',
    'emotion': '02 Emotion',
    'dsl': '03 DSL',
    'dsl_done': '03 DSL ✓',
    'candidates': '04 Candidates',
    'candidate_partial': '04.1 Cand.',
    'rank': '05 Rank',
    'refine_start': '06 Refine',
    'refine_c1': '06.1 C1',
    'refine_c1_step': '06.1 C1',
    'refine_c1_done': '06.1 C1 ✓',
    'refine_c2': '06.2 C2',
    'refine_c2_step': '06.2 C2',
    'refine_c2_done': '06.2 C2 ✓',
    'done': '07 Done',
    'final': '07 Done',
    'error': 'Error',
  }
  return map[step] || step
}
</script>
