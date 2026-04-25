# 🎤 微信聊天记录 → AI歌词生成器

**把任何聊天记录，自动变成一首可以唱的歌**

> 💡 不仅仅是歌词生成器，而是一个「情绪驱动的内容创作引擎」

---

## 🎯 一句话定义

输入微信聊天记录，输出：
- 🎵 **歌词**（有画面感、有Hook、结构完整）
- 🔊 **有声作品**（TTS + BGM）
- 🎼 **旋律规划**（MelodyPlan → 可接 DiffSinger）

---

## 🔄 演进路径

| 版本 | 架构 | 核心能力 |
|------|------|---------|
| v7.x | Agent OS + ArtPipeline | 人格化歌词生成 |
| v8.x | HumanRewriteLayer + HookGenerator | 去除AI感，增加传播性 |
| v9.x | SemanticFrame + NarrativeBuilder | 从"改写"升级为"语义叙事" |
| **v9.6-v9.9** | **画面化 + Hook强化 + MelodyPlanner** | **从"能跑"到"可传播"** |

---

## 🏗️ System Architecture（v9.9）

```
微信聊天记录
    ↓
ChatCompression（情绪提取）
    ↓
SemanticFrame（语义帧构建）
    ↓
NarrativeBuilder（叙事骨架 + 画面化）
    ↓
┌─────────────────────────────────────────┐
│  MelodyPlanner（v9.9 新增）              │
│  情绪 → 调式/BPM → 音符序列             │
│  输出 MelodyPlan（IR 层）                │
└─────────────────────────────────────────┘
    ↓
HumanRewriteLayer（人格化改写）
    ↓
HookGenerator（爆款句生成）
    ↓
┌─────────────────────────────────────────┐
│  AudioLayer（v9.8 新增）                │
│  TTS + BGM + 合成音频                   │
└─────────────────────────────────────────┘
    ↓
最终输出（歌词 + 音频 + MelodyPlan）
```

---

## 🎵 Demo 示例

**输入（微信聊天）：**
```
小明：你怎么不回我
小红：（已读）
小明：你到底怎么了
```

**输出歌词（v9.7）：**
```
[开场] 你开始不回消息
[主歌1] 只有我一个人在撑着
[主歌1] 好像只有我一个人在乎这段关系
[主歌1] 看着那句话 我发了很久的呆
[转折] 不是距离远了
        是心远了
[结尾] 原来已经回不去了
```

**输出 MelodyPlan（v9.9）：**
```
key: A_minor, bpm: 70
MIDI events:
  (0.0, 'D5', 0.5, '你')
  (0.5, 'B4', 0.5, '不')
  (1.0, 'G5', 0.5, '是')
  ...
```

---

## 🔑 核心升级点（v9.x）

### v9.6 画面化升级
- `VISUAL_TEMPLATES`：画面句替代解释句
- `IMAGERY`：意象词库增强身临其境感
- 相邻行去重（去除句内重复感）

### v9.7 Hook强化
- `HOOK_TEMPLATES`：按 core 分组的爆款候选句
- frame-conditioned turning（非随机）
- 两行结构 punch line（视觉冲击）

### v9.8 Audio Layer
- `AudioLayer.synthesize()`：TTS + BGM → 完整音频
- 情绪 → 音色/BGM 映射
- `EnhancedAgentOS.synthesize_audio()`：一键端到端

### v9.9 Melody Layer
- `MelodyPlanner.plan()`：歌词 → MelodyPlan
- 情绪 → 调式/BPM 映射（sadness→A_minor/70bpm）
- `to_midi_events()`：MIDI 事件流（供 DiffSinger 使用）
- Hook 句使用重复型旋律（制造洗脑感）

---

## 🚀 Quick Start

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 生成歌词（交互）
python chat2lyric_agent.py

# 生成歌词 + 音频
python -c "
from agent_os.integration import EnhancedAgentOS
eos = EnhancedAgentOS()
result = eos.synthesize_audio(chat_messages, output_path='output/song.mp3')
print(result['lyrics'])
print('Audio:', result['audio_output'])
"
```

---

## 📦 依赖

```
openai>=1.0.0
python-dotenv>=1.0.0
edge-tts>=6.1.0        # TTS（中文语音合成）
moviepy>=1.0.3         # 音频合成
Pillow>=9.0.0          # 图像处理（后续视频用）
```

---

## 🎯 适合谁用？

- 🎤 把聊天记录变成礼物的人
- 🎵 内容创作者寻找灵感
- 📱 想要生成「可传播内容」的项目
- 🧠 对「情绪驱动创作引擎」感兴趣的技术人

---

## 📍 下一步演进

```
v9.9（当前）
  MelodyPlanner（规则生成）
      ↓
v10
  接 DiffSinger / So-VITS-SVC（真唱）
  或 pitch-controlled TTS（伪唱）
      ↓
v11
  Hook melody reuse（副歌洗脑）
  节奏 pattern（抖音风）
  MV Generator（字幕 + 画面）
```

---

## 📖 License

MIT
