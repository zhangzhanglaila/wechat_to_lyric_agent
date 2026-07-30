# Roadmap

这个路线图围绕一个目标：让项目从“可运行原型”变成“路人看完 README 就愿意试、试完愿意 star 的中文 AI 音乐工具”。

## P0: 开源可信度

- 清理误提交的 `node_modules`、生成音频、临时输出和本地配置。
- 补全 `LICENSE`、干净 `.gitignore`、可复现安装文档。
- 在 README 第一屏放清晰卖点、启动方式、输入输出示例。
- GitHub 仓库设置 topics：`ai-music`, `lyrics-generator`, `wechat`, `song-generator`, `fastapi`, `vue`, `sse`。

## P1: 微信聊天转歌主流程

- 支持微信导出的 `.txt` 聊天记录解析。
- 自动识别说话人、时间线、关键词和情绪变化。
- 输出“故事摘要 + 情绪曲线 + 歌词初稿 + Hook”。
- 前端首页默认围绕“聊天记录 -> 歌词 -> 歌曲”，把工程参数收进高级设置。

## P2: 可传播 Demo

- 提供 3-5 个脱敏聊天样例。
- 每个样例包含：原始片段、生成歌词、生成音频、风格参数、耗时。
- README 增加 GIF、截图和音频试听链接。
- 发布 GitHub Release，附带 demo 输出文件。

## P3: 歌词质量

- 押韵控制：尾韵、内韵、隔行押韵。
- Hook 强化：副歌重复度、记忆点、短视频传播感。
- 风格模板：说唱 diss、毕业季、告白、分手、旅行、朋友局、日记体。
- 结果对比：Simple / Advanced / Baseline 三栏对比。

## P4: 部署和模型

- Docker Compose 一键启动。
- 支持 OpenAI、DeepSeek、Qwen、Ollama 的配置模板。
- 提供本地隐私模式说明。
- 增加健康检查和端到端 smoke test。
