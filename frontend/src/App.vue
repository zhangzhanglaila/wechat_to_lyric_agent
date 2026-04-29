<template>
  <div class="min-h-screen bg-bg-primary text-text-primary font-sans">

    <!-- Header -->
    <header class="bg-white border-b border-border-light px-6 py-4 sticky top-0 z-50">
      <div class="max-w-7xl mx-auto flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-lg bg-bilibili-blue flex items-center justify-center text-white font-bold text-sm">
            G
          </div>
          <div>
            <h1 class="text-base font-bold text-text-primary tracking-wide">
              GenWriter Agent
            </h1>
            <p class="text-xs text-text-tertiary">
              可控歌词/诗歌生成 — LLM + 搜索优化
            </p>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <!-- LLM 状态指示 -->
          <button @click="testLLM" :disabled="llmLoading"
                  class="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border border-border-light hover:border-bilibili-blue transition-colors">
            <span class="w-2 h-2 rounded-full" :class="llmStatus === 'ok' ? 'bg-green-500' : llmStatus === 'error' ? 'bg-red-500' : 'bg-gray-400'"></span>
            <span class="text-text-secondary">{{ llmStatusText }}</span>
          </button>
          <div class="flex items-center gap-1.5 text-xs text-text-tertiary">
            <span class="tag">v1.0</span>
            <span>beam search</span>
            <span>·</span>
            <span>DSL</span>
            <span>·</span>
            <span>multi-candidate</span>
          </div>
        </div>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-12 gap-5">

      <!-- Left: Input + Controls -->
      <div class="lg:col-span-4 flex flex-col gap-4">

        <!-- Input Card -->
        <div class="bg-white rounded-2xl shadow-card p-5">
          <div class="flex items-center gap-2 mb-3">
            <div class="w-1.5 h-4 bg-bilibili-blue rounded-full"></div>
            <span class="text-sm font-bold text-text-primary">输入</span>
          </div>
          <textarea
            v-model="inputText"
            class="w-full bg-gray-50 border border-border-light rounded-xl
                   px-3 py-2.5 text-sm text-text-primary placeholder-text-tertiary
                   resize-none focus:outline-none focus:border-bilibili-blue focus:ring-2 focus:ring-bilibili-blue/20
                   transition-all"
            rows="4"
            placeholder="输入关键词或聊天记录..."
          />
          <div class="flex gap-2 mt-3">
            <select v-model="mode" class="flex-1 bg-gray-50 border border-border-light rounded-lg px-2 py-1.5 text-xs text-text-secondary">
              <option value="lyrics">🎵 lyrics</option>
              <option value="poem">📝 poem</option>
            </select>
            <button @click="generate" :disabled="loading || !inputText.trim()"
                    class="flex-1 flex items-center justify-center gap-2 bg-bilibili-blue hover:bg-bilibili-blue/90 text-white rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
              <svg v-if="loading" class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" stroke-dasharray="20 40" stroke-linecap="round"/>
              </svg>
              <span>{{ loading ? '生成中...' : '▶ 生成' }}</span>
            </button>
          </div>
        </div>

        <!-- Control Panel -->
        <div class="bg-white rounded-2xl shadow-card p-5">
          <div class="flex items-center gap-2 mb-4">
            <div class="w-1.5 h-4 bg-bilibili-pink rounded-full"></div>
            <span class="text-sm font-bold text-text-primary">控制面板</span>
            <span class="ml-auto text-xs text-text-tertiary">实时调参</span>
          </div>

          <div class="space-y-4">
            <!-- Style -->
            <div>
              <label class="text-xs text-text-tertiary mb-1.5 block">风格 Style</label>
              <select v-model="style" class="w-full bg-gray-50 border border-border-light rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-bilibili-blue">
                <option value="douyin_sad">💧 抖音伤感</option>
                <option value="rap">🎤 说唱 Rap</option>
                <option value="emo_pop">🔥 Emo流行</option>
                <option value="pop">💗 流行 Pop</option>
                <option value="modern">🌙 现代诗</option>
                <option value="classical">🏯 古典</option>
                <option value="imagist">✨ 意象派</option>
                <option value="diary">📖 日记体</option>
              </select>
            </div>

            <!-- Expression -->
            <div>
              <label class="text-xs text-text-tertiary mb-1.5 block">表达方式</label>
              <select v-model="expression" class="w-full bg-gray-50 border border-border-light rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-bilibili-blue">
                <option value="">自动</option>
                <option value="direct">💬 直接</option>
                <option value="metaphor">🌹 隐喻</option>
                <option value="self_mock">😏 自嘲</option>
              </select>
            </div>

            <!-- Lyric Density -->
            <div>
              <label class="text-xs text-text-tertiary mb-1.5 block">
                句长风格
                <span class="text-bilibili-blue font-medium">{{ lyricDensity || '自动' }}</span>
              </label>
              <select v-model="lyricDensity" :disabled="mode === 'poem'"
                      class="w-full bg-gray-50 border border-border-light rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-bilibili-blue disabled:opacity-50">
                <option value="">自动</option>
                <option value="short">短句 Short</option>
                <option value="medium">中等 Medium</option>
                <option value="long">长句 Long</option>
              </select>
            </div>

            <!-- Sliders row -->
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="text-xs text-text-tertiary mb-1.5 flex justify-between">
                  <span>情绪强度</span>
                  <span class="text-bilibili-blue font-bold">{{ intensity }}</span>
                </label>
                <input type="range" v-model="intensity" min="0" max="1" step="0.1"
                       class="w-full accent-bilibili-blue" />
              </div>
              <div>
                <label class="text-xs text-text-tertiary mb-1.5 flex justify-between">
                  <span>Beam Width</span>
                  <span class="text-bilibili-blue font-bold">{{ beamWidth }}</span>
                </label>
                <input type="range" v-model="beamWidth" min="1" max="4" step="1"
                       class="w-full accent-bilibili-blue" />
              </div>
              <div>
                <label class="text-xs text-text-tertiary mb-1.5 flex justify-between">
                  <span>最大优化</span>
                  <span class="text-bilibili-blue font-bold">{{ maxRefine }}</span>
                </label>
                <input type="range" v-model="maxRefine" min="0" max="5" step="1"
                       class="w-full accent-bilibili-blue" />
              </div>
              <div>
                <label class="text-xs text-text-tertiary mb-1.5 flex justify-between">
                  <span>候选数</span>
                  <span class="text-bilibili-blue font-bold">{{ candidates }}</span>
                </label>
                <input type="range" v-model="candidates" min="1" max="6" step="1"
                       class="w-full accent-bilibili-blue" />
              </div>
            </div>

            <!-- Explain toggle -->
            <label class="flex items-center gap-2.5 cursor-pointer py-1">
              <input type="checkbox" v-model="explain"
                     class="w-4 h-4 rounded border-border-light bg-gray-50 text-bilibili-blue focus:ring-bilibili-blue/30" />
              <span class="text-sm text-text-secondary">显示创作说明</span>
            </label>
          </div>
        </div>
      </div>

      <!-- Right: Results -->
      <div class="lg:col-span-8 flex flex-col gap-4">

        <!-- Pipeline Live View -->
        <LivePipeline v-if="loading || pipelineSteps.length > 0" :steps="pipelineSteps" />

        <!-- Final Results -->
        <ResultComparison v-if="result" :result="result" />

        <!-- Explanation -->
        <ExplanationPanel v-if="result && result.explanation" :explanation="result.explanation" />

        <!-- Empty state -->
        <div v-if="!loading && pipelineSteps.length === 0 && !result"
             class="bg-white rounded-2xl shadow-card p-12 flex flex-col items-center gap-5 text-center">
          <div class="w-20 h-20 rounded-2xl bg-bilibili-blue/10 flex items-center justify-center">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" class="text-bilibili-blue">
              <path d="M9 18V5l12-2v13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="6" cy="18" r="3" fill="currentColor"/>
              <circle cx="18" cy="16" r="3" fill="currentColor"/>
            </svg>
          </div>
          <div>
            <p class="text-text-primary font-medium text-base">GenWriter Agent</p>
            <p class="text-text-tertiary text-sm mt-1">输入文本，选择参数</p>
            <p class="text-text-tertiary text-xs mt-0.5">点击「生成」启动创作管线</p>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import LivePipeline from './components/LivePipeline.vue'
import ResultComparison from './components/ResultComparison.vue'
import ExplanationPanel from './components/ExplanationPanel.vue'

const inputText = ref('')
const mode = ref('lyrics')
const style = ref('douyin_sad')
const expression = ref('')
const lyricDensity = ref('')
const intensity = ref(0.8)
const beamWidth = ref(2)
const maxRefine = ref(0)
const candidates = ref(1)
const explain = ref(true)

const loading = ref(false)
const pipelineSteps = ref([])
const result = ref(null)
const llmStatus = ref('unknown')
const llmStatusText = ref('LLM 状态')
const llmLoading = ref(false)

async function testLLM() {
  llmLoading.value = true
  llmStatusText.value = '测试中...'
  try {
    const resp = await fetch('/api/test_llm')
    const data = await resp.json()
    if (data.status === 'success') {
      llmStatus.value = 'ok'
      llmStatusText.value = 'LLM 正常'
    } else {
      llmStatus.value = 'error'
      llmStatusText.value = 'LLM 失败'
    }
  } catch {
    llmStatus.value = 'error'
    llmStatusText.value = '网络错误'
  } finally {
    llmLoading.value = false
  }
}

async function generate() {
  if (!inputText.value.trim() || loading.value) return

  loading.value = true
  pipelineSteps.value = []
  result.value = null

  const payload = {
    text: inputText.value,
    mode: mode.value,
    style: style.value || undefined,
    intensity: intensity.value,
    expression: expression.value || undefined,
    lyric_density: lyricDensity.value || undefined,
    beam_width: parseInt(beamWidth.value),
    candidates: parseInt(candidates.value),
    max_refine_steps: parseInt(maxRefine.value),
    explain: explain.value,
  }

  try {
    const resp = await fetch('/api/generate/stream', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    })

    if (!resp.ok) {
      const err = await resp.text()
      throw new Error(`HTTP ${resp.status}: ${err}`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // 按 SSE 事件分割（data: ...\n\n）
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''  // 不完整的行留在 buffer

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const evt = JSON.parse(line.slice(6))
          if (evt.step === 'error') throw new Error(evt.msg)

          // 分发步骤（去重更新）
          const existing = pipelineSteps.value.findIndex(
            s => s.step === evt.step && (evt.data?.candidate === undefined || s.data?.candidate === evt.data?.candidate)
          )
          if (existing >= 0) {
            pipelineSteps.value[existing] = evt
          } else {
            pipelineSteps.value.push(evt)
          }

          if (evt.step === 'final') {
            result.value = evt.data
          }
        } catch (parseErr) {
          if (parseErr.message !== '') console.warn('Parse error:', parseErr)
        }
      }
    }
  } catch (err) {
    console.error('Generate failed:', err)
    pipelineSteps.value.push({ step: 'error', msg: '生成失败: ' + err.message })
  } finally {
    loading.value = false
  }
}
</script>
