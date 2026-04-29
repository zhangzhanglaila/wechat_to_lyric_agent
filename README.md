# GenWriter Agent

一个中文歌词 / 诗歌生成系统，核心目标不是堆复杂 pipeline，而是提供一个**默认可用、响应快、可观测**的 LLM 创作服务。

当前架构是双模式：

- **简易模式 Simple Mode**：默认路径，单次 LLM + SSE 流式返回，优先保证响应速度和用户体验。
- **高级模式 Advanced Mode**：可选路径，保留 Emotion → DSL → Generate → Rank → Refine 的多阶段优化链，适合研究和高质量生成。

---

## 功能特性

### 简易模式（默认）

- 快速生成，目标约 10-20 秒内完成
- 单次 LLM 调用
- SSE 流式输出，前端实时显示 token
- Prompt 强约束输入主题，减少跑偏
- 适合大多数用户和演示场景

### 高级模式（可选）

- 多阶段 pipeline：Emotion → DSL → Generate → Rank → Refine
- 支持多候选、重排、一次精修
- 更可控，但更慢，通常约 60-200 秒
- 适合研究、对比实验和高级用户

---

## 架构

```text
Client (Vue)
  ↓ SSE
Backend (FastAPI)
  ├─ Simple Mode（默认）
  │   └─ Prompt 构造 → 单次 LLM Streaming → 实时返回
  │
  ├─ Advanced Mode（可选）
  │   └─ Emotion → DSL → 多候选生成 → Rank → Refine
  │
  └─ Observability
      ├─ step events
      ├─ token stream
      ├─ elapsed latency
      └─ score / candidates
```

默认请求不会进入 AgentOS 复杂链路；只有显式开启 `advanced_mode` 才会走高级 pipeline。

---

## 使用方式

### 1. 启动后端

```bash
python -m backend.main
```

默认服务地址：

```text
http://localhost:8000
```

接口文档：

```text
http://localhost:8000/docs
```

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认进入简易模式，可以在控制面板中切换到高级模式。

---

## API 示例

实际接口前缀是 `/api`。

### 默认：简易模式

```http
POST /api/generate/stream
Content-Type: application/json
```

```json
{
  "text": "我是你爸爸",
  "mode": "lyrics",
  "style": "rap"
}
```

特点：

- `advanced_mode` 默认为 `false`
- 单次 LLM 调用
- 通过 SSE 持续返回 `token` 事件

### 高级模式

```http
POST /api/generate/stream
Content-Type: application/json
```

```json
{
  "text": "我是你爸爸",
  "mode": "lyrics",
  "style": "rap",
  "advanced_mode": true,
  "candidates": 3,
  "max_refine_steps": 1,
  "beam_width": 2
}
```

特点：

- 会进入 AgentOS 多阶段链路
- 支持多候选、评分、排序、精修
- 延迟和成本明显高于简易模式

### 同步接口

```http
POST /api/generate
Content-Type: application/json
```

请求体与 `/api/generate/stream` 相同，但不会逐 token 返回，适合脚本调用。

---

## 前端模式切换

控制面板中提供两个模式：

```text
[ Simple Mode ⚡ ]   [ Advanced Mode ]
```

### Simple Mode

- 默认开启
- 秒级反馈
- 实时显示生成中的正文
- 隐藏候选数、beam width、refine 等复杂参数

### Advanced Mode

- 手动开启
- 展示候选数、beam width、最大优化步数
- 适合需要更高质量或想观察 pipeline 的场景

---

## Prompt 策略

简易模式使用强约束 prompt：

```text
你是一个专业中文歌词创作助手。

【输入主题】
{user_input}

【硬性要求】
- 必须围绕输入语义，不得偏离
- 风格：{style}
- 语言：口语化、有节奏感
- 禁止无故生成伤感情歌
- 不要输出解释、分析、前言

【结构】
【开场】
【主歌】
【Hook】

【输出】
直接输出正文
```

这样可以避免模型默认滑向“伤感情歌”等高频分布。

---

## 性能目标

| 指标 | 目标 |
|---|---|
| 首 token | 尽量 < 2 秒 |
| 简易模式完整生成 | 约 10-20 秒 |
| 默认 LLM 调用次数 | 1 |
| UI 响应 | token 实时展示 |
| 高级模式完整生成 | 约 60-200 秒 |

实际延迟取决于模型服务、网络和输出长度。

---

## 超时与可观测性

后端会为每次生成创建 `request_id`，并在 SSE 事件、最终响应和日志中透出，便于排查问题。

默认超时配置：

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `FAST_PATH_TIMEOUT_SECONDS` | `60` | Simple Mode 总超时 |
| `ADVANCED_PATH_TIMEOUT_SECONDS` | `240` | Advanced Mode 总超时 |

日志为结构化 JSON，包含：

```json
{
  "event": "generation",
  "request_id": "a1b2c3d4e5f6",
  "status": "completed",
  "path": "fast",
  "first_token": 1.42,
  "total_elapsed": 8.76,
  "llm_calls": 1
}
```

前端在失败或超时时会展示明确错误和 `Request ID`，不会一直停留在“生成中”。

---

## 主要文件

```text
backend/
  main.py                  # FastAPI 入口
  api/generate.py          # /api/generate 与 /api/generate/stream
  services/generator.py    # Simple Mode + Advanced Mode 调度
  schemas/generate.py      # 请求 / 响应 schema

frontend/
  src/App.vue              # 主 UI，模式切换与 SSE 消费
  src/components/
    LivePipeline.vue       # 步骤与耗时展示
    ResultComparison.vue   # 结果展示
    ExplanationPanel.vue   # 创作说明

agent_os/
  art_layer.py             # LLM streaming、风格模板、艺术层工具
  integration.py           # Advanced Mode 的 AgentOS pipeline
```

---

## 设计取舍

本项目不把复杂度放在默认路径里。

默认路径追求：

- 稳定
- 快
- 可观测
- 用户能看到实时反馈

高级路径保留：

- 多候选
- rerank
- refine
- DSL / Emotion pipeline

这对应真实工程中的取舍：**fast path 服务大多数请求，slow path 作为可选增强能力。**
