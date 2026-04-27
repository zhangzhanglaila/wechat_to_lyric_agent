# GenWriter Agent - 歌词/诗歌生成引擎

**把聊天记录/情绪/关键词，自动变成一首有感染力的歌词或诗**

> 核心定位：不是"AI写作"，而是"情绪驱动的创作过程建模"

---

## 一句话定义

输入：聊天记录 / 关键词 / 情绪描述
输出：歌词（主歌/副歌/Hook结构）或 诗歌（现代/古典/意象派/日记体）

---

## 架构（v12.x）

```
输入
  ↓
ChatCompressionLayer（聊天记录 → 情绪单元）
  ↓
EmotionEngine（情绪 → EmotionVector）
  ↓
StructureDSLGenerator（Emotion + Style → 结构化意图）
  ↓
TextGenerator（DSL → 各节/行文本）
  ↓
HumanRewriteLayer（去除AI感）
  ↓
HookGenerator（爆款Hook句）
  ↓
CandidateScorer（多候选 + 评分 + Kill规则）
  ↓
输出：歌词 / 诗歌 + Hook + 评分
```

---

## 核心能力

### 1. 双模式生成

```bash
# 歌词模式（主歌+副歌+Hook，可唱结构）
python chat2lyric_agent.py --input chat.txt --mode lyrics --style douyin_sad

# 诗歌模式（多体裁：现代/古典/意象派/日记体）
python chat2lyric_agent.py --input keywords.txt --mode poem --style modern
```

### 2. 风格系统

| 风格 | 描述 | 适用场景 |
|------|------|---------|
| douyin_sad | 抖音伤感风，副歌强Hook | 失落/离别情绪 |
| rap | 强节奏，快韵脚 | 愤怒/宣泄 |
| pop | 流行情歌，朗朗上口 | 甜蜜/思念 |
| emo | 情绪激烈，摇滚感 | 深夜独白 |
| modern | 现代诗，自由分行 | 文艺表达 |
| classical | 古典押韵，格律感 | 国风/文言 |
| imagist | 意象派，短句强画面 | 朦胧情感 |
| diary | 日记体，第一人称 | 私密倾诉 |

### 3. 多候选 + 评分

默认生成 3 个候选，通过评分排序：
- 歌词：hook_strength / lyric_variation / emotion_consistency / singability
- 诗歌：imagery_density / novelty / coherence / emotional_depth

**Kill规则**：某项过低直接大幅扣分，避免bad case

```bash
# 显示所有候选
python chat2lyric_agent.py --input chat.txt --mode lyrics --show-candidates
```

### 4. Structure DSL

情绪 + 风格 → 结构化意图 → 文本

**歌词DSL节类型**：intro / verse / pre_hook / hook / outro
**诗歌DSL行类型**：image / feeling / contrast / closure

### 5. 可迭代优化

```python
from agent_os.integration import EnhancedAgentOS

eos = EnhancedAgentOS()
result = eos.generate(
    content=chat_messages,  # list 或 str
    mode="lyrics",
    style="douyin_sad",
    constraints={"intensity": 0.8},
    num_candidates=3,
)
print(result.text)       # 主结果
print(result.hook)       # 爆款Hook句
print(result.candidates)  # 所有候选
print(result.score)      # 综合评分
```

---

## 文件结构

```
agent_os/
  art_layer.py      # 17个核心类（Emotion/Hook/Style/Narrative）
  integration.py    # EnhancedAgentOS + StructureDSL + Scorer
chat2lyric_agent.py # CLI入口
requirements.txt    # 依赖
```

---

## 依赖

```
openai>=1.0.0
python-dotenv>=1.0.0
```

---

## License

MIT