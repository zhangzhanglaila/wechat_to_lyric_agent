"""
WeChatChat2Lyric-Agent v5.5
Enhanced Self-Optimizing System

新增功能：
- 风格控制器（Style Controller）- 可控生成
- 固定歌词结构模板（Structure Template）
- 故事图谱提取（Story Graph）
- 可解释生成（Explainable Generation）

核心架构升级：
- 从"随机生成" → "可控生成"
- 从"自由结构" → "模板约束"
- 从"表面分析" → "深度故事理解"
- 从"黑盒输出" → "可解释输出"
"""

import os
import re
import sys
import json
from typing import List, Dict, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv
from datetime import datetime
from collections import defaultdict

from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage

# ==================== 配置 ====================
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY", "sk-44b7a257f56d4d80b85ed5ac4d1d182d")
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")

llm = ChatOpenAI(
    openai_api_key=API_KEY,
    openai_api_base=API_BASE,
    model_name=MODEL_NAME,
    temperature=0.8,
    streaming=False
)


# ==================== 风格控制器 ====================

@dataclass
class StyleProfile:
    """风格配置"""
    name: str
    description: str
    prompt_suffix: str
    temperature: float
    rhyme_density: float  # 押韵密度 0-1
    emotion_intensity: float  # 情感强度 0-1
    narrative_mode: str  # "first_person" / "third_person" / "universal"


class StyleController:
    """
    风格控制器
    支持细粒度风格选择，不只是曲风
    """
    # 预设风格库
    STYLES = {
        # 情感类
        "甜蜜": StyleProfile(
            name="甜蜜",
            description="温暖甜蜜，适合情侣",
            prompt_suffix="甜蜜、温馨、幸福",
            temperature=0.7,
            rhyme_density=0.8,
            emotion_intensity=0.7,
            narrative_mode="first_person"
        ),
        "伤感": StyleProfile(
            name="伤感",
            description="忧郁抒情，触动心弦",
            prompt_suffix="伤感、忧郁、怀旧",
            temperature=0.6,
            rhyme_density=0.9,
            emotion_intensity=0.9,
            narrative_mode="first_person"
        ),
        "治愈": StyleProfile(
            name="治愈",
            description="温暖疗愈，给人力量",
            prompt_suffix="治愈、希望、温暖",
            temperature=0.75,
            rhyme_density=0.7,
            emotion_intensity=0.6,
            narrative_mode="universal"
        ),
        # 叙事类
        "叙事": StyleProfile(
            name="叙事",
            description="讲故事，有画面感",
            prompt_suffix="叙事性强、有画面感、讲故事",
            temperature=0.8,
            rhyme_density=0.6,
            emotion_intensity=0.5,
            narrative_mode="first_person"
        ),
        "民谣": StyleProfile(
            name="民谣",
            description="质朴自然，文艺清新",
            prompt_suffix="民谣风格、质朴、自然、文艺",
            temperature=0.8,
            rhyme_density=0.7,
            emotion_intensity=0.5,
            narrative_mode="first_person"
        ),
        # 节奏类
        "说唱": StyleProfile(
            name="说唱",
            description="节奏强劲，押韵密集",
            prompt_suffix="说唱风格、节奏感强、押韵密集、态度鲜明",
            temperature=0.85,
            rhyme_density=1.0,
            emotion_intensity=0.8,
            narrative_mode="first_person"
        ),
        "摇滚": StyleProfile(
            name="摇滚",
            description="力量感强，情绪爆发",
            prompt_suffix="摇滚风格、力量感强、节奏强劲、震撼",
            temperature=0.9,
            rhyme_density=0.8,
            emotion_intensity=0.95,
            narrative_mode="first_person"
        ),
        # 特殊风格
        "R&B": StyleProfile(
            name="R&B",
            description="丝滑 R&B 风格",
            prompt_suffix="R&B风格、丝滑、性感、优雅",
            temperature=0.75,
            rhyme_density=0.85,
            emotion_intensity=0.75,
            narrative_mode="first_person"
        ),
        "古风": StyleProfile(
            name="古风",
            description="唯美古风，意境悠远",
            prompt_suffix="古风、唯美、意境、诗意",
            temperature=0.65,
            rhyme_density=0.9,
            emotion_intensity=0.7,
            narrative_mode="universal"
        ),
    }

    @classmethod
    def get_style(cls, style_name: str) -> StyleProfile:
        """获取风格配置"""
        return cls.STYLES.get(style_name, cls.STYLES["流行"])

    @classmethod
    def list_styles(cls) -> List[str]:
        """列出所有可用风格"""
        return list(cls.STYLES.keys())

    @classmethod
    def apply_style_to_prompt(cls, base_prompt: str, style_name: str) -> str:
        """将风格配置应用到 prompt"""
        style = cls.get_style(style_name)
        styled_prompt = f"{base_prompt}\n\n风格要求：{style.description}"
        return styled_prompt


# ==================== 歌词结构模板 ====================

@dataclass
class SectionTemplate:
    """段落模板"""
    name: str  # verse1, chorus, verse2, bridge, etc.
    display_name: str  # 主歌1, 副歌, 主歌2, 桥段
    min_lines: int
    max_lines: int
    emotion_target: str  # low, rising, peak, fall
    function: str  # intro, climax, continuation, turn, final


class LyricStructureTemplate:
    """
    固定歌词结构模板
    确保歌词结构稳定，不是自由生成
    """
    TEMPLATES = {
        # 标准流行结构
        "standard_pop": {
            "name": "标准流行",
            "description": "最常见的歌词结构",
            "sections": [
                SectionTemplate("verse1", "主歌1", 4, 6, "low", "intro"),
                SectionTemplate("pre_chorus", "副歌前", 2, 4, "rising", "buildup"),
                SectionTemplate("chorus", "副歌", 4, 6, "peak", "climax"),
                SectionTemplate("verse2", "主歌2", 4, 6, "low", "continuation"),
                SectionTemplate("chorus", "副歌", 4, 6, "peak", "climax"),
                SectionTemplate("bridge", "桥段", 4, 4, "fall", "turn"),
                SectionTemplate("chorus", "副歌", 4, 6, "peak", "final"),
            ]
        },
        # 简洁结构
        "simple": {
            "name": "简洁结构",
            "description": "主歌+副歌简单循环",
            "sections": [
                SectionTemplate("verse1", "主歌1", 4, 4, "low", "intro"),
                SectionTemplate("chorus", "副歌", 4, 4, "peak", "climax"),
                SectionTemplate("verse2", "主歌2", 4, 4, "rising", "continuation"),
                SectionTemplate("chorus", "副歌", 4, 4, "peak", "climax"),
            ]
        },
        # 完整结构
        "full": {
            "name": "完整结构",
            "description": "最完整的歌词结构",
            "sections": [
                SectionTemplate("intro", "开场", 2, 2, "low", "intro"),
                SectionTemplate("verse1", "主歌1", 4, 6, "low", "intro"),
                SectionTemplate("pre_chorus", "副歌前", 2, 4, "rising", "buildup"),
                SectionTemplate("chorus", "副歌", 4, 6, "peak", "climax"),
                SectionTemplate("verse2", "主歌2", 4, 6, "rising", "continuation"),
                SectionTemplate("chorus", "副歌", 4, 6, "peak", "climax"),
                SectionTemplate("bridge", "桥段", 4, 4, "fall", "turn"),
                SectionTemplate("chorus", "副歌", 4, 6, "peak", "final"),
                SectionTemplate("outro", "尾奏", 2, 2, "fall", "ending"),
            ]
        },
        # 说唱结构
        "rap": {
            "name": "说唱结构",
            "description": "适合说唱的节奏结构",
            "sections": [
                SectionTemplate("intro", "开场", 2, 2, "rising", "intro"),
                SectionTemplate("verse1", "主歌1", 8, 8, "rising", "verse"),
                SectionTemplate("hook", "钩子", 4, 4, "peak", "hook"),
                SectionTemplate("verse2", "主歌2", 8, 8, "rising", "verse"),
                SectionTemplate("hook", "钩子", 4, 4, "peak", "hook"),
                SectionTemplate("bridge", "过渡", 4, 4, "fall", "bridge"),
                SectionTemplate("hook", "钩子", 4, 4, "peak", "final"),
            ]
        },
    }

    @classmethod
    def get_template(cls, template_name: str):
        """获取模板"""
        return cls.TEMPLATES.get(template_name, cls.TEMPLATES["standard_pop"])

    @classmethod
    def generate_structure_constraint(cls, template_name: str, skeleton_data: Dict) -> str:
        """生成结构约束文本"""
        template = cls.get_template(template_name)
        constraints = []

        for section in template.sections:
            # 从 skeleton 获取该段的信息
            section_data = None
            for s in skeleton_data.get("sections", []):
                if section.name in s.get("section_type", ""):
                    section_data = s
                    break

            rhyme = section_data.get("rhyme_end", "ang") if section_data else "ang"
            keywords = section_data.get("keywords", []) if section_data else []

            constraints.append(
                f"[{section.display_name}]\n"
                f"- 句数: {section.min_lines}-{section.max_lines}\n"
                f"- 情感: {section.emotion_target}\n"
                f"- 功能: {section.function}\n"
                f"- 韵脚: {rhyme}\n"
                f"- 关键词: {', '.join(keywords[:3])}"
            )

        return "\n\n".join(constraints)


# ==================== 故事图谱 ====================

@dataclass
class StoryNode:
    """故事节点"""
    type: str  # emotion_event, relationship_milestone, conflict, resolution
    content: str
    timestamp: str = ""
    importance: float = 1.0  # 0-1


@dataclass
class StoryGraph:
    """故事图谱"""
    nodes: List[StoryNode] = field(default_factory=list)
    emotion_arc: List[str] = field(default_factory=list)  # 情感弧线
    core_theme: str = ""


class StoryGraphExtractor:
    """
    故事图谱提取器
    从聊天记录中提取故事结构
    """

    @classmethod
    def extract(cls, chat_text: str, emotion: str) -> StoryGraph:
        """从聊天记录中提取故事图谱"""
        prompt = f"""从聊天记录中提取故事图谱：

聊天记录：
{chat_text}

情感基调：{emotion}

请提取：
1. 情感事件节点（emotion_event）：重要的情感表达时刻
2. 关系里程碑（relationship_milestone）：关系进展的关键点
3. 核心主题（core_theme）：整个对话的核心

输出JSON格式：
{{
    "nodes": [
        {{"type": "emotion_event", "content": "描述", "importance": 0.9}},
        {{"type": "relationship_milestone", "content": "描述", "importance": 0.8}}
    ],
    "emotion_arc": ["起点情感", "发展", "高潮", "结尾"],
    "core_theme": "核心主题"
}}

直接输出JSON："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]

            data = json.loads(result)

            nodes = []
            for n in data.get("nodes", []):
                nodes.append(StoryNode(
                    type=n.get("type", "emotion_event"),
                    content=n.get("content", ""),
                    importance=n.get("importance", 1.0)
                ))

            return StoryGraph(
                nodes=nodes,
                emotion_arc=data.get("emotion_arc", []),
                core_theme=data.get("core_theme", "")
            )
        except:
            return StoryGraph()

    @classmethod
    def to_context(cls, graph: StoryGraph) -> str:
        """将图谱转换为生成上下文"""
        if not graph.nodes:
            return ""

        context_parts = ["【故事图谱】"]
        for node in graph.nodes:
            importance_bar = "⭐" * int(node.importance * 5)
            context_parts.append(f"{importance_bar} [{node.type}] {node.content}")

        if graph.core_theme:
            context_parts.append(f"\n核心主题：{graph.core_theme}")

        if graph.emotion_arc:
            context_parts.append(f"情感弧线：{' → '.join(graph.emotion_arc)}")

        return "\n".join(context_parts)


# ==================== 可解释生成 ====================

@dataclass
class LyricExplanation:
    """歌词解释"""
    line: str
    source_chat: str  # 对应聊天内容
    emotion_reason: str  # 为什么这样写
    rhyme_explanation: str  # 押韵说明


class ExplainableGenerator:
    """
    可解释生成器
    解释每句歌词的来源和原因
    """

    @classmethod
    def generate_explanation(
        cls,
        lyrics: str,
        chat_text: str,
        emotion: str,
        keywords: List[str]
    ) -> List[LyricExplanation]:
        """生成歌词解释"""
        prompt = f"""为以下歌词生成解释：

歌词：
{lyrics}

原始聊天记录：
{chat_text}

情感：{emotion}
关键词：{', '.join(keywords)}

请为每句歌词解释：
1. 对应聊天中的哪句话
2. 为什么这样写
3. 押韵设计

输出JSON格式：
{{
    "explanations": [
        {{
            "line": "歌词句子",
            "source_chat": "对应的聊天内容",
            "emotion_reason": "为什么这样写",
            "rhyme_explanation": "押韵说明"
        }}
    ]
}}

直接输出JSON："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]

            data = json.loads(result)
            explanations = []

            for e in data.get("explanations", []):
                explanations.append(LyricExplanation(
                    line=e.get("line", ""),
                    source_chat=e.get("source_chat", ""),
                    emotion_reason=e.get("emotion_reason", ""),
                    rhyme_explanation=e.get("rhyme_explanation", "")
                ))

            return explanations
        except:
            return []

    @classmethod
    def format_explanations(cls, explanations: List[LyricExplanation]) -> str:
        """格式化解释输出"""
        if not explanations:
            return ""

        parts = ["\n" + "="*50]
        parts.append("📖 歌词解释")
        parts.append("="*50)

        for i, exp in enumerate(explanations, 1):
            parts.append("\n【第" + str(i) + "句】" + exp.line)
            parts.append("   聊天来源：" + exp.source_chat)
            parts.append("   情感设计：" + exp.emotion_reason)
            parts.append("   押韵：" + exp.rhyme_explanation)

        return "\n".join(parts)


# ==================== 核心组件（保持不变） ====================

class ConstraintLock:
    """全局约束锁"""
    def __init__(self):
        self.locked_dims: Set[str] = set()
        self.lock_threshold = 8.0

    def evaluate_and_lock(self, scores: Dict[str, float]) -> Set[str]:
        for dim, score in scores.items():
            if score >= self.lock_threshold and dim not in self.locked_dims:
                self.locked_dims.add(dim)
        return self.locked_dims

    def get_lock_report(self) -> str:
        if not self.locked_dims:
            return "无锁定"
        return f"已锁定: {', '.join(self.locked_dims)}"


@dataclass
class EditAction:
    line_index: int
    action_type: str
    target_content: str = ""
    original_content: str = ""
    reason: str = ""


class DiffEditor:
    """差分编辑器"""
    def parse_lyrics_to_lines(self, lyrics: str) -> List[str]:
        lines = []
        for line in lyrics.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('[') and line.endswith(']'):
                lines.append(line)
            else:
                lines.append(line)
        return lines

    def generate_targeted_edit_plan(
        self,
        lyrics: str,
        issues: List[str],
        locked_dims: Set[str]
    ) -> List[EditAction]:
        lines = self.parse_lyrics_to_lines(lyrics)
        edit_plan = []

        rhyme_issues = [i for i in issues if '押韵' in i]
        if rhyme_issues and 'rhyme' not in locked_dims:
            last_idx = len(lines) - 1
            while last_idx >= 0 and lines[last_idx].startswith('['):
                last_idx -= 1
            if last_idx >= 0:
                edit_plan.append(EditAction(
                    line_index=last_idx,
                    action_type="fix_rhyme",
                    reason=rhyme_issues[0]
                ))

        return edit_plan


class GlobalOptimizer:
    """全局优化器"""
    def compute_global_score(self, scores: Dict) -> float:
        return round(sum(scores.values()) / len(scores), 2) if scores else 0


# ==================== Agent 实现 ====================

class CleanerAgent:
    @classmethod
    def execute(cls, context: Dict) -> str:
        raw_text = context.get("raw_text", "")
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

        return '\n'.join(cleaned_lines)


class EmotionAnalystAgent:
    @classmethod
    def execute(cls, context: Dict) -> Dict:
        cleaned_text = context.get("cleaned_text", "")

        prompt = f"""分析聊天记录，输出JSON：
{{
    "emotion": "情感",
    "emotion_detail": "情感细化",
    "keywords": ["词1", "词2", "词3", "词4", "词5"],
    "story": "故事线"
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
            return {"emotion": "未知", "emotion_detail": "", "keywords": [], "story": ""}


class SkeletonPlannerAgent:
    @classmethod
    def execute(cls, context: Dict) -> Dict:
        emotion = context.get("emotion", "")
        emotion_detail = context.get("emotion_detail", "")
        keywords = context.get("keywords", [])
        story = context.get("story", "")

        prompt = f"""生成歌词骨架（严格JSON）：
{{
    "sections": [
        {{"section_type": "verse1", "lines": 4, "emotion": "low", "theme": "引入", "keywords": ["{keywords[0]}"], "rhyme_end": "ang"}},
        {{"section_type": "chorus", "lines": 4, "emotion": "peak", "theme": "高潮", "keywords": ["{keywords[1] if len(keywords) > 1 else keywords[0]}"], "rhyme_end": "ian", "hook_line": "核心金句"}},
        {{"section_type": "verse2", "lines": 4, "emotion": "rising", "theme": "延续", "keywords": ["{keywords[2] if len(keywords) > 2 else keywords[0]}"], "rhyme_end": "ou"}},
        {{"section_type": "bridge", "lines": 4, "emotion": "fall", "theme": "转折", "keywords": ["{keywords[3] if len(keywords) > 3 else keywords[0]}"], "rhyme_end": "en"}}
    ]
}}

情感：{emotion} - {emotion_detail}
直接输出JSON："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            return json.loads(result)
        except:
            return {"sections": []}


class GeneratorAgent:
    @classmethod
    def execute(cls, context: Dict, style: str = "流行", structure_template: str = "standard_pop") -> str:
        emotion = context.get("emotion", "")
        emotion_detail = context.get("emotion_detail", "")
        keywords = context.get("keywords", [])
        story = context.get("story", "")
        skeleton_data = context.get("skeleton_plan", {})
        style_profile = StyleController.get_style(style)
        structure_constraint = LyricStructureTemplate.generate_structure_constraint(structure_template, skeleton_data)

        prompt = f"""基于以下信息创作歌词：

情感：{emotion} - {emotion_detail}
风格：{style_profile.description}
故事：{story}
关键词：{', '.join(keywords)}

结构要求：
{structure_constraint}

要求：
1. 严格按句数创作
2. 按韵脚押韵
3. 禁止真实人名地名
4. 体现{style}风格特点

直接输出歌词："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return "生成失败"


class VerifierAgent:
    @classmethod
    def execute(cls, context: Dict) -> Dict:
        lyrics = context.get("lyrics", "")
        emotion = context.get("emotion", "")
        keywords = context.get("keywords", [])

        prompt = f"""审查歌词（JSON）：
{{
    "overall": 8.5,
    "rhythm_quality": 8.0,
    "emotion_match": 9.0,
    "structure_compliance": 8.5,
    "rhyme_quality": 8.0,
    "keyword_coverage": 7.5,
    "issues": [],
    "targeted_repairs": {{"fix_rhyme": true}}
}}

歌词：{lyrics}
情感：{emotion}
关键词：{', '.join(keywords)}

直接输出JSON："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            return json.loads(result)
        except:
            return {"overall": 5.0, "issues": [], "targeted_repairs": {}}


class TitleAgent:
    @classmethod
    def execute(cls, context: Dict) -> str:
        lyrics = context.get("lyrics", "")
        emotion = context.get("emotion", "")

        prompt = f"""生成歌词标题（2-6字）：
歌词：{lyrics[:300]}
情感：{emotion}
直接输出："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return "无题"


# ==================== 主 Pipeline ====================

class EnhancedLyricPipeline:
    """
    v5.5 增强版 Pipeline
    整合：风格控制 + 结构模板 + 故事图谱 + 可解释生成
    """

    def __init__(self, api_key: str, api_base: str, model_name: str):
        self.llm = ChatOpenAI(
            openai_api_key=api_key,
            openai_api_base=api_base,
            model_name=model_name,
            temperature=0.8
        )
        self.constraint_lock = ConstraintLock()
        self.global_optimizer = GlobalOptimizer()
        self.diff_editor = DiffEditor()

    def run(
        self,
        chat_text: str,
        style: str = "流行",
        structure_template: str = "standard_pop",
        enable_explanation: bool = False
    ) -> Dict:
        """执行增强版流程"""
        context = {
            "raw_text": chat_text,
            "style": style,
            "structure_template": structure_template
        }

        print("\n" + "="*60)
        print("🎵 WeChatChat2Lyric-Agent v5.5 (Enhanced)")
        print("="*60)
        print(f"📂 聊天记录: {len(chat_text)} 字符")
        print(f"🎨 风格: {style}")
        print(f"📐 结构模板: {structure_template}")
        print(f"💡 可解释生成: {'开启' if enable_explanation else '关闭'}")
        print()

        # Phase 1: 基础处理
        print("[Phase 1] 清洗和分析...")
        context["cleaned_text"] = CleanerAgent.execute(context)
        analysis = EmotionAnalystAgent.execute(context)
        context.update(analysis)
        print(f"       情感: {context.get('emotion', '未知')}")
        print(f"       关键词: {', '.join(context.get('keywords', [])[:5])}")

        # Phase 2: 故事图谱提取
        print("\n[Phase 2] 提取故事图谱...")
        story_graph = StoryGraphExtractor.extract(chat_text, context.get("emotion", ""))
        context["story_graph"] = story_graph
        graph_context = StoryGraphExtractor.to_context(story_graph)
        context["graph_context"] = graph_context
        if story_graph.core_theme:
            print(f"       核心主题: {story_graph.core_theme}")
        print(f"       情感弧线: {' → '.join(story_graph.emotion_arc[:3]) if story_graph.emotion_arc else '未识别'}")

        # Phase 3: 骨架规划
        print("\n[Phase 3] 规划歌词骨架...")
        context["skeleton_plan"] = SkeletonPlannerAgent.execute(context)

        # Phase 4: 生成（带风格和结构控制）
        print("\n[Phase 4] 生成歌词...")
        context["lyrics"] = GeneratorAgent.execute(
            context,
            style=style,
            structure_template=structure_template
        )
        print(f"       生成: {len(context['lyrics'])} 字符")

        # Phase 5: 优化循环
        print("\n[Phase 5] 自优化...")
        iteration = 0
        max_iterations = 3

        while iteration < max_iterations:
            iteration += 1
            verification = VerifierAgent.execute(context)
            global_score = self.global_optimizer.compute_global_score({
                "rhythm": verification.get("rhythm_quality", 0),
                "emotion": verification.get("emotion_match", 0),
                "structure": verification.get("structure_compliance", 0),
                "rhyme": verification.get("rhyme_quality", 0),
                "keyword": verification.get("keyword_coverage", 0)
            })

            print(f"       第{iteration}轮: {global_score}/10")

            if global_score >= 7.5:
                print(f"       ✅ 达标")
                break

            # 差分修复
            edit_plan = self.diff_editor.generate_targeted_edit_plan(
                context["lyrics"],
                verification.get("issues", []),
                self.constraint_lock.get_locked_dims()
            )

            if edit_plan:
                # 应用修复
                context["lyrics"] = GeneratorAgent.execute(context, style=style)

        # Phase 6: 标题
        print("\n[Phase 6] 生成标题...")
        context["title"] = TitleAgent.execute(context)
        print(f"       标题: {context['title']}")

        # Phase 7: 可解释生成
        if enable_explanation:
            print("\n[Phase 7] 生成解释...")
            explanations = ExplainableGenerator.generate_explanation(
                context["lyrics"],
                chat_text,
                context.get("emotion", ""),
                context.get("keywords", [])
            )
            context["explanations"] = explanations
            explanation_text = ExplainableGenerator.format_explanations(explanations)
            context["explanation_text"] = explanation_text
            print(f"       生成 {len(explanations)} 句解释")

        return self._build_result(context)

    def _build_result(self, context: Dict) -> Dict:
        return {
            "title": context.get("title", "无题"),
            "style": context.get("style", "流行"),
            "structure_template": context.get("structure_template", "standard_pop"),
            "emotion": context.get("emotion", ""),
            "emotion_detail": context.get("emotion_detail", ""),
            "keywords": context.get("keywords", []),
            "story": context.get("story", ""),
            "story_graph": {
                "core_theme": context.get("story_graph", {}).core_theme if context.get("story_graph") else "",
                "emotion_arc": context.get("story_graph", {}).emotion_arc if context.get("story_graph") else []
            },
            "lyrics": context.get("lyrics", ""),
            "explanation_text": context.get("explanation_text", ""),
        }

    def print_result(self, result: Dict):
        print("\n" + "="*60)
        print("🎵 歌曲标题:", result["title"])
        print("🎨 风格:", result["style"])
        print("📐 结构:", result["structure_template"])
        print("🎧 情感:", result["emotion"], "-", result["emotion_detail"])
        print("🔑 关键词:", ", ".join(result["keywords"][:6]))
        if result.get("story_graph", {}).get("core_theme"):
            print("📖 核心主题:", result["story_graph"]["core_theme"])
        print("="*60)
        print("\n📝 歌词:")
        print("-"*40)
        print(result["lyrics"])
        print("-"*40)

        if result.get("explanation_text"):
            print(result["explanation_text"])


# ==================== 演示 ====================

def run_demo():
    """演示"""
    print("\n" + "="*60)
    print("🎵 WeChatChat2Lyric-Agent v5.5 演示")
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

    print("\n📝 示例聊天记录：")
    print(demo_chat[:200] + "...\n")

    print("\n🎨 可用风格:", ", ".join(StyleController.list_styles()))
    print("📐 结构模板:", ", ".join(LyricStructureTemplate.TEMPLATES.keys()))

    # 选择配置
    style = input("\n选择风格 (默认甜蜜): ").strip() or "甜蜜"
    structure = input("选择结构模板 (默认standard_pop): ").strip() or "standard_pop"
    explain = input("开启可解释生成？(y/n，默认n): ").strip().lower() == 'y'

    pipeline = EnhancedLyricPipeline(API_KEY, API_BASE, MODEL_NAME)
    result = pipeline.run(demo_chat, style=style, structure_template=structure, enable_explanation=explain)
    pipeline.print_result(result)


# ==================== 主入口 ====================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--demo":
            run_demo()
        elif sys.argv[1] == "--help":
            print("""
使用：python chat2lyric_agent.py --demo
     python chat2lyric_agent.py --help

风格选项：甜蜜, 伤感, 治愈, 叙事, 民谣, 说唱, 摇滚, R&B, 古风
结构模板：standard_pop, simple, full, rap
            """)
        else:
            print("使用 --demo 运行演示")
    else:
        run_demo()
