"""
WeChatChat2Lyric-Agent v5.6
Control Policy Layer + Conflict Resolution

Phase 1 产品化升级：
1. Control Policy Layer（控制优先级系统）
2. Dynamic Priority Resolver（动态优先级解析）
3. Conflict Resolver（冲突调解器）
4. 简化风格选择（4种核心风格）
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

API_KEY = os.getenv("OPENAI_API_KEY")
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")

llm = ChatOpenAI(
    openai_api_key=API_KEY,
    openai_api_base=API_BASE,
    model_name=MODEL_NAME,
    temperature=0.8,
    streaming=False
)


# ==================== 控制优先级系统 ====================

@dataclass
class ControlPolicy:
    """控制策略"""
    story_priority: float = 0.5      # 故事/情感一致性
    emotion_priority: float = 0.3  # 情感匹配度
    style_priority: float = 0.15     # 风格一致性
    structure_priority: float = 0.05 # 结构合规性

    def to_dict(self) -> Dict:
        return {
            "story": self.story_priority,
            "emotion": self.emotion_priority,
            "style": self.style_priority,
            "structure": self.structure_priority
        }

    def get_conflict_weights(self, conflict_type: str) -> Dict[str, float]:
        """获取冲突时的权重"""
        base = self.to_dict()

        if conflict_type == "emotion_vs_style":
            # 情感和风格冲突时，以情感为主
            return {"emotion": 0.7, "style": 0.3}

        elif conflict_type == "story_vs_structure":
            # 故事和结构冲突时，以故事为主
            return {"story": 0.8, "structure": 0.2}

        elif conflict_type == "all":
            # 全面冲突时，使用基础权重
            return base

        return base


class ControlPolicyLayer:
    """
    控制策略层
    定义各维度优先级，解决冲突
    """

    # 预设策略
    PRESET_POLICIES = {
        # 情感优先（伤感、抒情类）
        "emotion_first": ControlPolicy(
            story_priority=0.4,
            emotion_priority=0.4,
            style_priority=0.15,
            structure_priority=0.05
        ),

        # 故事优先（叙事、民谣类）
        "story_first": ControlPolicy(
            story_priority=0.5,
            emotion_priority=0.25,
            style_priority=0.15,
            structure_priority=0.10
        ),

        # 风格优先（说唱、摇滚类）
        "style_first": ControlPolicy(
            story_priority=0.3,
            emotion_priority=0.2,
            style_priority=0.4,
            structure_priority=0.10
        ),

        # 均衡模式
        "balanced": ControlPolicy(
            story_priority=0.35,
            emotion_priority=0.35,
            style_priority=0.20,
            structure_priority=0.10
        ),
    }

    @classmethod
    def get_policy(cls, policy_name: str) -> ControlPolicy:
        """获取策略"""
        return cls.PRESET_POLICIES.get(policy_name, cls.PRESET_POLICIES["balanced"])

    @classmethod
    def auto_select_policy(cls, style: str, emotion: str) -> Tuple[ControlPolicy, str]:
        """
        根据风格和情感自动选择策略
        返回：(策略, 策略名)
        """
        # 说唱/摇滚 -> 风格优先
        if style in ["说唱", "摇滚", "R&B"]:
            return cls.PRESET_POLICIES["style_first"], "style_first"

        # 叙事/民谣 -> 故事优先
        if style in ["叙事", "民谣", "古风"]:
            return cls.PRESET_POLICIES["story_first"], "story_first"

        # 甜蜜/治愈 -> 情感优先
        if style in ["甜蜜", "治愈"] or "甜蜜" in emotion or "治愈" in emotion:
            return cls.PRESET_POLICIES["emotion_first"], "emotion_first"

        # 默认均衡
        return cls.PRESET_POLICIES["balanced"], "balanced"


# ==================== 冲突检测与调解 ====================

@dataclass
class ConflictReport:
    """冲突报告"""
    has_conflict: bool
    conflicts: List[str]
    resolution: str
    adjusted_weights: Dict[str, float]


class ConflictResolver:
    """
    冲突调解器
    检测并解决多维度冲突
    """

    @classmethod
    def detect_conflicts(
        cls,
        style: str,
        emotion: str,
        structure: str,
        story_graph
    ) -> List[str]:
        """检测潜在冲突"""
        conflicts = []

        # 风格 vs 情感冲突
        style_emotion_map = {
            "甜蜜": ["甜蜜", "幸福", "温馨"],
            "伤感": ["伤感", "忧郁", "悲伤"],
            "说唱": ["热血", "愤怒", "力量"],
            "摇滚": ["热血", "愤怒", "力量"],
        }

        expected_emotions = style_emotion_map.get(style, [])
        if expected_emotions and emotion:
            # 检查情感是否匹配风格
            emotion_match = any(e in emotion for e in expected_emotions)
            if not emotion_match and "未知" not in emotion:
                conflicts.append(f"风格'{style}'与情感'{emotion}'可能不匹配")

        # 故事弧线 vs 情感冲突
        if story_graph and story_graph.emotion_arc:
            arc = story_graph.emotion_arc
            if len(arc) >= 2:
                # 检查情感弧线是否合理
                if arc[0] == "peak" and arc[-1] == "low":
                    conflicts.append("情感弧线从高潮到低落，可能需要调整")

        return conflicts

    @classmethod
    def resolve(
        cls,
        conflicts: List[str],
        policy: ControlPolicy,
        style: str,
        emotion: str
    ) -> ConflictReport:
        """解决冲突，返回调解方案"""
        if not conflicts:
            return ConflictReport(
                has_conflict=False,
                conflicts=[],
                resolution="无冲突",
                adjusted_weights=policy.to_dict()
            )

        # 根据冲突类型调整权重
        adjusted = policy.to_dict()

        for conflict in conflicts:
            if "风格" in conflict and "情感" in conflict:
                # 风格与情感冲突，以情感为主
                adjusted = policy.get_conflict_weights("emotion_vs_style")
                resolution = "以情感为主，风格做让步"
            elif "情感弧线" in conflict:
                adjusted = policy.get_conflict_weights("story_vs_structure")
                resolution = "调整情感弧线，保持故事连贯性"
            else:
                resolution = "使用默认优先级"
                adjusted = policy.get_conflict_weights("all")

        return ConflictReport(
            has_conflict=True,
            conflicts=conflicts,
            resolution=resolution,
            adjusted_weights=adjusted
        )


# ==================== 统一评分函数 ====================

class UnifiedScoringFunction:
    """
    统一评分函数
    多目标优化，收敛检测
    """

    def __init__(self, weights: Dict[str, float] = None):
        # 默认权重
        self.weights = weights or {
            "story": 0.35,
            "emotion": 0.35,
            "style": 0.20,
            "structure": 0.10
        }

    def compute_score(self, verification: Dict) -> float:
        """计算综合分数"""
        score = (
            self.weights.get("story", 0.35) * verification.get("story_consistency", verification.get("emotion_match", 0)) +
            self.weights.get("emotion", 0.35) * verification.get("emotion_match", 0) +
            self.weights.get("style", 0.20) * verification.get("style_fit", 8.0) +
            self.weights.get("structure", 0.10) * verification.get("structure_compliance", 0)
        )
        return round(score, 2)

    def compute_detailed_scores(self, verification: Dict) -> Dict:
        """计算各维度分数"""
        return {
            "overall": self.compute_score(verification),
            "story_score": verification.get("story_consistency", verification.get("emotion_match", 0)),
            "emotion_score": verification.get("emotion_match", 0),
            "style_score": verification.get("style_fit", 8.0),
            "structure_score": verification.get("structure_compliance", 0),
            "rhythm_score": verification.get("rhythm_quality", 0),
            "rhyme_score": verification.get("rhyme_quality", 0),
        }

    def should_converge(self, scores: Dict, iteration: int, threshold: float = 7.5) -> Tuple[bool, str]:
        """判断是否应该收敛"""
        overall = scores.get("overall", 0)

        if overall >= threshold:
            return True, f"分数达标 ({overall})"

        if iteration >= 4:
            return True, f"达到最大迭代 ({iteration})"

        # 检查是否收敛（分数变化小于阈值）
        return False, f"继续优化 ({overall})"


# ==================== 风格控制器（简化版） ====================

@dataclass
class SimpleStyle:
    """简化风格"""
    name: str
    emoji: str
    description: str
    policy: str  # 对应控制策略


SIMPLE_STYLES = {
    "💗 甜蜜": SimpleStyle("甜蜜", "💗", "温暖甜蜜，适合情侣", "emotion_first"),
    "💔 伤感": SimpleStyle("伤感", "💔", "忧郁抒情，触动心弦", "emotion_first"),
    "🔥 说唱": SimpleStyle("说唱", "🔥", "节奏强劲，押韵密集", "style_first"),
    "🌿 治愈": SimpleStyle("治愈", "🌿", "温暖疗愈，给人力量", "emotion_first"),
    "🎸 摇滚": SimpleStyle("摇滚", "🎸", "力量感强，情绪爆发", "style_first"),
    "📖 叙事": SimpleStyle("叙事", "📖", "讲故事，有画面感", "story_first"),
    "🎻 民谣": SimpleStyle("民谣", "🎻", "质朴自然，文艺清新", "story_first"),
    "🎹 R&B": SimpleStyle("R&B", "🎹", "丝滑 R&B 风格", "style_first"),
}


# ==================== 故事图谱 ====================

@dataclass
class StoryNode:
    type: str
    content: str
    importance: float = 1.0


@dataclass
class StoryGraph:
    nodes: List[StoryNode] = field(default_factory=list)
    emotion_arc: List[str] = field(default_factory=list)
    core_theme: str = ""


class StoryGraphExtractor:
    @classmethod
    def extract(cls, chat_text: str, emotion: str) -> StoryGraph:
        prompt = f"""从聊天记录中提取故事图谱：

聊天记录：
{chat_text}

情感基调：{emotion}

输出JSON：
{{
    "nodes": [
        {{"type": "emotion_event", "content": "描述", "importance": 0.9}}
    ],
    "emotion_arc": ["起点", "发展", "高潮", "结尾"],
    "core_theme": "核心主题"
}}

直接输出JSON："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            data = json.loads(result)

            nodes = [
                StoryNode(type=n.get("type", "event"), content=n.get("content", ""), importance=n.get("importance", 1.0))
                for n in data.get("nodes", [])
            ]
            return StoryGraph(nodes=nodes, emotion_arc=data.get("emotion_arc", []), core_theme=data.get("core_theme", ""))
        except:
            return StoryGraph()


# ==================== 可解释生成 ====================

@dataclass
class LyricExplanation:
    line: str
    source_chat: str
    emotion_reason: str
    rhyme_explanation: str


class ExplainableGenerator:
    @classmethod
    def generate_explanation(cls, lyrics: str, chat_text: str, emotion: str, keywords: List[str]) -> List[LyricExplanation]:
        prompt = f"""为歌词生成解释：

歌词：{lyrics}
聊天：{chat_text}
情感：{emotion}

输出JSON：
{{
    "explanations": [
        {{
            "line": "歌词",
            "source_chat": "对应聊天",
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
            return [
                LyricExplanation(
                    line=e.get("line", ""),
                    source_chat=e.get("source_chat", ""),
                    emotion_reason=e.get("emotion_reason", ""),
                    rhyme_explanation=e.get("rhyme_explanation", "")
                )
                for e in data.get("explanations", [])
            ]
        except:
            return []

    @classmethod
    def format_explanations(cls, explanations: List[LyricExplanation]) -> str:
        if not explanations:
            return ""
        parts = ["\n" + "="*50, "📖 歌词解释", "="*50]
        for i, exp in enumerate(explanations, 1):
            parts.append("\n【第" + str(i) + "句】" + exp.line)
            parts.append("   来源：" + exp.source_chat)
            parts.append("   设计：" + exp.emotion_reason)
        return "\n".join(parts)


# ==================== Agent 实现 ====================

class CleanerAgent:
    @classmethod
    def execute(cls, context: Dict) -> str:
        raw_text = context.get("raw_text", "")
        lines = raw_text.split('\n')
        cleaned_lines = []

        timestamp_pattern = r'\d{4}[/\-]\d{1,2}[/\-]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?'
        system_patterns = [r'^以上是打招呼内容', r'^以上是正文内容', r'^点击添加备注', r'^---\s*$', r'^\s*$', r'^【.*】$']

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

        prompt = f"""分析聊天记录（JSON）：
{{
    "emotion": "情感",
    "emotion_detail": "细化",
    "keywords": ["词1", "词2", "词3"],
    "story": "故事线"
}}

聊天：{cleaned_text}
直接输出JSON："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            return json.loads(result)
        except:
            return {"emotion": "未知", "emotion_detail": "", "keywords": [], "story": ""}


class GeneratorAgent:
    @classmethod
    def execute(cls, context: Dict, style: str, policy: ControlPolicy) -> str:
        emotion = context.get("emotion", "")
        emotion_detail = context.get("emotion_detail", "")
        keywords = context.get("keywords", [])
        story = context.get("story", "")
        graph_context = context.get("graph_context", "")
        style_profile = {
            "甜蜜": "甜蜜、温馨、幸福",
            "伤感": "伤感、忧郁、怀旧",
            "说唱": "说唱风格、节奏感强、押韵密集",
            "治愈": "治愈、希望、温暖",
            "摇滚": "摇滚风格、力量感强",
            "叙事": "叙事性强、有画面感",
            "民谣": "民谣风格、质朴自然",
            "R&B": "R&B风格、丝滑性感"
        }

        prompt = f"""基于聊天创作歌词：

情感：{emotion} - {emotion_detail}
风格：{style_profile.get(style, style)}
故事：{story}
关键词：{', '.join(keywords)}

{graph_context}

要求：
1. 主歌4句 + 副歌4句 + 主歌2 4句 + 副歌4句
2. 按韵脚押韵（ang/ian/ou/en）
3. 禁止真实人名地名
4. 体现{style}风格

直接输出歌词："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return "生成失败"


class VerifierAgent:
    @classmethod
    def execute(cls, context: Dict, style: str) -> Dict:
        lyrics = context.get("lyrics", "")
        emotion = context.get("emotion", "")
        keywords = context.get("keywords", [])

        style_expected = {
            "甜蜜": "温馨幸福",
            "伤感": "忧郁悲伤",
            "说唱": "节奏强劲",
            "治愈": "温暖治愈",
        }

        prompt = f"""审查歌词（JSON）：
{{
    "overall": 8.5,
    "emotion_match": 8.0,
    "style_fit": 8.0,
    "structure_compliance": 8.5,
    "rhythm_quality": 8.0,
    "rhyme_quality": 8.0,
    "story_consistency": 8.0,
    "issues": [],
    "targeted_repairs": {{"fix_rhyme": true}}
}}

歌词：{lyrics}
情感：{emotion}
风格：{style}（期望：{style_expected.get(style, "")}）

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
        prompt = f"""生成标题（2-6字）：
歌词：{lyrics[:300]}
直接输出："""
        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return "无题"


# ==================== 主 Pipeline ====================

class ControlledLyricPipeline:
    """
    v5.6 控制型歌词生成 Pipeline
    核心：Control Policy Layer + Conflict Resolution
    """

    def __init__(self, api_key: str, api_base: str, model_name: str):
        self.llm = ChatOpenAI(
            openai_api_key=api_key,
            openai_api_base=api_base,
            model_name=model_name,
            temperature=0.8
        )
        self.scoring = UnifiedScoringFunction()
        self.conflict_resolver = ConflictResolver()

    def run(
        self,
        chat_text: str,
        style: str = "甜蜜",
        enable_explanation: bool = False
    ) -> Dict:
        """执行带控制的生成流程"""
        context = {
            "raw_text": chat_text,
            "style": style
        }

        print("\n" + "="*60)
        print("🎵 WeChatChat2Lyric-Agent v5.6 (Controlled Generation)")
        print("="*60)
        print(f"📂 聊天记录: {len(chat_text)} 字符")
        print(f"🎨 风格: {style}")
        print(f"💡 可解释生成: {'开启' if enable_explanation else '关闭'}")

        # Step 1: 清洗和分析
        print("\n[Step 1] 清洗和分析...")
        context["cleaned_text"] = CleanerAgent.execute(context)
        analysis = EmotionAnalystAgent.execute(context)
        context.update(analysis)
        print(f"       情感: {context.get('emotion', '未知')}")

        # Step 2: 故事图谱
        print("\n[Step 2] 提取故事图谱...")
        story_graph = StoryGraphExtractor.extract(chat_text, context.get("emotion", ""))
        context["story_graph"] = story_graph
        graph_context = ""
        if story_graph.nodes:
            graph_context = "【故事节点】" + " | ".join([n.content for n in story_graph.nodes[:3]])
        context["graph_context"] = graph_context

        # Step 3: 控制策略选择（核心新功能）
        print("\n[Step 3] 选择控制策略...")
        policy, policy_name = ControlPolicyLayer.auto_select_policy(style, context.get("emotion", ""))
        context["policy"] = policy
        print(f"       策略: {policy_name}")
        print(f"       权重: 故事{policy.story_priority:.0%} | 情感{policy.emotion_priority:.0%} | 风格{policy.style_priority:.0%} | 结构{policy.structure_priority:.0%}")

        # Step 4: 冲突检测
        print("\n[Step 4] 检测冲突...")
        conflicts = self.conflict_resolver.detect_conflicts(
            style,
            context.get("emotion", ""),
            "standard_pop",
            story_graph
        )

        if conflicts:
            print(f"       ⚠️ 检测到冲突: {conflicts[0]}")
            report = self.conflict_resolver.resolve(conflicts, policy, style, context.get("emotion", ""))
            print(f"       → 解决方案: {report.resolution}")
            context["adjusted_weights"] = report.adjusted_weights
            # 更新评分权重
            self.scoring.weights = report.adjusted_weights
        else:
            print(f"       ✅ 无冲突")

        # Step 5: 生成
        print("\n[Step 5] 生成歌词...")
        context["lyrics"] = GeneratorAgent.execute(context, style=style, policy=policy)
        print(f"       生成: {len(context['lyrics'])} 字符")

        # Step 6: 验证和收敛
        print("\n[Step 6] 验证和收敛...")
        iteration = 0
        max_iterations = 3

        while iteration < max_iterations:
            iteration += 1

            verification = VerifierAgent.execute(context, style)
            scores = self.scoring.compute_detailed_scores(verification)
            context["verification"] = verification

            print(f"       第{iteration}轮: 整体{scores['overall']:.1f} | 情感{scores['emotion_score']:.1f} | 风格{scores['style_score']:.1f}")

            should_stop, reason = self.scoring.should_converge(scores, iteration)
            if should_stop:
                print(f"       ✅ {reason}")
                break

            # 重新生成
            context["lyrics"] = GeneratorAgent.execute(context, style=style, policy=policy)

        # Step 7: 标题
        print("\n[Step 7] 生成标题...")
        context["title"] = TitleAgent.execute(context)
        print(f"       标题: {context['title']}")

        # Step 8: 可解释生成
        if enable_explanation:
            print("\n[Step 8] 生成解释...")
            explanations = ExplainableGenerator.generate_explanation(
                context["lyrics"],
                chat_text,
                context.get("emotion", ""),
                context.get("keywords", [])
            )
            context["explanations"] = explanations
            context["explanation_text"] = ExplainableGenerator.format_explanations(explanations)

        return self._build_result(context)

    def _build_result(self, context: Dict) -> Dict:
        return {
            "title": context.get("title", "无题"),
            "style": context.get("style", "流行"),
            "policy": context.get("policy", ControlPolicy()).to_dict() if context.get("policy") else {},
            "emotion": context.get("emotion", ""),
            "emotion_detail": context.get("emotion_detail", ""),
            "keywords": context.get("keywords", []),
            "story": context.get("story", ""),
            "story_graph": {
                "core_theme": context.get("story_graph", StoryGraph()).core_theme if context.get("story_graph") else "",
                "emotion_arc": context.get("story_graph", StoryGraph()).emotion_arc if context.get("story_graph") else []
            },
            "lyrics": context.get("lyrics", ""),
            "explanation_text": context.get("explanation_text", ""),
        }

    def print_result(self, result: Dict):
        print("\n" + "="*60)
        print("🎵 歌曲标题:", result["title"])
        print("🎨 风格:", result["style"])
        print("📊 控制策略:", result.get("policy", {}))

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
    print("🎵 WeChatChat2Lyric-Agent v5.6 演示")
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

    print("\n🎨 简化风格选择（输入数字）：")
    for i, (name, s) in enumerate(SIMPLE_STYLES.items(), 1):
        print(f"   {i}. {name} - {s.description}")

    choice = input("\n选择风格 (1-8，默认1甜蜜): ").strip() or "1"
    try:
        idx = int(choice) - 1
        style_names = list(SIMPLE_STYLES.keys())
        if 0 <= idx < len(style_names):
            selected_style = SIMPLE_STYLES[style_names[idx]].name
        else:
            selected_style = "甜蜜"
    except:
        selected_style = "甜蜜"

    explain = input("开启可解释生成？(y/n，默认n): ").strip().lower() == 'y'

    pipeline = ControlledLyricPipeline(API_KEY, API_BASE, MODEL_NAME)
    result = pipeline.run(demo_chat, style=selected_style, enable_explanation=explain)
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

风格：甜蜜、伤感、说唱、治愈、摇滚、叙事、民谣、R&B
            """)
        else:
            print("使用 --demo 运行演示")
    else:
        run_demo()
