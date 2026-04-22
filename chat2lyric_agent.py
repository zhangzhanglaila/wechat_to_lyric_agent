"""
WeChatChat2Lyric-Agent v4.0
Graph-based Multi-Agent System

核心架构：
- DAG Workflow Engine（可插拔、可条件路由）
- Targeted Repair Loop（精准定位问题）
- Beat-Structured Skeleton（可执行计划）
- 7个独立 Agent 分工协作
"""

import os
import re
import sys
import json
from typing import List, Dict, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv
from datetime import datetime
from collections import defaultdict

# LangChain 核心
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from langchain.prompts import ChatPromptTemplate

# ==================== 配置 ====================
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY", "sk-44b7a257f56d4d80b85ed5ac4d1d182d")
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")

GENRE_OPTIONS = ["流行", "民谣", "说唱", "抒情", "摇滚"]

# 全局 LLM
llm = ChatOpenAI(
    openai_api_key=API_KEY,
    openai_api_base=API_BASE,
    model_name=MODEL_NAME,
    temperature=0.8,
    streaming=False
)


# ==================== DAG Workflow Engine ====================

class NodeType(Enum):
    """节点类型"""
    AGENT = "agent"
    CONDITION = "condition"
    MERGE = "merge"
    OUTPUT = "output"


@dataclass
class DAGNode:
    """DAG 节点"""
    id: str
    type: NodeType
    agent_name: str = ""
    params: Dict = field(default_factory=dict)
    condition_fn: Callable = None  # 条件函数
    on_fail: str = ""  # 失败时跳转
    on_success: str = ""  # 成功时跳转


class DAGWorkflow:
    """
    有向无环图工作流引擎
    支持：条件路由、节点插拔、并行分支
    """

    def __init__(self):
        self.nodes: Dict[str, DAGNode] = {}
        self.edges: Dict[str, List[str]] = defaultdict(list)
        self.default_output = ""

    def add_node(self, node: DAGNode):
        """添加节点"""
        self.nodes[node.id] = node

    def add_edge(self, from_id: str, to_id: str):
        """添加边"""
        self.edges[from_id].append(to_id)

    def set_conditions(self, node_id: str, conditions: Dict[str, str]):
        """
        设置条件跳转
        conditions: {"score<7": "fix_rhyme", "score>=7": "next"}
        """
        if node_id in self.nodes:
            self.nodes[node_id].params["conditions"] = conditions

    def execute(self, context: Dict, start_node: str = "load") -> Dict:
        """执行工作流"""
        current = start_node
        visited = set()
        max_iterations = 50
        iteration = 0

        while current and iteration < max_iterations:
            iteration += 1

            if current in visited:
                print(f"⚠️ 检测到循环，跳出: {current}")
                break

            visited.add(current)
            node = self.nodes.get(current)

            if not node:
                break

            # 执行节点
            result = self._execute_node(node, context)

            # 存储结果
            if result is not None:
                context[f"{node.id}_result"] = result

            # 决定下一步
            current = self._get_next_node(node, context)

        return context

    def _execute_node(self, node: DAGNode, context: Dict) -> Any:
        """执行单个节点"""
        if node.type == NodeType.AGENT:
            # 调用对应的 Agent
            agent = AgentRegistry.get(node.agent_name)
            if agent:
                return agent.execute(context, **node.params)
        elif node.type == NodeType.OUTPUT:
            return context.get("lyrics", "")

        return None

    def _get_next_node(self, node: DAGNode, context: Dict) -> str:
        """根据条件决定下一步"""
        if node.type == NodeType.OUTPUT:
            return None

        # 检查是否有条件跳转
        conditions = node.params.get("conditions", {})
        if conditions:
            for cond, next_node in conditions.items():
                if self._evaluate_condition(cond, context):
                    return next_node

        # 默认走第一条边
        edges = self.edges.get(node.id, [])
        return edges[0] if edges else None

    def _evaluate_condition(self, cond: str, context: Dict) -> bool:
        """评估条件表达式"""
        try:
            # 简单条件解析：score<7, emotion_match<7, etc.
            for key in ["score", "rhythm", "emotion_match", "structure", "rhyme"]:
                if key in cond:
                    val = context.get(f"{key}_score", 0)
                    op = "<" if "<" in cond else ">=" if ">=" in cond else ">"
                    threshold = float(cond.split(op)[1].strip())
                    if op == "<":
                        return val < threshold
                    elif op == ">=":
                        return val >= threshold
            return False
        except:
            return False


# ==================== Beat-Structured Skeleton ====================

@dataclass
class SectionPlan:
    """段落计划（Beat-Structured 的核心）"""
    section_type: str  # verse1, chorus, verse2, bridge, chorus
    lines: int
    emotion: str  # low, rising, peak, fall
    theme: str  # 段落主题
    keywords: List[str]  # 必须包含的词
    rhyme_end: str = ""  # 韵脚（如：ang, ian, ou）
    hook_line: str = ""  # 金句（仅用于chorus）
    tone: str = ""  # 语气（温柔/强烈/低沉）
    melody_hint: str = ""  # 旋律暗示（上行/下行/平稳）


@dataclass
class BeatStructuredSkeleton:
    """
    可执行的歌词骨架
    每个段落都有明确的执行指令
    """
    sections: List[SectionPlan] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "sections": [
                {
                    "section_type": s.section_type,
                    "lines": s.lines,
                    "emotion": s.emotion,
                    "theme": s.theme,
                    "keywords": s.keywords,
                    "rhyme_end": s.rhyme_end,
                    "hook_line": s.hook_line,
                    "tone": s.tone,
                    "melody_hint": s.melody_hint,
                }
                for s in self.sections
            ]
        }

    @staticmethod
    def from_dict(data: Dict) -> "BeatStructuredSkeleton":
        sections = []
        for s in data.get("sections", []):
            sections.append(SectionPlan(
                section_type=s.get("section_type", "verse"),
                lines=s.get("lines", 4),
                emotion=s.get("emotion", "low"),
                theme=s.get("theme", ""),
                keywords=s.get("keywords", []),
                rhyme_end=s.get("rhyme_end", ""),
                hook_line=s.get("hook_line", ""),
                tone=s.get("tone", ""),
                melody_hint=s.get("melody_hint", ""),
            ))
        return BeatStructuredSkeleton(sections=sections)


# ==================== Agent 基类 ====================

class BaseAgent:
    """Agent 基类"""

    name = "base"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> Any:
        """执行 Agent"""
        raise NotImplementedError


class AgentRegistry:
    """Agent 注册表"""

    _agents: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str, agent_class: type):
        cls._agents[name] = agent_class

    @classmethod
    def get(cls, name: str) -> Optional[type]:
        return cls._agents.get(name)

    @classmethod
    def list_agents(cls) -> List[str]:
        return list(cls._agents.keys())


# ==================== Agent 实现 ====================

class CleanerAgent(BaseAgent):
    """清洗 Agent"""

    name = "clean"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> str:
        raw_text = context.get("raw_text", "")

        # 正则预清洗
        lines = raw_text.split('\n')
        cleaned_lines = []
        timestamp_pattern = r'\d{4}[/\-]\d{1,2}[/\-]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?'
        system_patterns = [
            r'^以上是打招呼内容', r'^以上是正文内容', r'^点击添加备注',
            r'^---\s*$', r'^\s*$', r'^【.*】$'
        ]

        for line in lines:
            line = line.strip()
            if not line or re.match(timestamp_pattern, line):
                continue
            if any(re.match(p, line) for p in system_patterns):
                continue
            line = re.sub(r'^["\"]?[\u4e00-\u9fa5a-zA-Z0-9_]+["\"]?\s*[:：]\s*', '', line)
            if line and len(line) > 1:
                cleaned_lines.append(line)

        cleaned = '\n'.join(cleaned_lines)

        # LLM 深度清洗
        prompt = f"""清洗微信聊天记录，每行一条消息，保留核心语义：

{cleaned}

直接输出清洗结果："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return cleaned


class EmotionAnalystAgent(BaseAgent):
    """情感分析 Agent"""

    name = "analyze"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> Dict:
        cleaned_text = context.get("cleaned_text", "")

        prompt = f"""深度分析聊天记录，输出严格JSON：

{{
    "emotion": "主要情感",
    "emotion_detail": "情感细化",
    "keywords": ["词1", "词2", "词3", "词4", "词5"],
    "story": "故事线（60字内）",
    "relationship": "人物关系",
    "emotion_curve": ["low", "rising", "peak", "fall", "peak"],
    "core_theme": "核心主题词"
}}

聊天记录：
{cleaned_text}

直接输出JSON："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()

            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]

            return json.loads(result)
        except:
            return {
                "emotion": "未知",
                "emotion_detail": "",
                "keywords": [],
                "story": "",
                "relationship": "",
                "emotion_curve": ["low", "rising", "peak", "fall", "peak"],
                "core_theme": ""
            }


class SkeletonPlannerAgent(BaseAgent):
    """
    骨架规划 Agent - 生成 Beat-Structured Skeleton
    这是 v4.0 核心升级：从"描述"到"可执行计划"
    """

    name = "plan"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> Dict:
        emotion = context.get("emotion", "")
        emotion_detail = context.get("emotion_detail", "")
        keywords = context.get("keywords", [])
        story = context.get("story", "")
        genre = context.get("genre", "流行")

        genre_rhyme = {
            "流行": ["ang", "ian", "ou", "ei"],
            "民谣": ["an", "en", "ing", "ong"],
            "说唱": ["a", "e", "i", "ou", "an"],
            "抒情": ["ang", "ian", "ao", "ou"],
            "摇滚": ["ang", "ong", "ai", "ei"]
        }

        genre_melody = {
            "流行": ["平稳", "上行", "平稳", "下行"],
            "民谣": ["下行", "平稳", "上行", "平稳"],
            "说唱": ["上行", "上行", "上行", "上行"],
            "抒情": ["下行", "上行", "peak", "下行"],
            "摇滚": ["上行", "上行", "peak", "上行"]
        }

        rhyme_options = genre_rhyme.get(genre, ["ang", "ian"])
        melody_options = genre_melody.get(genre, ["平稳", "上行"])

        prompt = f"""你是顶级歌词策划师。生成可执行的 Beat-Structured Skeleton。

## 输入
- 情感：{emotion} - {emotion_detail}
- 关键词：{', '.join(keywords)}
- 故事：{story}
- 曲风：{genre}

## 输出格式（严格JSON）
每个段落必须是"可执行的指令"：

{{
    "sections": [
 {{
            "section_type": "verse1",
            "lines": 4,
            "emotion": "low",
            "theme": "引入故事背景",
            "keywords": ["词1", "词2"],
            "rhyme_end": "ang",
            "hook_line": "",
            "tone": "叙事",
            "melody_hint": "下行"
        }},
        {{
            "section_type": "chorus",
            "lines": 4,
            "emotion": "peak",
            "theme": "情感爆发点",
            "keywords": ["核心词1", "核心词2"],
            "rhyme_end": "ian",
            "hook_line": "副歌金句（必须押韵，10字内）",
            "tone": "强烈",
            "melody_hint": "上行"
        }},
        {{
            "section_type": "verse2",
            "lines": 4,
            "emotion": "rising",
            "theme": "延续+递进",
            "keywords": ["词3", "词4"],
            "rhyme_end": "ou",
            "hook_line": "",
            "tone": "叙事",
            "melody_hint": "平稳"
        }},
        {{
            "section_type": "bridge",
            "lines": 4,
            "emotion": "fall",
            "theme": "情感转折",
            "keywords": ["转折词1", "转折词2"],
            "rhyme_end": "en",
            "hook_line": "",
            "tone": "低沉",
            "melody_hint": "下行"
        }}
    ]
}}

要求：
1. 押韵词从 {rhyme_options} 选择
2. 情感曲线必须包含 low→rising→peak→fall→peak
3. 每段必须有明确的 theme 描述
4. chorus 必须有 hook_line（金句）
5. keywords 必须来自输入的关键词

直接输出JSON，不要解释："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()

            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]

            return json.loads(result)
        except:
            # 默认骨架
            return {
                "sections": [
                    {"section_type": "verse1", "lines": 4, "emotion": "low", "theme": "引入",
                     "keywords": keywords[:2], "rhyme_end": "ang", "hook_line": "", "tone": "叙事", "melody_hint": "下行"},
                    {"section_type": "chorus", "lines": 4, "emotion": "peak", "theme": "高潮",
                     "keywords": keywords[:2], "rhyme_end": "ian", "hook_line": "我们的故事继续", "tone": "强烈", "melody_hint": "上行"},
                    {"section_type": "verse2", "lines": 4, "emotion": "rising", "theme": "延续",
                     "keywords": keywords[:2], "rhyme_end": "ou", "hook_line": "", "tone": "叙事", "melody_hint": "平稳"},
                    {"section_type": "bridge", "lines": 4, "emotion": "fall", "theme": "转折",
                     "keywords": keywords[:1], "rhyme_end": "en", "hook_line": "", "tone": "低沉", "melody_hint": "下行"},
                ]
            }


class GeneratorAgent(BaseAgent):
    """歌词生成 Agent - 基于 Beat-Structured Skeleton"""

    name = "generate"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> str:
        emotion = context.get("emotion", "")
        emotion_detail = context.get("emotion_detail", "")
        keywords = context.get("keywords", [])
        story = context.get("story", "")
        genre = context.get("genre", "流行")
        skeleton_data = context.get("skeleton_plan", {})

        skeleton = BeatStructuredSkeleton.from_dict(skeleton_data)

        genre_notes = {
            "流行": "旋律优美，情感细腻",
            "民谣": "叙事性强，画面感足",
            "说唱": "节奏强劲，押韵密集",
            "抒情": "情感浓烈，旋律优美",
            "摇滚": "力量感足，节奏强劲"
        }

        # 构建段落约束指令
        section_instructions = []
        for s in skeleton.sections:
            section_instructions.append(f"""
[{s.section_type.upper()}]
- 句数: {s.lines}
- 情感: {s.emotion}
- 主题: {s.theme}
- 必须包含: {', '.join(s.keywords)}
- 韵脚: {s.rhyme_end}
- 语气: {s.tone}
- 旋律: {s.melody_hint}
{f"- 金句: {s.hook_line}" if s.hook_line else ""}
""")

        prompt = f"""你是专业的歌词创作者。基于以下结构指令创作歌词。

## 曲风
{genre} - {genre_notes.get(genre, '')}

## 情感
{emotion} - {emotion_detail}

## 关键词
{', '.join(keywords)}

## 故事线
{story}

## 段落结构（必须严格遵循）
{''.join(section_instructions)}

## 创作要求
1. 每个段落必须恰好 {sum(s.lines for s in skeleton.sections)} 句
2. 严格按照指定的韵脚押韵
3. 情感曲线：low→rising→peak→fall→peak
4. 包含所有指定的关键词
5. 禁止真实人名地名
6. chorus 必须使用金句："{skeleton.sections[1].hook_line if len(skeleton.sections) > 1 else ''}"

直接输出歌词："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return "生成失败"


class RhymeFixerAgent(BaseAgent):
    """押韵修复 Agent - Targeted Repair"""

    name = "fix_rhyme"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> str:
        lyrics = context.get("lyrics", "")
        skeleton_data = context.get("skeleton_plan", {})

        prompt = f"""修复以下歌词的押韵问题：

{lyrics}

要求：
1. 保持原意和情感
2. 加强句尾押韵（使用 AABB 格式）
3. 保持原有句数
4. 直接输出修复后的歌词，不要解释："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return lyrics


class EmotionBoostAgent(BaseAgent):
    """情感增强 Agent - Targeted Repair"""

    name = "boost_emotion"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> str:
        lyrics = context.get("lyrics", "")
        emotion = context.get("emotion", "")
        emotion_detail = context.get("emotion_detail", "")

        prompt = f"""增强以下歌词的情感表达：

{lyrics}

目标情感：{emotion} - {emotion_detail}

要求：
1. 保持押韵和结构
2. 增强情感感染力
3. 添加更细腻的情感描写
4. 直接输出，不要解释："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return lyrics


class StructureFixAgent(BaseAgent):
    """结构修复 Agent - Targeted Repair"""

    name = "fix_structure"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> str:
        lyrics = context.get("lyrics", "")
        skeleton_data = context.get("skeleton_plan", {})

        skeleton = BeatStructuredSkeleton.from_dict(skeleton_data)
        expected_lines = sum(s.lines for s in skeleton.sections)

        prompt = f"""修复以下歌词的结构问题：

{lyrics}

要求：
1. 确保总句数正确
2. 保持段落标记 [verse1] [chorus] [verse2] [bridge]
3. 保持押韵
4. 直接输出，不要解释："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return lyrics


class VerifierAgent(BaseAgent):
    """
    质量审查 Agent - 分解评分 + Targeted Repair 定位
    v4.0 核心：不仅评分，还精确定位问题
    """

    name = "verify"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> Dict:
        lyrics = context.get("lyrics", "")
        emotion = context.get("emotion", "")
        emotion_detail = context.get("emotion_detail", "")
        keywords = context.get("keywords", [])
        skeleton_data = context.get("skeleton_plan", {})

        skeleton = BeatStructuredSkeleton.from_dict(skeleton_data)

        prompt = f"""全面审查歌词质量，按维度评分：

## 歌词
{lyrics}

## 目标情感
{emotion} - {emotion_detail}

## 关键词
{', '.join(keywords)}

## 结构要求
主歌 {skeleton.sections[0].lines if skeleton.sections else 4} 句
副歌 {skeleton.sections[1].lines if len(skeleton.sections) > 1 else 4} 句
桥段 {skeleton.sections[3].lines if len(skeleton.sections) > 3 else 4} 句

## 评分维度（每项 0-10）
1. rhythm_quality: 节奏和句长协调性
2. emotion_match: 情感匹配度
3. structure_compliance: 结构合规性
4. rhyme_quality: 押韵质量
5. keyword_coverage: 关键词覆盖率

## 输出格式（严格JSON）
{{
    "overall": 8.5,
    "rhythm_quality": 8.0,
    "emotion_match": 9.0,
    "structure_compliance": 8.5,
    "rhyme_quality": 8.0,
    "keyword_coverage": 7.5,
    "issues": ["问题1（定位到具体段落）", "问题2"],
    "targeted_repairs": {{
        "fix_rhyme": true,
        "boost_emotion": false,
        "fix_structure": true
    }}
}}

直接输出JSON："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()

            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]

            data = json.loads(result)

            # 存储分数到 context（供条件路由使用）
            context["score"] = data.get("overall", 0)
            context["rhythm_score"] = data.get("rhythm_quality", 0)
            context["emotion_match"] = data.get("emotion_match", 0)
            context["structure_score"] = data.get("structure_compliance", 0)
            context["rhyme_score"] = data.get("rhyme_quality", 0)
            context["keyword_score"] = data.get("keyword_coverage", 0)

            return data

        except:
            return {
                "overall": 5.0,
                "issues": ["审查失败"],
                "targeted_repairs": {"fix_rhyme": True, "boost_emotion": True, "fix_structure": True}
            }


class TitleAgent(BaseAgent):
    """标题生成 Agent"""

    name = "title"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> str:
        lyrics = context.get("lyrics", "")
        emotion = context.get("emotion", "")
        keywords = context.get("keywords", [])

        prompt = f"""为歌词生成标题（2-6字，有诗意）：

歌词片段：
{lyrics[:400]}

情感: {emotion}
关键词: {', '.join(keywords)}

直接输出标题："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return "无题"


# 注册所有 Agent
AgentRegistry.register("clean", CleanerAgent)
AgentRegistry.register("analyze", EmotionAnalystAgent)
AgentRegistry.register("plan", SkeletonPlannerAgent)
AgentRegistry.register("generate", GeneratorAgent)
AgentRegistry.register("fix_rhyme", RhymeFixerAgent)
AgentRegistry.register("boost_emotion", EmotionBoostAgent)
AgentRegistry.register("fix_structure", StructureFixAgent)
AgentRegistry.register("verify", VerifierAgent)
AgentRegistry.register("title", TitleAgent)


# ==================== Graph Workflow 定义 ====================

def create_graph_workflow() -> DAGWorkflow:
    """
    创建 Graph Workflow
    支持条件路由和 Targeted Repair
    """
    dag = DAGWorkflow()

    # 节点定义
    dag.add_node(DAGNode(id="load", type=NodeType.AGENT, agent_name="clean"))
    dag.add_node(DAGNode(id="analyze", type=NodeType.AGENT, agent_name="analyze"))
    dag.add_node(DAGNode(id="plan", type=NodeType.AGENT, agent_name="plan"))
    dag.add_node(DAGNode(id="generate", type=NodeType.AGENT, agent_name="generate"))

    # 验证节点（带条件路由）
    verify_node = DAGNode(
        id="verify",
        type=NodeType.AGENT,
        agent_name="verify",
        params={
            "conditions": {
                "score>=7.5": "title",
                "score<7.5": "repair_dispatch"
            }
        }
    )
    dag.add_node(verify_node)

    # 修复节点（可并行）
    dag.add_node(DAGNode(id="fix_rhyme", type=NodeType.AGENT, agent_name="fix_rhyme"))
    dag.add_node(DAGNode(id="boost_emotion", type=NodeType.AGENT, agent_name="boost_emotion"))
    dag.add_node(DAGNode(id="fix_structure", type=NodeType.AGENT, agent_name="fix_structure"))

    # 修复调度器（条件分支）
    repair_node = DAGNode(
        id="repair_dispatch",
        type=NodeType.CONDITION,
        params={
            "conditions": {
                "rhyme_score<7": "fix_rhyme",
                "emotion_match<7": "boost_emotion",
                "structure_score<7": "fix_structure"
            }
        }
    )
    dag.add_node(repair_node)

    dag.add_node(DAGNode(id="title", type=NodeType.AGENT, agent_name="title"))
    dag.add_node(DAGNode(id="output", type=NodeType.OUTPUT))

    # 边定义
    dag.add_edge("load", "analyze")
    dag.add_edge("analyze", "plan")
    dag.add_edge("plan", "generate")
    dag.add_edge("generate", "verify")
    dag.add_edge("verify", "title")
    dag.add_edge("title", "output")

    # 修复路径
    dag.add_edge("fix_rhyme", "generate")
    dag.add_edge("fix_structure", "generate")
    dag.add_edge("boost_emotion", "generate")
    dag.add_edge("repair_dispatch", "fix_rhyme")

    return dag


# ==================== 主 Pipeline ====================

class LyricGraphPipeline:
    """
    Graph-based Multi-Agent Pipeline
    可扩展、可插拔、精准修复
    """

    def __init__(self, api_key: str, api_base: str, model_name: str):
        self.llm = ChatOpenAI(
            openai_api_key=api_key,
            openai_api_base=api_base,
            model_name=model_name,
            temperature=0.8
        )
        self.graph = create_graph_workflow()
        self.genre = "流行"
        self.max_repair_loops = 3

    def run(self, chat_text: str, genre: str = "流行") -> Dict:
        """执行 Graph Workflow"""
        self.genre = genre

        context = {
            "raw_text": chat_text,
            "genre": genre,
            "repair_count": 0
        }

        print("\n" + "="*60)
        print("🎵 WeChatChat2Lyric-Agent v4.0 (Graph-based Multi-Agent)")
        print("="*60)
        print(f"📂 加载聊天记录: {len(chat_text)} 字符")
        print(f"🎸 曲风: {genre}")
        print("\n🔄 开始 Graph Workflow...\n")

        # 手动执行（更精确控制）
        result = self._execute_workflow(context)

        return result

    def _execute_workflow(self, context: Dict) -> Dict:
        """执行工作流"""
        iteration = 0
        max_iterations = 20

        while iteration < max_iterations:
            iteration += 1

            state = context.get("_current_state", "load")

            if state == "load":
                print("\n[Step 1] 清洗聊天记录...")
                context["cleaned_text"] = CleanerAgent.execute(context)
                print(f"   → 清洗完成: {len(context['cleaned_text'])} 字符")
                context["_current_state"] = "analyze"

            elif state == "analyze":
                print("\n[Step 2] 分析情感...")
                analysis = EmotionAnalystAgent.execute(context)
                context.update(analysis)
                print(f"   → 情感: {context.get('emotion', '未知')}")
                print(f"   → 关键词: {', '.join(context.get('keywords', [])[:5])}")
                context["_current_state"] = "plan"

            elif state == "plan":
                print("\n[Step 3] 规划歌词骨架...")
                skeleton_data = SkeletonPlannerAgent.execute(context)
                context["skeleton_plan"] = skeleton_data

                sections = skeleton_data.get("sections", [])
                print(f"   → 段落数: {len(sections)}")
                for s in sections:
                    print(f"   → [{s['section_type']}] {s['lines']}句 情感:{s['emotion']} 韵脚:{s['rhyme_end']}")

                context["_current_state"] = "generate"

            elif state == "generate":
                print("\n[Step 4] 生成歌词...")
                context["lyrics"] = GeneratorAgent.execute(context)
                print(f"   → 生成完成: {len(context['lyrics'])} 字符")
                context["_current_state"] = "verify"

            elif state == "verify":
                print("\n[Step 5] 质量审查...")
                verification = VerifierAgent.execute(context)
                context["verification"] = verification

                print(f"   ⭐ 总分: {verification.get('overall', 0):.1f}/10")
                print(f"   节奏感: {verification.get('rhythm_quality', 0):.1f}")
                print(f"   情感匹配: {verification.get('emotion_match', 0):.1f}")
                print(f"   结构合规: {verification.get('structure_compliance', 0):.1f}")
                print(f"   押韵质量: {verification.get('rhyme_quality', 0):.1f}")

                score = verification.get('overall', 0)
                targeted = verification.get('targeted_repairs', {})

                if score >= 7.5:
                    print(f"   ✅ 质量达标")
                    context["_current_state"] = "title"
                else:
                    context["repair_count"] = context.get("repair_count", 0) + 1
                    if context["repair_count"] >= self.max_repair_loops:
                        print(f"   ⚠️ 达到最大修复次数，跳过")
                        context["_current_state"] = "title"
                    else:
                        print(f"   🔧 执行 Targeted Repair ({context['repair_count']}/{self.max_repair_loops})")
                        self._execute_targeted_repair(context, verification)
                        context["_current_state"] = "generate"

            elif state == "title":
                print("\n[Step 6] 生成标题...")
                context["title"] = TitleAgent.execute(context)
                print(f"   → 标题: {context['title']}")
                context["_current_state"] = "done"

            elif state == "done":
                break

        return self._build_result(context)

    def _execute_targeted_repair(self, context: Dict, verification: Dict):
        """执行精准修复"""
        targeted = verification.get("targeted_repairs", {})
        issues = verification.get("issues", [])

        print(f"   📋 问题列表: {', '.join(issues[:3])}")

        if targeted.get("fix_rhyme"):
            print("   → 修复押韵...")
            context["lyrics"] = RhymeFixerAgent.execute(context)

        if targeted.get("boost_emotion"):
            print("   → 增强情感...")
            context["lyrics"] = EmotionBoostAgent.execute(context)

        if targeted.get("fix_structure"):
            print("   → 修复结构...")
            context["lyrics"] = StructureFixAgent.execute(context)

    def _build_result(self, context: Dict) -> Dict:
        """构建结果"""
        return {
            "title": context.get("title", "无题"),
            "genre": self.genre,
            "emotion": context.get("emotion", ""),
            "emotion_detail": context.get("emotion_detail", ""),
            "keywords": context.get("keywords", []),
            "story": context.get("story", ""),
            "lyric_plan": context.get("skeleton_plan", {}),
            "lyrics": context.get("lyrics", ""),
            "quality_score": context.get("verification", {}),
        }

    def print_result(self, result: Dict):
        """打印结果"""
        print("\n" + "="*60)
        print("🎵 歌曲标题:", result["title"])
        print("🎸 曲风:", result["genre"])
        print("🎧 情感:", result["emotion"], "-", result["emotion_detail"])
        print("🔑 关键词:", ", ".join(result["keywords"][:6]))

        qs = result.get("quality_score", {})
        if qs:
            print(f"⭐ 质量评分: {qs.get('overall', 0):.1f}/10")

        print("="*60)
        print("\n📝 歌词:")
        print("-"*40)
        print(result["lyrics"])
        print("-"*40)

    def save_result(self, result: Dict, file_path: str) -> bool:
        """保存结果"""
        content = f"""🎵 歌曲标题: {result['title']}
🎸 曲风: {result['genre']}
🎧 情感类型: {result['emotion']}
🔑 关键词: {', '.join(result['keywords'])}

{'='*50}
📝 歌词:
{'='*50}

{result['lyrics']}
"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ 已保存到: {file_path}")
            return True
        except:
            return False


# ==================== 演示 ====================

def run_demo():
    """运行演示"""
    print("\n" + "="*60)
    print("🎵 WeChatChat2Lyric-Agent v4.0 演示")
    print("="*60)

    demo_chat = """2024/1/1 12:00:00
小明：亲爱的，新年快乐！
小红：新年快乐呀～今年是我们在一起的第三年了
小明：是啊，时间过得好快
小红：记得我们第一次见面是在咖啡店
小明：你当时穿了一条白裙子
小红：你还记得呀，你当时紧张得话都说不清楚
小明：那是太喜欢你了嘛
小红：哼，就会说好听的
小明：我说的是真的，每次看到你都很开心
小红：我也是呀，和你在一起的时候
小明：今年有什么想做的事吗？
小红：想和你一起去旅行，看更多的风景
小明：好，我带你去你看日出
小红：说定了哦，不许反悔
小明：绝不反悔，我们拉钩
小红：拉钩上吊一百年不许变"""

    print("\n📝 示例聊天记录（情侣甜蜜对话）:\n")
    print(demo_chat[:200] + "...\n")

    pipeline = LyricGraphPipeline(API_KEY, API_BASE, MODEL_NAME)
    result = pipeline.run(demo_chat, "流行")
    pipeline.print_result(result)

    return result


# ==================== 命令行 ====================

def interactive_mode():
    """交互式界面"""
    print("""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║        🎵 WeChatChat2Lyric-Agent v4.0 🎵                ║
║                                                          ║
║     Graph-based Multi-Agent + Targeted Repair Loop      ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
    """)

    print("\n🎯 操作选项：")
    print("  1. 从文件加载")
    print("  2. 直接输入聊天记录")
    print("  3. 运行示例演示")
    print("  0. 退出")

    choice = input("\n请输入: ").strip()

    if choice == "1":
        file_path = input("文件路径: ").strip()
        genre = input("曲风 (1流行/2民谣/3说唱/4抒情/5摇滚，默认1): ").strip()
        genre_map = {"1": "流行", "2": "民谣", "3": "说唱", "4": "抒情", "5": "摇滚"}
        genre = genre_map.get(genre, "流行")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                chat_text = f.read()

            pipeline = LyricGraphPipeline(API_KEY, API_BASE, MODEL_NAME)
            result = pipeline.run(chat_text, genre)
            pipeline.print_result(result)

            if input("\n保存？(y/n): ").strip().lower() == 'y':
                save_path = input("路径: ").strip()
                if save_path:
                    pipeline.save_result(result, save_path)
        except Exception as e:
            print(f"❌ 错误: {e}")

    elif choice == "2":
        print("\n粘贴聊天记录（EOF结束）：")
        lines = []
        while True:
            try:
                line = input()
                if line.strip().upper() == "EOF":
                    break
                lines.append(line)
            except:
                break

        genre = input("曲风 (1流行/2民谣/3说唱/4抒情/5摇滚，默认1): ").strip()
        genre_map = {"1": "流行", "2": "民谣", "3": "说唱", "4": "抒情", "5": "摇滚"}
        genre = genre_map.get(genre, "流行")

        pipeline = LyricGraphPipeline(API_KEY, API_BASE, MODEL_NAME)
        result = pipeline.run('\n'.join(lines), genre)
        pipeline.print_result(result)

    elif choice == "3":
        run_demo()

    else:
        print("👋 再见！")


# ==================== 主入口 ====================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--demo":
            run_demo()
        elif sys.argv[1] == "--help":
            print("""
使用：python chat2lyric_agent.py              # 交互
     python chat2lyric_agent.py --demo      # 演示
     python chat2lyric_agent.py <file> [genre]  # 文件
            """)
        else:
            file_path = sys.argv[1]
            genre = sys.argv[2] if len(sys.argv) > 2 else "流行"

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    chat_text = f.read()

                pipeline = LyricGraphPipeline(API_KEY, API_BASE, MODEL_NAME)
                result = pipeline.run(chat_text, genre)
                pipeline.print_result(result)
            except Exception as e:
                print(f"❌ 错误: {e}")
    else:
        interactive_mode()
