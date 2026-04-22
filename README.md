# WeChatChat2Lyric-Agent 使用说明

## 一、项目简介

**WeChatChat2Lyric-Agent** 是一个基于 LangChain Agent 框架的智能歌词生成工具。通过读取本地导出的微信聊天记录，自动完成数据清洗、情感分析、关键词提取，最终生成符合指定曲风的原创歌词。

## 二、功能特点

- 读取本地微信聊天记录（.txt格式）
- 自动清洗冗余数据（时间戳、系统提示等）
- 智能分析情感类型和核心关键词
- 支持多种曲风：流行、民谣、说唱、抒情、摇滚
- 生成押韵、符合歌曲结构的原创歌词
- 轻量化依赖，仅需 LLM API Key 即可使用

## 三、环境配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

**方式一：创建 .env 文件（推荐）**

在项目根目录创建 `.env` 文件：

```
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1
MODEL_NAME=gpt-3.5-turbo
```

**方式二：直接编辑代码**

编辑 `chat2lyric_agent.py` 中的配置区：

```python
API_KEY = "your-api-key-here"  # 填入您的 API Key
API_BASE = "https://api.openai.com/v1"  # API 地址
MODEL_NAME = "gpt-3.5-turbo"  # 模型名称
```

### 3. 支持的模型

支持所有 OpenAI 格式的 API，包括：
- OpenAI GPT-3.5 / GPT-4
- 国产大模型（需兼容 OpenAI 格式）
- 自建大模型 API

## 四、导出微信聊天记录

### 手机端导出教程

1. 打开微信，进入目标对话
2. 点击右上角「...」→「查找聊天记录」
3. 选择「日期」，筛选要导出的时间段
4. 长按任意消息 → 「更多」→ 全选
5. 点击右下角「分享」→ 「保存为文本」

### 电脑端导出教程

1. 登录微信电脑版
2. 打开目标对话
3. 点击右上角「...」→「导出聊天记录」
4. 选择「全部消息」→「txt格式」→「导出」

## 五、使用方法

### 方式一：交互式命令行

```bash
python chat2lyric_agent.py
```

### 方式二：指定文件路径

```bash
python chat2lyric_agent.py path/to/chat.txt
```

### 方式三：指定曲风

```bash
python chat2lyric_agent.py path/to/chat.txt 摇滚
```

曲风选项：流行、民谣、说唱、抒情、摇滚

### 方式四：运行演示

```bash
python chat2lyric_agent.py --demo
```

## 六、API 配置教程

### OpenAI API

1. 访问 https://platform.openai.com/api-keys
2. 登录并创建 API Key
3. 在 .env 文件中配置

### 国产大模型配置示例

**智谱 GLM：**
```
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://open.bigmodel.cn/api/paas/v4
MODEL_NAME=glm-4
```

**百度文心：**
```
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://aip.baidubce.com/rpc/2.0/ai_custom/v1
MODEL_NAME=ernie-4.0-8k
```

## 七、注意事项

1. **API Key 安全**：不要将 API Key 提交到公开仓库
2. **内容质量**：聊天记录越丰富，生成的歌词越准确
3. **曲风选择**：不同曲风会影响歌词的节奏和用词
4. **网络连接**：需要稳定的网络连接来调用 LLM API
