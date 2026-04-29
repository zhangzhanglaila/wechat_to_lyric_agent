<template>
  <div class="bg-white rounded-2xl shadow-card p-5 border border-border-light">
    <div class="flex items-center gap-2 mb-4">
      <div class="w-1 h-3 bg-bilibili-blue rounded-full"></div>
      <span class="text-xs font-semibold text-text-secondary uppercase tracking-widest">Creation Explanation</span>
    </div>

    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">

      <div class="bg-gray-50 border border-border-light rounded-lg px-3 py-2">
        <p class="text-xs text-text-tertiary mb-1">Emotion Arc</p>
        <p class="text-xs text-bilibili-pink font-semibold">{{ explanation.emotion_arc }}</p>
      </div>

      <div class="bg-gray-50 border border-border-light rounded-lg px-3 py-2">
        <p class="text-xs text-text-tertiary mb-1">Hook Strategy</p>
        <p class="text-xs text-bilibili-blue">{{ explanation.hook_strategy }}</p>
      </div>

      <div class="bg-gray-50 border border-border-light rounded-lg px-3 py-2">
        <p class="text-xs text-text-tertiary mb-1">Expression</p>
        <p class="text-xs text-bilibili-purple">
          {{ explanation.style_decisions?.expression || '—' }}
        </p>
      </div>

      <div class="bg-gray-50 border border-border-light rounded-lg px-3 py-2">
        <p class="text-xs text-text-tertiary mb-1">Refine Steps</p>
        <p class="text-xs text-green-600 font-medium">
          {{ explanation.final_refine_steps }}
          <span class="text-text-tertiary font-normal">/ {{ explanation.optimization_steps?.length || 0 }} applied</span>
        </p>
      </div>
    </div>

    <!-- Optimization Steps -->
    <div v-if="explanation.optimization_steps?.length" class="mb-4">
      <p class="text-xs text-text-tertiary mb-2 uppercase tracking-wider font-medium">Optimization Path</p>
      <div class="relative pl-4 border-l border-border-light space-y-3">
        <div
          v-for="(step, i) in explanation.optimization_steps"
          :key="step.step"
          class="relative"
        >
          <!-- Node -->
          <div class="absolute -left-[17px] w-2 h-2 rounded-full border-2 border-bilibili-blue bg-white"></div>
          <div class="bg-gray-50 border border-border-light rounded-lg px-3 py-2">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-xs font-bold text-text-secondary">Step {{ i + 1 }}</span>
              <span class="bg-bilibili-blue/10 border border-bilibili-blue/20 rounded px-2 py-0.5 text-xs text-bilibili-blue font-mono">
                {{ step.applied_op }}
              </span>
            </div>
            <div v-if="step.issues?.length" class="flex flex-wrap gap-1">
              <span
                v-for="issue in step.issues"
                :key="issue"
                class="text-xs text-red-500 bg-red-50 border border-red-200 rounded px-1.5 py-0.5"
              >
                {{ issue }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Style Decisions -->
    <div v-if="explanation.style_decisions">
      <p class="text-xs text-text-tertiary mb-2 uppercase tracking-wider font-medium">Style Decisions</p>
      <div class="flex flex-wrap gap-2">
        <span
          v-for="(val, key) in explanation.style_decisions"
          :key="key"
          v-show="val"
          class="text-xs px-2 py-1 rounded border border-border-light text-text-secondary"
        >
          {{ key }}: <span class="text-text-primary">{{ val }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ explanation: Object })
</script>
