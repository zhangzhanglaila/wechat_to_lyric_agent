"""
WeChatChat2Lyric-Agent v6.0
Multi-Agent Runtime System

架构升级：
- Agent Registry（Agent 注册表）
- Role-Based Agents（角色化 Agent）
- Shared Memory（共享内存）
- Execution Engine（执行引擎）
- Task Queue（任务队列）

类似 AutoGPT / CrewAI 级别架构
"""

import os
import re
import json
import argparse
import time
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv
from openai import OpenAI

# ==================== 配置 ====================
load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1")
)


def llm(prompt: str, temp: float = 0.8) -> str:
    return client.chat.completions.create(
        model=os.getenv("MODEL_NAME", "deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=temp
    ).choices[0].message.content


# ==================== Agent Roles ====================

class AgentRole(Enum):
    PLANNER = "planner"       # 策略规划
    ANALYST = "analyst"       # 情感分析
    WRITER = "writer"         # 歌词创作
    CRITIC = "critic"         # 质量审查
    EDITOR = "editor"         # 编辑修改
    ORCHESTRATOR = "orchestrator"  # 调度中心


@dataclass
class AgentConfig:
    role: AgentRole
    name: str
    description: str
    tools: List[str]
    max_retries: int = 3


# ==================== Shared Memory ====================

class SharedMemory:
    """
    共享内存 - 所有 Agent 可读写
    类似 CrewAI 的 Crew.memory
    """

    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.agents_output: Dict[str, Any] = {}
        self.task_history: List[Dict] = []
        self.iteration: int = 0

    def set(self, key: str, value: Any):
        self.data[key] = value

    def get(self, key: str, default=None) -> Any:
        return self.data.get(key, default)

    def log(self, agent: str, action: str, result: Any, score: float = 0.0):
        self.agents_output[agent] = {"action": action, "result": result, "score": score}
        self.task_history.append({
            "agent": agent,
            "action": action,
            "timestamp": time.time(),
            "score": score
        })

    def get_history(self, agent: str = None) -> List[Dict]:
        if agent:
            return [h for h in self.task_history if h["agent"] == agent]
        return self.task_history

    def get_best_result(self, agent: str) -> Optional[Dict]:
        history = self.get_history(agent)
        if not history:
            return None
        return max(history, key=lambda x: x.get("score", 0))


# ==================== Base Agent ====================

class BaseAgent:
    """Agent 基类"""

    def __init__(self, config: AgentConfig, memory: SharedMemory):
        self.config = config
        self.memory = memory

    def execute(self, task: Dict) -> Dict:
        """执行任务，返回结果"""
        raise NotImplementedError

    def get_prompt(self, task: Dict) -> str:
        """构建 prompt"""
        raise NotImplementedError

    def parse_result(self, response: str) -> Any:
        """解析响应"""
        return response


# ==================== Tool Agents ====================

class CleanerAgent(BaseAgent):
    """清洗 Agent"""

    def __init__(self, memory: SharedMemory):
        super().__init__(AgentConfig(
            role=AgentRole.ANALYST,
            name="Cleaner",
            description="清洗聊天记录",
            tools=["regex", "llm"]
        ), memory)

    def execute(self, task: Dict) -> Dict:
        raw = task.get("raw_text", "")
        lines = raw.split('\n')
        cleaned = []

        ts_pattern = r'\d{4}[/\-]\d{1,2}[/\-]\d{1,2}\s+\d{1,2}:\d{2}'

        for line in lines:
            line = line.strip()
            if not line or re.match(ts_pattern, line):
                continue
            line = re.sub(r'^[\u4e00-\u9fa5a-zA-Z0-9_]+\s*[:：]\s*', '', line)
            if line and len(line) > 1:
                cleaned.append(line)

        prompt = f"清洗微信聊天，每行一条消息：\n{' '.join(cleaned[:50])}"
        result = llm(prompt, 0.3).strip()

        self.memory.set("cleaned_text", result)
        self.memory.log(self.config.name, "clean", result[:100])

        return {"status": "success", "output": result}


class EmotionAnalystAgent(BaseAgent):
    """情感分析 Agent"""

    def __init__(self, memory: SharedMemory):
        super().__init__(AgentConfig(
            role=AgentRole.ANALYST,
            name="EmotionAnalyst",
            description="分析聊天情感和关键词",
            tools=["llm"]
        ), memory)

    def execute(self, task: Dict) -> Dict:
        text = self.memory.get("cleaned_text", "")

        prompt = f"""分析聊天，返回JSON：
{{"emotion":"情感类型","emotion_detail":"细化","keywords":["词1","词2","词3"],"story":"故事线"}}

聊天：{text[:500]}
直接JSON："""

        result = llm(prompt, 0.3)

        try:
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            data = json.loads(result)

            self.memory.set("emotion", data.get("emotion", "未知"))
            self.memory.set("emotion_detail", data.get("emotion_detail", ""))
            self.memory.set("keywords", data.get("keywords", []))
            self.memory.set("story", data.get("story", ""))

            self.memory.log(self.config.name, "analyze", data.get("emotion", ""), 0)
            return {"status": "success", "output": data}
        except:
            return {"status": "error", "output": result}


class StoryGraphAgent(BaseAgent):
    """故事图谱 Agent"""

    def __init__(self, memory: SharedMemory):
        super().__init__(AgentConfig(
            role=AgentRole.ANALYST,
            name="StoryGraph",
            description="提取故事结构",
            tools=["llm"]
        ), memory)

    def execute(self, task: Dict) -> Dict:
        chat = self.memory.get("raw_text", "")
        emotion = self.memory.get("emotion", "")

        prompt = f"""提取故事图谱（JSON）：
{{"nodes":[{{"content":"","type":""}}],"emotion_arc":[],"core_theme":""}}

聊天：{chat[:400]}
情感：{emotion}
直接JSON："""

        result = llm(prompt, 0.3)

        try:
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            data = json.loads(result)

            self.memory.set("story_graph", data)
            graph_context = "【故事】" + " | ".join([n["content"] for n in data.get("nodes", [])[:3]])
            self.memory.set("graph_context", graph_context)

            self.memory.log(self.config.name, "extract", data.get("core_theme", ""))
            return {"status": "success", "output": data}
        except:
            return {"status": "error", "output": {}}


class WriterAgent(BaseAgent):
    """歌词创作 Agent"""

    STYLES = {
        "甜蜜": "甜蜜温馨", "伤感": "伤感忧郁", "说唱": "节奏强劲",
        "治愈": "温暖治愈", "摇滚": "力量感强", "叙事": "叙事画面",
        "民谣": "质朴自然", "R&B": "丝滑性感"
    }

    def __init__(self, memory: SharedMemory):
        super().__init__(AgentConfig(
            role=AgentRole.WRITER,
            name="Writer",
            description="创作歌词",
            tools=["llm"]
        ), memory)

    def execute(self, task: Dict) -> Dict:
        style = task.get("style", "甜蜜")
        feedback = task.get("feedback", "")

        prompt = f"""创作歌词：

情感：{self.memory.get("emotion", "")} {self.memory.get("emotion_detail", "")}
风格：{self.STYLES.get(style, style)}
故事：{self.memory.get("story", "")}
关键词：{', '.join(self.memory.get("keywords", []))}
{self.memory.get("graph_context", "")}
{feedback}

要求：主歌4句+副歌4句+主歌2 4句+副歌4句，按韵脚押韵。

歌词："""

        result = llm(prompt, 0.85)

        self.memory.set("current_lyrics", result)
        self.memory.log(self.config.name, "write", result[:50])

        return {"status": "success", "output": result}


class CriticAgent(BaseAgent):
    """审查 Agent"""

    def __init__(self, memory: SharedMemory):
        super().__init__(AgentConfig(
            role=AgentRole.CRITIC,
            name="Critic",
            description="审查歌词质量",
            tools=["llm"]
        ), memory)

    def execute(self, task: Dict) -> Dict:
        lyrics = self.memory.get("current_lyrics", "")
        style = task.get("style", "甜蜜")
        emotion = self.memory.get("emotion", "")

        prompt = f"""审查歌词（JSON）：
{{"overall":8.0,"emotion_match":8.0,"style_fit":8.0,"issues":[],"suggestions":[]}}

歌词：{lyrics}
情感：{emotion}
风格：{style}

直接JSON："""

        result = llm(prompt, 0.3)

        try:
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            data = json.loads(result)

            score = data.get("overall", 0)
            self.memory.log(self.config.name, "critic", data.get("issues", []), score)
            self.memory.set("last_critique", data)

            return {"status": "success", "output": data, "score": score}
        except:
            return {"status": "error", "output": {}, "score": 0}


class EditorAgent(BaseAgent):
    """编辑 Agent"""

    def __init__(self, memory: SharedMemory):
        super().__init__(AgentConfig(
            role=AgentRole.EDITOR,
            name="Editor",
            description="编辑修改歌词",
            tools=["llm"]
        ), memory)

    def execute(self, task: Dict) -> Dict:
        lyrics = self.memory.get("current_lyrics", "")
        suggestions = task.get("suggestions", [])

        if not suggestions:
            return {"status": "success", "output": lyrics}

        prompt = f"""修改歌词：

原文：{lyrics}

修改建议：{', '.join(suggestions)}

要求：保持结构，只改问题部分。直接输出修改后的歌词："""

        result = llm(prompt, 0.7)

        self.memory.set("current_lyrics", result)
        self.memory.log(self.config.name, "edit", result[:50])

        return {"status": "success", "output": result}


class TitleAgent(BaseAgent):
    """标题 Agent"""

    def __init__(self, memory: SharedMemory):
        super().__init__(AgentConfig(
            role=AgentRole.WRITER,
            name="TitleGenerator",
            description="生成标题",
            tools=["llm"]
        ), memory)

    def execute(self, task: Dict) -> Dict:
        lyrics = self.memory.get("best_lyrics", self.memory.get("current_lyrics", ""))
        emotion = self.memory.get("emotion", "")

        prompt = f"标题（2-6字）：{lyrics[:200]}\n情感：{emotion}\n直接输出："
        result = llm(prompt, 0.8).strip()

        self.memory.log(self.config.name, "title", result)
        return {"status": "success", "output": result}


# ==================== Agent Registry ====================

class AgentRegistry:
    """Agent 注册表"""

    _agents: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str, agent_class: type):
        cls._agents[name] = agent_class

    @classmethod
    def create(cls, name: str, memory: SharedMemory) -> BaseAgent:
        agent_class = cls._agents.get(name)
        if not agent_class:
            raise ValueError(f"Agent {name} not registered")
        return agent_class(memory)

    @classmethod
    def list_agents(cls) -> List[str]:
        return list(cls._agents.keys())


# 注册所有 Agent
AgentRegistry.register("Cleaner", CleanerAgent)
AgentRegistry.register("EmotionAnalyst", EmotionAnalystAgent)
AgentRegistry.register("StoryGraph", StoryGraphAgent)
AgentRegistry.register("Writer", WriterAgent)
AgentRegistry.register("Critic", CriticAgent)
AgentRegistry.register("Editor", EditorAgent)
AgentRegistry.register("Title", TitleAgent)


# ==================== Execution Engine ====================

class ExecutionEngine:
    """
    执行引擎
    负责任务队列和 Agent 调度
    """

    def __init__(self, memory: SharedMemory):
        self.memory = memory
        self.task_queue: List[Dict] = []
        self.completed_tasks: List[Dict] = []

    def add_task(self, agent: str, task: Dict) -> str:
        """添加任务到队列"""
        task_id = f"{agent}_{len(self.task_queue)}"
        self.task_queue.append({
            "id": task_id,
            "agent": agent,
            "task": task,
            "status": "pending"
        })
        return task_id

    def execute_task(self, task: Dict) -> Dict:
        """执行单个任务"""
        agent_name = task["agent"]
        task_data = task["task"]

        try:
            agent = AgentRegistry.create(agent_name, self.memory)
            result = agent.execute(task_data)

            self.completed_tasks.append({
                "id": task["id"],
                "status": "success",
                "result": result
            })

            return {"status": "success", "result": result}

        except Exception as e:
            self.completed_tasks.append({
                "id": task["id"],
                "status": "error",
                "error": str(e)
            })
            return {"status": "error", "error": str(e)}

    def run_queue(self) -> List[Dict]:
        """执行所有队列任务"""
        results = []
        for task in self.task_queue:
            result = self.execute_task(task)
            results.append(result)
        self.task_queue.clear()
        return results


# ==================== Multi-Agent Runtime ====================

class MultiAgentRuntime:
    """
    多智能体运行时
    核心调度器
    """

    def __init__(self):
        self.memory = SharedMemory()
        self.engine = ExecutionEngine(self.memory)

    def run(self, chat_text: str, style: str = "甜蜜", max_iterations: int = 3) -> Dict:
        """运行多 Agent 系统"""

        print("\n" + "="*50)
        print("WeChatChat2Lyric-Agent v6.0 (Multi-Agent Runtime)")
        print("="*50)
        print(f"风格: {style} | 最大迭代: {max_iterations}")

        self.memory.set("raw_text", chat_text)
        self.memory.set("style", style)

        # ===== Phase 1: 理解 =====
        print("\n[Phase 1] 理解...")
        self.engine.add_task("Cleaner", {"raw_text": chat_text})
        self.engine.run_queue()

        self.engine.add_task("EmotionAnalyst", {})
        self.engine.run_queue()

        self.engine.add_task("StoryGraph", {})
        self.engine.run_queue()

        print(f"    情感: {self.memory.get('emotion', '未知')}")

        # ===== Phase 2: 生成 + 反馈循环 =====
        print("\n[Phase 2] 生成 + 反馈循环...")

        best_lyrics = ""
        best_score = 0.0
        feedback = ""

        for i in range(max_iterations):
            iteration = i + 1
            self.memory.iteration = iteration

            print(f"    迭代 {iteration}/{max_iterations}...")

            # 写入
            self.engine.add_task("Writer", {"style": style, "feedback": feedback})
            self.engine.run_queue()

            # 审查
            self.engine.add_task("Critic", {"style": style})
            results = self.engine.run_queue()

            # 获取分数
            score = 0.0
            if results and results[0].get("status") == "success":
                score = results[0].get("score", 0)

            print(f"    分数: {score:.1f}/10")

            current_lyrics = self.memory.get("current_lyrics", "")

            if score > best_score:
                best_score = score
                best_lyrics = current_lyrics
                self.memory.set("best_lyrics", best_lyrics)
                self.memory.set("best_score", best_score)

            if score >= 7.5:
                print(f"    ✅ 达标")
                break

            # 准备反馈
            critique = self.memory.get("last_critique", {})
            suggestions = critique.get("suggestions", [])
            feedback = f"问题：{', '.join(suggestions[:2])}" if suggestions else ""

        # ===== Phase 3: 输出 =====
        print("\n[Phase 3] 输出...")

        self.engine.add_task("Title", {})
        results = self.engine.run_queue()

        title = "无题"
        if results and results[0].get("status") == "success":
            title = results[0].get("result", {}).get("output", "无题")

        print(f"    {title}")

        # ===== 结果 =====
        return {
            "title": title,
            "style": style,
            "emotion": self.memory.get("emotion"),
            "keywords": self.memory.get("keywords", []),
            "story": self.memory.get("story"),
            "story_graph": self.memory.get("story_graph"),
            "lyrics": best_lyrics,
            "best_score": best_score,
            "iterations": self.memory.iteration,
            "task_history": self.memory.task_history,
        }


# ==================== CLI ====================

def print_result(result: Dict):
    print("\n" + "="*50)
    print(f"🎵 {result['title']}")
    print(f"🎨 {result['style']} | 🎧 {result['emotion']}")
    print(f"📊 最佳分数: {result['best_score']:.1f}/10 | 迭代: {result['iterations']}次")
    if result.get("story"):
        print(f"📖 故事: {result['story'][:50]}...")
    print("="*50)
    print("\n📝 歌词:")
    print("-"*40)
    print(result["lyrics"])
    print("-"*40)


def main():
    parser = argparse.ArgumentParser(description="微信聊天记录 → AI歌词生成器 v6.0")
    parser.add_argument("--chat", type=str, help="聊天文本")
    parser.add_argument("--file", type=str, help="文件路径")
    parser.add_argument("--style", default="甜蜜",
                        choices=["甜蜜", "伤感", "说唱", "治愈", "摇滚", "叙事", "民谣", "R&B"])
    parser.add_argument("--iterations", type=int, default=3, help="最大迭代次数")
    parser.add_argument("--save", type=str, help="保存路径")

    args = parser.parse_args()

    if not args.chat and not args.file:
        print("请使用 --chat 或 --file 提供聊天记录")
        print("使用 --help 查看帮助")
        return

    chat_text = args.chat
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            chat_text = f.read()

    runtime = MultiAgentRuntime()
    result = runtime.run(chat_text, style=args.style, max_iterations=args.iterations)

    print_result(result)

    if args.save:
        with open(args.save, 'w', encoding='utf-8') as f:
            f.write(f"🎵 {result['title']}\n\n{result['lyrics']}")
        print(f"\n✅ 已保存: {args.save}")


if __name__ == "__main__":
    main()
