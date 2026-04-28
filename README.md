# GenWriter Agent

**A controllable lyric & poetry generation system powered by LLM + search optimization.**

把聊天记录 / 关键词 / 情绪，自动变成一首有感染力的歌词或诗歌。

> 本质：将文本创作建模为 **搜索问题**，通过 DSL 约束 + 候选生成 + 束搜索优化，实现可控的歌词与诗歌生成。

---

## 架构

```
User Input
    ↓
Emotion Modeling
    ↓
DSL (User Editable)  ← 用户可编辑结构
    ↓
Constrained Generation (N candidates)
    ↓
Hook Optimization (multi-variant + scoring)
    ↓
Beam Search Refinement (LLM + ops space)
    ↓
Final Output + Creation Explanation
```

---

## 核心能力

### 双模式生成

```bash
# 歌词模式
python chat2lyric_agent.py --input chat.txt --mode lyrics --style douyin_sad

# 诗歌模式
python chat2lyric_agent.py --input keywords.txt --mode poem --style modern
```

### 用户可控维度

| 维度 | 选项 |
|------|------|
| `mode` | `lyrics` / `poem` |
| `style` | `douyin_sad` `rap` `emo_pop` `modern` `classical` `imagist` `diary` |
| `expression` | `direct` / `metaphor` / `self_mock` |
| `lyric_density` | `short` / `medium` / `long` |
| `intensity` | 0.0 ~ 1.0 |
| `beam_width` | 2 ~ 4（越大优化路径越多） |
| `weights` | 自定义目标函数权重 |

### DSL 外显（用户可编辑结构）

```python
structure = [
    {"section": "intro",   "intent": "场景设定"},
    {"section": "verse",   "intent": "叙述关系变化"},
    {"section": "hook",    "intent": "核心记忆点"},
]
result = eos.generate(content, mode="lyrics", constraints={"structure": structure})
```

---

## Baseline 对比

用 `--baseline` 开关对比"无优化链的原始生成" vs "完整管线"：

```bash
python chat2lyric_agent.py --input chat.txt --mode lyrics --baseline --explain
```

输出示例：

```
========================================================
  Baseline（无优化链的原始 LLM 生成）
========================================================

【歌词】
...（较差的结果）

========================================================
  优化后（完整管线）
========================================================

【歌词】
...（明显更好的结果）

【对比】Baseline 0.31  ↑  System 0.79  (Δ +0.48)
```

---

## 创作说明（可解释）

加 `--explain` 开关，输出创作过程：

```bash
python chat2lyric_agent.py --input keywords.txt --mode poem --explain
```

```
【创作说明】
------------------------------------------------------------
  情绪演化  : sadness (0.8)
  表达方式  : direct
  句长风格  : short
  Hook策略  : 洗脑 Hook（重复3次），高复述性
  优化步数  : 3
  ──────────────────
    Step 1: [hook_weak] → rewrite_hook
    Step 2: [too_flat] → shorten_lines
    Step 3: [no_imagery] → add_imagery

【分数】
  Total   : 0.79
  ─────   : ──────
  hook_strength    : ████████░░ 0.82
  lyric_variation  : ██████░░░░ 0.61
  emotion_consistency: ███████░░░ 0.71
  singability      : ██████░░░░ 0.58
```

---

## 完整示例

```bash
python chat2lyric_agent.py \
  --input "思念 远方的你 分手" \
  --mode lyrics \
  --style douyin_sad \
  --intensity 0.8 \
  --candidates 3 \
  --beam-width 2 \
  --explain \
  --show-candidates \
  --baseline
```

---

## 文件结构

```
agent_os/
  art_layer.py      # EmotionEngine / HookGenerator / StyleTemplate / NarrativeBuilder
  integration.py   # EnhancedAgentOS / HookOptimizer / TextAnalyzer /
                   # RefineLoop(beam search) / ObjectiveFunction / StyleChecker
chat2lyric_agent.py  # CLI 入口
requirements.txt
```

---

## 依赖

```
openai>=1.0.0
python-dotenv>=1.0.0
```

---

## 核心设计思想

本项目的本质是 **Iterative Structured Generation System**：

1. **Emotion → DSL**：情绪向量生成结构化意图
2. **DSL → 强约束生成**：每行按 intent + section 约束生成，而非自由发挥
3. **多候选 + HookOptimizer**：生成多个 Hook 变体，评分选最优
4. **Beam Search Refine**：多步束搜索，动态 LLM 提议操作
5. **Objective - Penalty**：目标函数驱动的优化，风格一致性约束

这使得系统从"调 API 生成工具"进化为"可控创作 Agent"。
