# WeChat2Song / GenWriter Agent

把微信聊天记录、关键词或一段故事，一键生成中文歌词，并继续合成可播放的 AI 歌曲 demo。  
Turn WeChat chat logs, keywords, or a short story into Chinese lyrics, then synthesize a playable AI song demo.

> 当前项目包含：FastAPI 后端、Vue Web UI、SSE 流式歌词生成、情绪/风格控制、歌词评分、多候选优化、歌词到 MIDI/TTS/混音的歌曲生成链路。  
> This project includes a FastAPI backend, Vue Web UI, SSE streaming generation, emotion/style controls, lyric scoring, multi-candidate optimization, and a lyrics-to-MIDI/TTS/mixing song pipeline.

## 为什么值得试 / Why Try It

- **聊天记录转歌词**：输入微信式聊天文本，自动提取人物关系、情绪和故事线，生成口语化中文歌词。  
  **Chat logs to lyrics**: Paste WeChat-style conversations and generate conversational Chinese lyrics from the relationship, emotion, and story.

- **歌词继续变歌曲**：生成歌词后点击 `Sing`，走旋律生成、MIDI、TTS/合成歌声、混音，输出可播放 WAV。  
  **Lyrics to song**: After lyrics are generated, click `Sing` to create melody, MIDI, TTS/synthetic vocals, mixing, and a playable WAV file.

- **实时可见**：歌词和歌曲生成过程都通过 SSE 推送，前端能看到 token、pipeline 步骤、耗时和错误信息。  
  **Live feedback**: Both lyric and song generation stream progress through SSE, including tokens, pipeline steps, latency, and errors.

- **双模式生成**：Simple Mode 默认快速返回；Advanced Mode 提供多候选、重排和精修。  
  **Two generation modes**: Simple Mode is fast by default; Advanced Mode enables multi-candidate generation, ranking, and refinement.

- **适合中文场景**：内置抖音伤感、中文说唱、Emo 流行、现代诗、古典、日记体等风格。  
  **Built for Chinese scenarios**: Includes styles such as Douyin sad pop, Chinese rap, emo pop, modern poetry, classical poetry, and diary-like writing.

## 效果预览 / Preview

输入可以是普通关键词，也可以是聊天记录：  
The input can be plain keywords or chat logs:

```text
小明：新年快乐，今年是我们在一起的第三年了
小红：记得第一次见面是在咖啡店
小明：你当时穿了一条白裙子
小红：下周一起去看樱花吧
```

生成链路：  
Generation pipeline:

```text
微信聊天记录 / 关键词
WeChat chat logs / keywords
  -> 情绪与主题提取 / emotion and theme extraction
  -> 中文歌词生成 / Chinese lyric generation
  -> Hook / 结构评分 / hook and structure scoring
  -> 旋律生成 / melody generation
  -> MIDI + 人声/TTS / MIDI + vocals/TTS
  -> 混音输出 WAV / mixed WAV output
```

仓库内提供了一个示例输入：[example_chat.txt](example_chat.txt)。  
A sample input is included in this repository: [example_chat.txt](example_chat.txt).

## 快速开始 / Quick Start

### 1. 配置模型 / Configure Model

复制环境变量示例：  
Copy the environment template:

```bash
cp .env.example .env
```

修改 `.env`：  
Edit `.env`:

```env
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat
```

也可以切到 OpenAI 或其他兼容 OpenAI SDK 的服务。  
You can also switch to OpenAI or any OpenAI SDK-compatible provider.

### 2. 安装后端依赖 / Install Backend Dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 安装前端依赖 / Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

### 4. 启动服务 / Start Server

```bash
python -m backend.main
```

打开：  
Open:

```text
http://localhost:8000
```

接口文档：  
API docs:

```text
http://localhost:8000/docs
```

如果前端没有显示，请先构建：  
If the frontend is not served, build it first:

```bash
cd frontend
npm run build
cd ..
python -m backend.main
```

开发前端时可以单独运行：  
For frontend development:

```bash
cd frontend
npm run dev
```

## API 示例 / API Examples

### 流式生成歌词 / Stream Lyrics

```http
POST /api/generate/stream
Content-Type: application/json
```

```json
{
  "text": "分手后的微信聊天记录，最后一句是再也不见",
  "mode": "lyrics",
  "style": "rap",
  "advanced_mode": false
}
```

### 歌词生成歌曲 / Generate Song From Lyrics

```http
POST /api/sing/stream
Content-Type: application/json
```

```json
{
  "lyrics": "窗外的麻雀 在电线杆上多嘴\n你说这一句 很有夏天的感觉",
  "style": "rap",
  "mode": "full",
  "instrumental_volume": 0.4,
  "vocal_volume": 0.8
}
```

返回的 final event 会包含：  
The final event includes:

```json
{
  "audio_url": "/api/sing/audio/<filename>.wav",
  "filename": "<filename>.wav"
}
```

## 模式说明 / Modes

| 模式 / Mode | 适合场景 / Best For | 特点 / Notes |
|---|---|---|
| Simple Mode | 默认体验、演示、低延迟 / default use, demos, low latency | 单次 LLM，SSE 流式输出，优先快速可用 / one LLM call, SSE streaming, optimized for speed |
| Advanced Mode | 质量对比、研究、调参 / quality comparison, research, tuning | Emotion -> DSL -> 多候选 -> Rank -> Refine / Emotion -> DSL -> candidates -> rank -> refine |
| Sing | 歌词转歌曲 demo / lyrics-to-song demo | 旋律、MIDI、TTS/合成歌声、混音、音频下载 / melody, MIDI, TTS/synthetic vocals, mixing, audio download |

## 项目结构 / Project Structure

```text
backend/
  main.py                  # FastAPI 入口 / FastAPI entry
  api/generate.py          # 歌词/诗歌生成 API / lyric/poem generation API
  api/sing.py              # 歌词转歌曲 API / lyrics-to-song API
  services/generator.py    # Simple / Advanced 生成调度 / generation orchestration
  services/singer.py       # 旋律、MIDI、TTS、混音调度 / melody, MIDI, TTS, mixing orchestration

frontend/
  src/App.vue              # Web UI 主界面 / main Web UI
  src/components/          # pipeline、结果、评分、说明组件 / pipeline, result, score, explanation components

agent_os/
  art_layer.py             # LLM、风格模板、情绪对象 / LLM, style templates, emotion objects
  integration.py           # Advanced Mode pipeline
  melody_generator.py      # 旋律生成 / melody generation
  audio_engine.py          # MIDI、TTS、混音 / MIDI, TTS, mixing
```

## 隐私说明 / Privacy

本项目适合本地运行。聊天记录只会在你本机服务和你配置的模型 API 之间流转；如果你处理真实聊天记录，请先脱敏姓名、电话、地址、账号和私密内容。  
This project is designed for local use. Chat logs only flow between your local server and the model API you configure. If you process real conversations, remove names, phone numbers, addresses, accounts, and private content first.

## 当前限制 / Limitations

- 歌曲生成是 demo 级，不等同于 Suno/Udio 级商业音乐生成。  
  Song generation is demo-level and not comparable to commercial systems such as Suno or Udio.

- TTS 演唱自然度依赖 `edge-tts`、音高切片和混音质量。  
  Vocal naturalness depends on `edge-tts`, pitch slicing, and mixing quality.

- Advanced Mode 成本和延迟明显高于 Simple Mode。  
  Advanced Mode costs more and is slower than Simple Mode.

- 微信聊天记录解析目前偏文本输入，后续会补更严格的导入格式解析。  
  WeChat chat parsing currently focuses on plain text input; stricter import format support is planned.

## Roadmap

详见 [ROADMAP.md](ROADMAP.md)。  
See [ROADMAP.md](ROADMAP.md).

近期重点：  
Near-term focus:

- 微信聊天 `.txt/.csv/.json` 导入解析  
  WeChat `.txt/.csv/.json` import parsing

- 在线 demo / 截图 / 音频样例  
  Online demo, screenshots, and audio samples

- Docker Compose 一键启动  
  One-command startup with Docker Compose

- 本地模型适配：Ollama / Qwen / DeepSeek / OpenAI  
  Local/provider model adapters: Ollama / Qwen / DeepSeek / OpenAI

- 歌词押韵控制、Hook 强化、风格模板市场  
  Rhyme control, stronger hooks, and a style-template marketplace

## License

MIT License. See [LICENSE](LICENSE).  
MIT License. See [LICENSE](LICENSE).
