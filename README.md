# 🎤 微信聊天记录 → AI歌词生成器

✨ **把任何聊天记录，自动变成一首可以唱的歌**

🧠 一个**不会"越改越差"**的 AI 写作系统

> 💡 Not just a lyric generator — it's a system that prevents AI from breaking itself.

---

## 💡 一句话定义

让 AI 像人一样"改作文"：

👉 **只改坏的部分，而不是重写整篇**

---

## 😵 AI 写歌词的真实问题

**普通 AI（无限退化）：**
```
Iteration 1 → 基础版本
Iteration 2 → 改了一处，坏了两处
Iteration 3 → 回退重写
Iteration 4 → 彻底崩溃
```
👉 **结果：全靠运气**

---

**本项目（收敛控制）：**
```
Iteration 1 → 6.8分 baseline
Iteration 2 → 锁住好的，只修押韵 → 7.5分
Iteration 3 → 锁住好的，只修情感 → 8.2分 ✅
```
👉 **结果：稳定收敛**

---

## 🎵 Demo 示例

**输入（微信聊天记录）：**
```
小明：亲爱的，新年快乐！
小红：新年快乐呀～今年是我们在一起的第三年了
小明：是啊，时间过得好快
小红：记得我们第一次见面是在咖啡店
小明：你当时穿了一条白裙子
小红：你还记得呀，你当时紧张得话都说不清楚
...
```

**收敛过程：**

| 迭代 | 分数 | 操作 |
|------|------|------|
| 第1轮 | 6.8/10 | 生成初版 |
| 第2轮 | 7.5/10 | 差分修复押韵 |
| 第3轮 | 8.2/10 | 收敛完成 ✅ |

**最终输出：**
```
[主歌1]
那天的咖啡店 你穿着白裙
我紧张得说不清 只记得你的眼睛
三年时光走过 笑过也哭过
每一刻都珍贵 你是我最好的决定

[副歌]
我想带你看日出 在最高的地方说爱你
拉钩上吊一百年 我们的故事继续
```

---

## 🎯 这个项目解决什么问题？

你有没有遇到过这种情况：

❌ 让 AI 修改一首歌词，改完押韵了，但情感没了
❌ AI 反复改，越改越乱，最后还不如第一版
❌ 想要的效果和 AI 理解的不一样，沟通成本很高

**本项目做了什么：**

传统 AI 生成是"整段重写"，改一处动全身。

我们实现了四个机制来解决这个问题：

| 机制 | 通俗理解 |
|------|---------|
| **约束冻结** | AI 改文章时，"写得好的地方自动锁住，不让动" |
| **差分编辑** | 不是整段重写，而是"只改有问题的那个句子" |
| **全局优化** | 统一衡量押韵、情感、节奏，而不是只优化一个 |
| **元学习** | AI 会"学习历史经验"，知道哪些修复是有效的 |

**最终效果：2-3轮稳定收敛，输出质量可控。**

---

## 🔧 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Chat Input                               │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  [Cleaner] → [Analyzer] → [Planner] → [Generator]           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                 Self-Optimizing Loop                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Constraint  │  │    Diff     │  │   Global    │         │
│  │    Lock     │  │   Editor    │  │  Optimizer  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                          │                                  │
│                   ┌──────┴──────┐                           │
│                   │  MetaAgent  │                           │
│                   └─────────────┘                           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   Final Output                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧠 What is This?

A multi-agent system that turns chat history into structured lyrics.

Unlike typical LLM pipelines, it introduces **convergence-aware generation**:

- it does not endlessly regenerate
- it selectively edits
- it stabilizes output quality over iterations

---

## 📊 Architecture Evolution

| Version | Architecture | Key Innovation |
|---------|-------------|----------------|
| v3.0 | Linear State Machine | Pipeline + Verifier |
| v4.0 | Graph-based DAG | Conditional Routing + Targeted Repair |
| **v5.0** | **Self-Optimizing System** | **Convergence Control + Meta Learning** |

---

## 🌟 Applicable Scenarios

This convergence control architecture is applicable to:

- 📝 Story generation & refinement
- 💻 Code generation & bug fixing
- 🎯 Agent planning loops
- 🧠 Multi-step reasoning systems
- 🎵 Any multi-iteration generative pipeline

---

## ⚠️ Engineering Note

This system improves stability, but does not eliminate LLM variance entirely. Results may vary between runs. The optimization loop is designed to **minimize variance and converge toward quality**, not guarantee identical output every time.

---

## 🚀 Quick Start

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 运行演示
python chat2lyric_agent.py --demo

# 交互模式
python chat2lyric_agent.py
```

### 支持的曲风

流行 / 民谣 / 说唱 / 抒情 / 摇滚

---

## 🧩 适合谁用？

- 🎤 对歌词创作感兴趣的个人
- 🎵 内容创作者寻找灵感
- 🧠 对 Agent 架构感兴趣的技术人
- 📝 想把聊天记录变成礼物的用户

---

## 🧠 本质

This is not a lyric generator.

This is a **stability layer for generative AI systems**.

---

## 📖 License

MIT
