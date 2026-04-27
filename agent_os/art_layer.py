"""
v8.0 Agent OS - Art Generation Layer（人格化人类层）
=====================================
Core upgrade: Human Profile System

Pipeline:
微信输入 → ChatCompression → HookGenerator → LyricRenderer → HumanRewriteLayer(with Profile)

v8.0 核心升级：
1. HumanProfile - 人格控制，不同人格不同噪声分布
2. 6种人格类型：tsundere/suppressed/downward/calm_collapse/nostalgic/resigned
3. 情绪自动检测人格类型

效果对比（同一输入：你还是忘不了你）：
- 嘴硬型：我早该忘了你……好吧没有
- 压抑型：我还是/忘不了你
- emo型：我还是忘不了你/忘不了一点

v7.9.1 -> v8.0 核心变化：
❌ 之前：噪声强度控制"多少"
✅ 现在：人格控制"哪种噪声分布"
"""

import os
import sys
import json
import time
import hashlib
import threading
import copy
from typing import Dict, List, Optional, Any, Set, FrozenSet
from dataclasses import dataclass, field
from enum import Enum, auto
from dotenv import load_dotenv

# ==================== Config ====================
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")
MAX_WORKERS = int(os.getenv("MAX_AGENTS", "3"))

# Hook标记符号（Windows GBK兼容）
HOOK_PREFIX = "❗" if sys.stdout.encoding and "utf" in sys.stdout.encoding.lower() else "!"


# ==================== LLM ====================

def llm(prompt: str, temp: float = 0.8) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY, base_url=API_BASE)
    try:
        return client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=temp
        ).choices[0].message.content
    except Exception as e:
        return f"LLM Error: {e}"


# ==================== Art Layer: Emotion Vector ====================

class EmotionDimension(Enum):
    SADNESS = "sadness"
    NOSTALGIA = "nostalgia"
    JOY = "joy"
    ANGER = "anger"
    WARMTH = "warmth"
    LONELINESS = "loneliness"
    HOPE = "hope"
    REGRET = "regret"


@dataclass
class EmotionVector:
    """
    EmotionVector - emotional state representation
    """
    sadness: float = 0.0
    nostalgia: float = 0.0
    joy: float = 0.0
    anger: float = 0.0
    warmth: float = 0.0
    loneliness: float = 0.0
    hope: float = 0.0
    regret: float = 0.0

    def get_primary(self) -> tuple:
        emotions = {
            "sadness": self.sadness,
            "nostalgia": self.nostalgia,
            "joy": self.joy,
            "anger": self.anger,
            "warmth": self.warmth,
            "loneliness": self.loneliness,
            "hope": self.hope,
            "regret": self.regret
        }
        primary = max(emotions, key=emotions.get)
        return (primary, emotions[primary])

    def to_prompt_context(self) -> str:
        primary, intensity = self.get_primary()
        context_map = {
            "sadness": "伤感忧郁",
            "nostalgia": "怀旧温暖",
            "joy": "欢快明亮",
            "anger": "激昂慷慨",
            "warmth": "温暖治愈",
            "loneliness": "孤独寂寥",
            "hope": "希望憧憬",
            "regret": "遗憾惆怅"
        }
        return context_map.get(primary, "")

    def merge(self, other: 'EmotionVector', weight: float = 0.5) -> 'EmotionVector':
        return EmotionVector(
            sadness=self.sadness * (1-weight) + other.sadness * weight,
            nostalgia=self.nostalgia * (1-weight) + other.nostalgia * weight,
            joy=self.joy * (1-weight) + other.joy * weight,
            anger=self.anger * (1-weight) + other.anger * weight,
            warmth=self.warmth * (1-weight) + other.warmth * weight,
            loneliness=self.loneliness * (1-weight) + other.loneliness * weight,
            hope=self.hope * (1-weight) + other.hope * weight,
            regret=self.regret * (1-weight) + other.regret * weight
        )


# ==================== Art Layer: Lyric Rhythm Spec ====================

class LineLength(Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class RhymePattern(Enum):
    AABB = "aabb"
    ABAB = "abab"
    FREE = "free"


class HookPosition(Enum):
    FIRST_LINE = "first"
    THIRD_LINE = "third"
    LAST_LINE = "last"
    BRIDGE = "bridge"


@dataclass
class LyricRhythmSpec:
    """
    LyricRhythmSpec - lyric rhythm structure specification
    v7.8: 支持从 EmotionBias 自适应生成
    """
    line_length: LineLength = LineLength.MEDIUM
    rhyme_pattern: RhymePattern = RhymePattern.AABB
    hook_position: HookPosition = HookPosition.LAST_LINE

    structure: Dict[str, int] = field(default_factory=lambda: {
        "verse1": 4,
        "chorus": 4,
        "verse2": 4,
        "bridge": 2
    })

    tempo: str = "moderate"

    @classmethod
    def from_emotion_bias(cls, bias: 'EmotionBias') -> 'LyricRhythmSpec':
        """
        v7.8: 从 EmotionBias 自适应生成 LyricRhythmSpec
        """
        hook_map = {
            "first": HookPosition.FIRST_LINE,
            "third": HookPosition.THIRD_LINE,
            "last": HookPosition.LAST_LINE,
            "bridge": HookPosition.BRIDGE
        }

        rhythm_map = {
            "steady": RhymePattern.AABB,
            "build": RhymePattern.ABAB,
            "pulse": RhymePattern.AABB,
            "fade": RhymePattern.FREE
        }

        length_map = {
            "low_peak_fade": LineLength.LONG,
            "build_peak": LineLength.MEDIUM,
            "steady": LineLength.SHORT,
            "wave": LineLength.MEDIUM
        }

        return cls(
            line_length=length_map.get(bias.intensity_curve, LineLength.MEDIUM),
            rhyme_pattern=rhythm_map.get(bias.rhythm_bias, RhymePattern.AABB),
            hook_position=hook_map.get(bias.hook_position, HookPosition.LAST_LINE),
            tempo="slow" if bias.intensity_curve == "low_peak_fade" else "moderate"
        )

    def get_section_spec(self, section: str) -> str:
        lines = self.structure.get(section, 4)
        length_desc = {
            LineLength.SHORT: "短句",
            LineLength.MEDIUM: "中等长度",
            LineLength.LONG: "稍长句子"
        }.get(self.line_length, "标准长度")

        rhyme_desc = {
            RhymePattern.AABB: "偶数句押韵",
            RhymePattern.ABAB: "交叉押韵",
            RhymePattern.FREE: "自由押韵"
        }.get(self.rhyme_pattern, "标准韵律")

        return f"{length_desc}，{rhyme_desc}"


# ==================== Art Layer: Chat Compression ====================

class ChatCompressionLayer:
    """
    ChatCompressionLayer - chat to imagery compression
    """

    EMOTION_PATTERNS = {
        "嗯": ("cold_response", 0.3),
        "哦": ("cold_response", 0.4),
        "好吧": ("reluctant_accept", 0.2),
        "算了": ("give_up", 0.5),
        "晚安": ("night_ending", 0.6),
        "睡了": ("sleep_signal", 0.5),
        "再见": ("farewell", 0.4),
        "分手": ("breakup", 0.9),
        "不合适": ("incompatibility", 0.8),
        "累了": ("exhaustion", 0.7),
        "想你": ("longing", 0.8),
        "在吗": ("reach_out", 0.6),
        "记得": ("memory", 0.5),
    }

    IMAGERY_DICT = {
        "cold_response": ["冷风", "沉默", "白开水", "玻璃窗"],
        "night_ending": ["凌晨", "夜深", "手机屏幕", "最后一条消息"],
        "sleep_signal": ["关灯", "黑暗", "独处", "枕头"],
        "farewell": ["背影", "车站", "挥手", "远去"],
        "breakup": ["碎片", "眼泪", "日记本", "空房间"],
        "exhaustion": ["疲惫", "沉重", "石阶", "黄昏"],
        "longing": ["月亮", "思念", "照片", "等待"],
        "reach_out": ["试探", "光", "门铃", "心跳"],
        "memory": ["老歌", "照片", "雨声", "熟悉的街"],
        "silence": ["空白", "回声", "黑洞", "等待"],
        "withdrawn": ["删除", "痕迹消失", "烟雾", "消散"],
        "give_up": ["放手", "飘散", "终点", "释然"],
        "reluctant_accept": ["叹息", "妥协", "转身", "无奈"],
        "incompatibility": ["平行线", "两条路", "错位", "轨道"],
    }

    def compress(self, chat_messages: List[Dict]) -> Dict:
        events = []
        emotion_vector = EmotionVector()

        for msg in chat_messages:
            content = msg.get("content", "")
            sender = msg.get("sender", "")

            for pattern, (event_type, intensity) in self.EMOTION_PATTERNS.items():
                if pattern in content:
                    events.append({
                        "type": event_type,
                        "sender": sender,
                        "content": content,
                        "intensity": intensity
                    })
                    self._update_emotion(event_type, intensity, emotion_vector)

        imagery_tokens = self._generate_imagery(events)
        core_theme = self._extract_theme(events)

        return {
            "events": events,
            "emotion_vector": emotion_vector,
            "imagery_tokens": imagery_tokens,
            "core_theme": core_theme,
            "event_count": len(events)
        }

    def _update_emotion(self, event_type: str, intensity: float, vector: EmotionVector):
        emotion_map = {
            "cold_response": ("loneliness", 1.0),
            "night_ending": ("sadness", 0.7),
            "sleep_signal": ("loneliness", 0.6),
            "farewell": ("sadness", 0.5),
            "breakup": ("sadness", 1.0),
            "exhaustion": ("regret", 0.7),
            "longing": ("nostalgia", 0.9),
            "reach_out": ("hope", 0.5),
            "memory": ("nostalgia", 0.8),
            "silence": ("loneliness", 1.0),
            "withdrawn": ("sadness", 0.7),
            "give_up": ("regret", 0.6),
            "reluctant_accept": ("sadness", 0.4),
            "incompatibility": ("regret", 0.5),
        }

        if event_type in emotion_map:
            emotion, weight = emotion_map[event_type]
            current = getattr(vector, emotion)
            setattr(vector, emotion, current * 0.5 + intensity * weight * 0.5)

    def _generate_imagery(self, events: List[Dict]) -> List[str]:
        imagery = []
        for event in events:
            event_imagery = self.IMAGERY_DICT.get(event["type"], [])
            if event["intensity"] > 0.6 and event_imagery:
                imagery.append(event_imagery[0])
            elif event_imagery:
                imagery.append(event_imagery[-1])
        return list(set(imagery))[:6]

    def _extract_theme(self, events: List[Dict]) -> str:
        if not events:
            return "相遇与别离"

        event_types = [e["type"] for e in events]
        intensity = sum(e["intensity"] for e in events) / len(events) if events else 0

        theme_map = {
            ("breakup",): "分手后的独白",
            ("silence", "cold_response"): "沉默的距离",
            ("longing", "memory"): "思念与回忆",
            ("night_ending", "sleep_signal"): "深夜的告别",
            ("give_up", "reluctant_accept"): "放手的抉择",
        }

        for key, theme in theme_map.items():
            if all(kt in event_types for kt in key):
                return theme

        return "情感的流转" if intensity > 0.5 else "平凡的日常"


# ==================== Art Layer: Emotion Engine ====================

class EmotionEngine:
    """
    EmotionEngine - emotion-driven generation control
    """

    def __init__(self):
        self.emotion_vector: Optional[EmotionVector] = None
        self.history: List[EmotionVector] = []

    def set_emotion(self, emotion_vector: EmotionVector):
        self.emotion_vector = emotion_vector
        self.history.append(emotion_vector)

    def generate_emotion_context(self) -> str:
        if not self.emotion_vector:
            return ""

        primary, intensity = self.emotion_vector.get_primary()

        intensity_desc = ""
        if intensity > 0.7:
            intensity_desc = "浓烈的"
        elif intensity > 0.4:
            intensity_desc = "淡淡的"
        else:
            intensity_desc = "隐约的"

        return f"{intensity_desc}的情感"

    def get_generation_temperature(self) -> float:
        if not self.emotion_vector:
            return 0.8

        primary, intensity = self.emotion_vector.get_primary()

        if intensity > 0.7:
            return 0.7
        elif intensity > 0.4:
            return 0.8
        return 0.9


# ==================== Art Layer: Lyric Planner ====================

class LyricPlanner:
    """
    LyricPlanner - lyric structure planning
    """

    def __init__(self, rhythm_spec: LyricRhythmSpec = None):
        self.rhythm_spec = rhythm_spec or LyricRhythmSpec()

    def plan(self, emotion_vector: EmotionVector, imagery_tokens: List[str]) -> Dict:
        plan = {
            "sections": [],
            "hook_line": None,
            "rhyme_scheme": self.rhythm_spec.rhyme_pattern.value,
            "emotion_guidance": emotion_vector.to_prompt_context()
        }

        section_names = ["verse1", "chorus", "verse2", "bridge"]
        section_descs = {
            "verse1": "主歌一：铺陈故事",
            "chorus": "副歌：情感高潮",
            "verse2": "主歌二：深入情感",
            "bridge": "桥段：转折或升华"
        }

        for section in section_names:
            lines = self.rhythm_spec.structure.get(section, 4)
            plan["sections"].append({
                "name": section,
                "description": section_descs[section],
                "lines": lines,
                "spec": self.rhythm_spec.get_section_spec(section)
            })

        hook_section_idx = {
            HookPosition.FIRST_LINE: 0,
            HookPosition.THIRD_LINE: 2,
            HookPosition.LAST_LINE: len(plan["sections"]) - 1,
            HookPosition.BRIDGE: len(plan["sections"]) - 1
        }.get(self.rhythm_spec.hook_position, 3)

        plan["hook_section"] = hook_section_idx
        plan["hook_line_idx"] = {
            HookPosition.FIRST_LINE: 0,
            HookPosition.THIRD_LINE: 2,
            HookPosition.LAST_LINE: -1,
            HookPosition.BRIDGE: -1
        }.get(self.rhythm_spec.hook_position, -1)

        return plan

    def generate_prompt_parts(
        self,
        compression_result: Dict,
        lyric_plan: Dict,
        narrative: Dict = None
    ) -> Dict:
        emotion_vector = compression_result["emotion_vector"]
        imagery = compression_result["imagery_tokens"]
        theme = compression_result["core_theme"]

        parts = {
            "theme": f"主题：{theme}",
            "emotion": f"情绪：{emotion_vector.to_prompt_context()}",
            "imagery": f"意象：{'、'.join(imagery[:4])}" if imagery else "意象：待定",
            "structure": self._format_structure(lyric_plan),
            "rhythm": f"韵律：{self.rhythm_spec.rhyme_pattern.value}式押韵",
            "hook": self._format_hook(lyric_plan)
        }

        # v9.2: 加入叙事骨架，引导LLM按叙事弧生成
        if narrative:
            narrative_context = self._format_narrative(narrative)
            parts["narrative"] = narrative_context

        return parts

    def _format_narrative(self, narrative: Dict) -> str:
        """v9.5: 格式化叙事骨架到提示词"""
        lines = ["\n叙事骨架（按此弧线展开歌词）："]
        arc_type = narrative.get("arc_type", "heartbreak")
        lines.append(f"叙事弧线：{arc_type}")

        frames = narrative.get("events", [])
        if frames:
            lines.append("叙事事件（每个事件扩2-3句）：")
            for frame in frames:
                # v9.5: events 是 List[SemanticFrame]
                lines.append(f"- [{frame.core}] {frame.trigger}")

        lines.append(f"叙事视角：第一人称（我对你说）")
        lines.append("歌词要求（严格遵守）：")
        lines.append("- 每个事件必须扩展成2-3句，不能只有一句")
        lines.append("- 句子之间要有画面感和情绪递进")
        lines.append("- 中间必须有转折句（如：后来我才明白/那一刻我才懂）")
        lines.append("- 不要抽象概括，要具体场景描写")
        lines.append("- 像歌词，不是改写聊天记录")

        return "\n".join(lines)

    def _format_structure(self, plan: Dict) -> str:
        lines = ["歌词结构："]
        for section in plan["sections"]:
            lines.append(f"- {section['description']}（{section['lines']}句）")
        return "\n".join(lines)

    def _format_hook(self, plan: Dict) -> str:
        hook_idx = plan.get("hook_line_idx", -1)
        hook_position_map = {
            0: "首句",
            2: "第三句",
            -1: "末句"
        }
        return f"Hook位置：{hook_position_map.get(hook_idx, '末句')}设钩"


# ==================== Art Layer: Style Preset ====================

class StylePreset(Enum):
    """歌词风格预设"""
    JAY_CHOU = "jay_chou"           # 周杰伦风格：含蓄、意象跳跃
    FOLK = "folk"                   # 民谣风格：叙事、直接
    HEARTBREAK = "heartbreak"       # 失恋风格：痛、回忆
    NOSTALGIC = "nostalgic"         # 怀旧风格：温暖、时光感
    DARKNESS = "darkness"           # 暗黑风格：压抑、释放


@dataclass
class StyleConfig:
    """风格配置"""
    name: str
    hook_patterns: List[str]       # hook 模板
    typical_imagery: List[str]      # 典型意象
    line_starters: List[str]        # 开头句式
    emotional_keywords: List[str]   # 情绪关键词


class StylePresetLibrary:
    """风格预设库"""

    PRESETS = {
        StylePreset.JAY_CHOU: StyleConfig(
            name="周杰伦",
            hook_patterns=[
                "窗外的麻雀{}",
                "{}在枫叶漫天飞的时候",
                "我{}的时候你会在哪里",
                "{}像藏在心底的秘密",
            ],
            typical_imagery=["枫叶", "麻雀", "稻香", "彩虹", "长城"],
            line_starters=["看着", "听着", "想着", "那年"],
            emotional_keywords=["遗憾", "怀念", "含蓄", "沉默"]
        ),
        StylePreset.FOLK: StyleConfig(
            name="民谣",
            hook_patterns=[
                "{}在{}/{}故事里",
                "我记得{}",
                "{}还在{}",
                "{}唱了一首歌",
            ],
            typical_imagery=["吉他", "酒吧", "南方", "北方", "火车"],
            line_starters=["那年", "后来", "他说", "我记得"],
            emotional_keywords=["叙事", "直接", "真诚", "远方"]
        ),
        StylePreset.HEARTBREAK: StyleConfig(
            name="失恋",
            hook_patterns=[
                "你还是{}",
                "{}已经不在了",
                "我在{}等你",
                "{}只有我一个人",
            ],
            typical_imagery=["空房间", "手机屏幕", "照片", "凌晨", "烟"],
            line_starters=["再也没有", "原来", "其实", "如果"],
            emotional_keywords=["痛", "回忆", "不舍", "释然"]
        ),
        StylePreset.NOSTALGIC: StyleConfig(
            name="怀旧",
            hook_patterns=[
                "{}像老歌",
                "{}在时光里",
                "{}年的{}",
                "{}还在放",
            ],
            typical_imagery=["老歌", "照片", "日记本", "CD", "信"],
            line_starters=["那时候", "忽然想起", "那年夏天", "多年后"],
            emotional_keywords=["温暖", "时光", "纯真", "回不去"]
        ),
        StylePreset.DARKNESS: StyleConfig(
            name="暗黑",
            hook_patterns=[
                "{}在夜里",
                "{}沉入",
                "{}无尽",
                "{}在尖叫",
            ],
            typical_imagery=["夜", "血", "伤口", "深渊", "灰烬"],
            line_starters=["撕裂", "沉没", "燃烧", "崩塌"],
            emotional_keywords=["压抑", "释放", "极端", "狂欢"]
        )
    }

    @classmethod
    def get_preset(cls, preset: StylePreset) -> StyleConfig:
        return cls.PRESETS.get(preset, cls.PRESETS[StylePreset.HEARTBREAK])

    @classmethod
    def detect_from_emotion(cls, emotion_vector: EmotionVector) -> StylePreset:
        """从情绪向量自动检测风格"""
        if emotion_vector.joy > 0.5:
            return StylePreset.FOLK
        elif emotion_vector.sadness > 0.6:
            return StylePreset.HEARTBREAK
        elif emotion_vector.nostalgia > 0.5:
            return StylePreset.NOSTALGIC
        elif emotion_vector.anger > 0.4:
            return StylePreset.DARKNESS
        elif emotion_vector.warmth > 0.4:
            return StylePreset.JAY_CHOU
        return StylePreset.HEARTBREAK


# ==================== Art Layer: Emotion Curve ====================

class EmotionCurve(Enum):
    """情绪曲线类型"""
    LOW_PEAK_FADE = "low_peak_fade"       # 低 → 高 → 消散
    BUILD_PEAK = "build_peak"             # 渐强 → 高潮
    WAVE = "wave"                          # 波浪起伏
    STEADY = "steady"                     # 平稳
    V_SHAPE = "v_shape"                   # 先低后高


@dataclass
class EmotionArc:
    """情绪弧线描述"""
    curve_type: EmotionCurve
    sections: List[str]  # 每个段落的情绪描述

    @classmethod
    def from_curve(cls, curve: EmotionCurve) -> 'EmotionArc':
        arc_map = {
            EmotionCurve.LOW_PEAK_FADE: [
                "开场：平静叙述",
                "发展：情绪积累",
                "副歌：爆发点",
                "尾声：余韵消散"
            ],
            EmotionCurve.BUILD_PEAK: [
                "铺垫：淡淡情绪",
                "推进：逐渐升温",
                "副歌：完全释放",
                "收尾：回归平静"
            ],
            EmotionCurve.WAVE: [
                "第一段：起",
                "过渡：落",
                "副歌：再起",
                "结尾：平静落地"
            ],
            EmotionCurve.STEADY: [
                "整体：稳定情绪",
                "副歌：微微加强",
                "回归：稳定"
            ],
            EmotionCurve.V_SHAPE: [
                "开场：低落",
                "中段：最低点",
                "副歌：上升",
                "结尾：希望"
            ]
        }
        return cls(curve_type=curve, sections=arc_map.get(curve, arc_map[EmotionCurve.STEADY]))


# ==================== Art Layer: Hook Generator ====================

class HookGenerator:
    """
    HookGenerator - 记忆点制造器

    核心功能：生成一句最打人的句子

    差距示例：
    没有hook：
    "我们聊了很多天，最后什么都没留下"

    有hook：
    "你还在联系人列表里，却再也不会亮起"
    """

    HOOK_TEMPLATES = {
        "contrast": [
            "{}还在/却{}",
            "{}是/但{}",
            "我{}的时候你{}",
            "你在/我在/他/她/它不在"
        ],
        "shock": [
            "{}才知道/已经{}",
            "原来/其实/到头来",
            "{}才是{}",
            "再也/永远/从来"
        ],
        "question": [
            "{}会{}吗",
            "{}还是{}",
            "{}在哪里/谁/什么/为什么"
        ],
        "image_alone": [
            "{}的{}",
            "{}还在{}",
            "只有{}记得"
        ],
        "time_marker": [
            "{}年{}",
            "{}/那天/那个/那个夏天",
            "多年后/某天/凌晨"
        ]
    }

    def __init__(self):
        self.last_hook = None

    def generate_hook(
        self,
        theme: str,
        emotion: EmotionVector,
        imagery: List[str],
        style: StylePreset = None,
        emotion_curve: EmotionCurve = None,
        profile: 'HumanProfile' = None
    ) -> str:
        """
        生成一句最打人的 hook

        v8.1: Hook 也会根据 profile 人格化
        """
        style_config = StylePresetLibrary.get_preset(style) if style else None

        # v8.4: 用最强情绪（而非主情绪），解决"局部 anger 爆发被整体 sadness 压制"的问题
        profile_strength = max(vars(emotion).values())

        # 根据情绪选择 hook 类型
        hook_type = self._select_hook_type(emotion, emotion_curve)

        # 填充模板
        hook = self._fill_hook_template(
            hook_type, theme, emotion, imagery, style_config
        )

        # v8.1: 应用人格到 Hook（使用 profile_strength 统一控制）
        if profile:
            hook = self._apply_profile_to_hook(hook, profile, profile_strength)

        self.last_hook = hook
        return hook

    def _apply_profile_to_hook(self, hook: str, profile: 'HumanProfile', profile_strength: float = 1.0) -> str:
        """
        v8.1 核心：Hook 人格化
        v8.3: Hook 概率与正文统一，使用 profile_strength

        让 Hook 和 Profile 对齐，解决"第一眼有性格"的问题

        示例：
        原始 Hook：你还是忘不了你

        tsundere：不是……你还是会忘不掉我……好吧没有
        suppressed：你还是忘不掉我
                    （换行，压抑感）
        downward： 你还是忘不掉我
                  忘不掉
        calm_collapse：我以为我已经忘了你……但没有
        """
        import random

        # 移除Hook标记（稍后会加回）
        clean_hook = hook.replace(HOOK_PREFIX, "").replace("!", "").strip()
        if not clean_hook:
            return hook

        # 根据人格类型处理 Hook
        profile_type = profile.profile_type

        if profile_type == HumanProfileType.TSUNDERE:
            # 嘴硬型：自打脸（v8.3: 概率 × profile_strength）
            if random.random() < min(1.0, profile.correction * profile_strength):
                prefixes = ["不是……", "好吧……", "……算了……"]
                prefix = random.choice(prefixes)
                suffix_prob = min(1.0, profile.hesitation * profile_strength)
                return f"{HOOK_PREFIX} {prefix}{clean_hook}……{'没有' if random.random() < suffix_prob else '吧'}"

        elif profile_type == HumanProfileType.SUPPRESSED:
            # 压抑型：换行，制造停顿感（用 fragmentation 控制断句）
            if len(clean_hook) > 6:
                words = clean_hook.split("，")
                if len(words) >= 2:
                    return f"{HOOK_PREFIX} {words[0]}\n{HOOK_PREFIX} {words[1]}"
                # 单句则断在中途
                mid = len(clean_hook) // 2
                return f"{HOOK_PREFIX} {clean_hook[:mid]}\n{HOOK_PREFIX} {clean_hook[mid:]}"

        elif profile_type == HumanProfileType.DOWNWARD_SPIRAL:
            # emo型：半句回收（v8.3: 概率 × profile_strength）
            prob = min(1.0, profile.repetition * profile_strength)
            if random.random() < prob and len(clean_hook) > 4:
                # 取后半句关键词
                suffix = clean_hook[-3:] if len(clean_hook) > 3 else clean_hook
                return f"{HOOK_PREFIX} {clean_hook}\n{HOOK_PREFIX} {suffix}"

        elif profile_type == HumanProfileType.CALM_COLLAPSE:
            # 冷静崩溃型：理性开头 → 崩（v8.3: 概率 × profile_strength）
            if random.random() < min(1.0, profile.correction * profile_strength):
                return f"{HOOK_PREFIX} 我以为我已经{clean_hook}……但没有"
            return f"{HOOK_PREFIX} 我以为{clean_hook}……其实没有"

        elif profile_type == HumanProfileType.NOSTALGIC:
            # 怀旧型：加时间感（v8.3: 概率 × profile_strength）
            if random.random() < min(1.0, profile.hesitation * profile_strength):
                return f"{HOOK_PREFIX} 那年，{clean_hook}"
            return f"{HOOK_PREFIX} {clean_hook}的时候"

        elif profile_type == HumanProfileType.RESIGNED:
            # 认命型：无奈收尾（v8.3: 概率 × profile_strength）
            if random.random() < min(1.0, profile.hesitation * profile_strength):
                return f"{HOOK_PREFIX} {clean_hook}……算了"
            return f"{HOOK_PREFIX} {clean_hook}……就这样吧"

        # 默认：轻微处理
        return f"{HOOK_PREFIX} {clean_hook}"

    def _select_hook_type(self, emotion: EmotionVector, curve: EmotionCurve) -> str:
        """根据情绪选择 hook 类型"""
        # 波浪曲线 → 对比型
        if curve == EmotionCurve.WAVE:
            return "contrast"
        # 高强度情绪 → 冲击型
        elif emotion.get_primary()[1] > 0.6:
            return "shock"
        # 低潮情绪 → 意象孤独型
        elif emotion.loneliness > 0.4 or emotion.sadness > 0.4:
            return "image_alone"
        # 怀旧 → 时间标记型
        elif emotion.nostalgia > 0.4:
            return "time_marker"
        # 默认 → 问句型
        return "question"

    def _fill_hook_template(
        self,
        hook_type: str,
        theme: str,
        emotion: EmotionVector,
        imagery: List[str],
        style_config: StyleConfig = None
    ) -> str:
        """填充 hook 模板"""
        templates = self.HOOK_TEMPLATES.get(hook_type, self.HOOK_TEMPLATES["question"])

        if style_config and style_config.hook_patterns:
            # 使用风格预设的模板
            import random
            template = random.choice(style_config.hook_patterns)
            imagery_pool = style_config.typical_imagery + imagery
        else:
            import random
            template = random.choice(templates)
            imagery_pool = imagery if imagery else ["夜", "风", "梦"]

        # 填充数据
        try:
            # 简单随机填充
            fills = []
            for _ in range(template.count("{}")):
                fills.append(random.choice(imagery_pool) if imagery_pool else "记忆")

            hook = template.format(*fills[:template.count("{}")])

            # 如果填充后不完整，做一个合理的默认
            if "{}" in hook:
                hook = hook.replace("{}", random.choice(imagery_pool))
        except:
            hook = f"原来{theme}，才明白"

        return hook

    def enhance_hook_variants(self, base_hook: str, emotion: EmotionVector) -> List[str]:
        """
        生成 hook 的多个变体（用于不同位置）
        """
        variants = [
            base_hook,  # 原版
            f"——{base_hook}",  # 加强版
            f"{base_hook}...",  # 省略版
            f"其实{base_hook}",  # 转折版
        ]

        # 根据情绪调整
        if emotion.sadness > 0.5:
            variants.append(f"再也没有{base_hook}")
        if emotion.nostalgia > 0.4:
            variants.append(f"那年{base_hook}")

        return variants[:4]


# ==================== Art Layer: Human Profile System (v8.0) ====================

class HumanProfileType(Enum):
    """人格类型"""
    TSUNDERE = "tsundere"           # 嘴硬型：自打脸、自我推翻
    SUPPRESSED = "suppressed"       # 压抑型：短句、空白、断句
    DOWNWARD_SPIRAL = "downward"   # emo型：重复强化、情绪下沉
    CALM_COLLAPSE = "calm_collapse" # 冷静崩溃型：理性开头 → 崩
    NOSTALGIC = "nostalgic"        # 怀旧型：时光感、倒带
    RESIGNED = "resigned"          # 认命型：无奈、接受


@dataclass
class HumanProfile:
    """
    HumanProfile - 人格写法控制 v8.0

    控制噪声分布权重，而不是噪声本身

    参数：
    - profile_type: 人格类型（用于比较）
    - hesitation: 犹豫程度（语气词、停顿）
    - repetition: 重复程度（半句回收、变体重复）
    - correction: 自我纠正程度（推翻刚说的话）
    - fragmentation: 断句程度（句子断裂、空白）
    """
    profile_type: HumanProfileType
    name: str
    hesitation: float      # 0.0-1.0
    repetition: float       # 0.0-1.0
    correction: float       # 0.0-1.0
    fragmentation: float    # 0.0-1.0

    # 特殊标签
    prefix_patterns: List[str] = field(default_factory=list)   # 句首特殊模式
    suffix_patterns: List[str] = field(default_factory=list)  # 句尾特殊模式
    echo_keywords: List[str] = field(default_factory=list)     # 允许echo的关键词


class HumanProfileLibrary:
    """人格预设库"""

    PROFILES = {
        HumanProfileType.TSUNDERE: HumanProfile(
            profile_type=HumanProfileType.TSUNDERE,
            name="嘴硬型",
            hesitation=0.2,
            repetition=0.3,
            correction=0.8,  # 核心：自我推翻多
            fragmentation=0.4,
            prefix_patterns=["不是", "好吧", "……算了"],
            suffix_patterns=["……没有", "……好吧", "……好吧没有"],
            echo_keywords=["早", "就", "以为了"]
        ),
        HumanProfileType.SUPPRESSED: HumanProfile(
            profile_type=HumanProfileType.SUPPRESSED,
            name="压抑型",
            hesitation=0.6,
            repetition=0.2,
            correction=0.2,
            fragmentation=0.7,  # 核心：断句多
            prefix_patterns=[],
            suffix_patterns=["……", "。", "。"],
            echo_keywords=["走", "等", "看", "想"]
        ),
        HumanProfileType.DOWNWARD_SPIRAL: HumanProfile(
            profile_type=HumanProfileType.DOWNWARD_SPIRAL,
            name="emo型",
            hesitation=0.4,
            repetition=0.8,   # 核心：重复强化情绪
            correction=0.3,
            fragmentation=0.5,
            prefix_patterns=["其实", "明明"],
            suffix_patterns=["啊", "吧", "……吧"],
            echo_keywords=["忘", "痛", "爱", "想", "哭"]
        ),
        HumanProfileType.CALM_COLLAPSE: HumanProfile(
            profile_type=HumanProfileType.CALM_COLLAPSE,
            name="冷静崩溃型",
            hesitation=0.2,
            repetition=0.4,
            correction=0.6,
            fragmentation=0.6,
            prefix_patterns=["其实", "我知道", "应该"],
            suffix_patterns=["但没有", "……没有", "……做不到"],
            echo_keywords=["应该", "知道", "明白"]
        ),
        HumanProfileType.NOSTALGIC: HumanProfile(
            profile_type=HumanProfileType.NOSTALGIC,
            name="怀旧型",
            hesitation=0.5,
            repetition=0.5,
            correction=0.3,
            fragmentation=0.3,
            prefix_patterns=["那年", "忽然", "那时候"],
            suffix_patterns=["的时候", "……吧", "……呢"],
            echo_keywords=["年", "夏天", "记得", "从前"]
        ),
        HumanProfileType.RESIGNED: HumanProfile(
            profile_type=HumanProfileType.RESIGNED,
            name="认命型",
            hesitation=0.3,
            repetition=0.3,
            correction=0.5,
            fragmentation=0.4,
            prefix_patterns=["算了", "就这样", "无所谓"],
            suffix_patterns=["……算了", "……就这样吧", "……也没什么"],
            echo_keywords=["算", "就这样", "无所谓"]
        )
    }

    @classmethod
    def get_profile(cls, profile_type: HumanProfileType) -> HumanProfile:
        """获取人格预设"""
        return cls.PROFILES.get(profile_type, cls.PROFILES[HumanProfileType.DOWNWARD_SPIRAL])

    @classmethod
    def detect_from_emotion(cls, emotion_vector) -> HumanProfileType:
        """从情绪向量自动检测人格类型"""
        if emotion_vector.anger > 0.5:
            return HumanProfileType.CALM_COLLAPSE
        elif emotion_vector.sadness > 0.6:
            return HumanProfileType.DOWNWARD_SPIRAL
        elif emotion_vector.regret > 0.5:
            return HumanProfileType.SUPPRESSED
        elif emotion_vector.nostalgia > 0.5:
            return HumanProfileType.NOSTALGIC
        elif emotion_vector.loneliness > 0.4:
            return HumanProfileType.RESIGNED
        return HumanProfileType.TSUNDERE


# ==================== Art Layer: Human Rewrite Layer ====================

class HumanRewriteLayer:
    """
    HumanRewriteLayer - 人类化算子 v8.0（人格驱动版）

    核心升级：
    1. Human Profile - 人格控制，不同人格不同噪声分布
    2. Emotion-Aware Noise - 噪声跟情绪走
    3. Hook Protection - Hook行绝对不被污染
    4. Echo Enhancement - 半句回收增强

    效果对比：
    同一输入：，我还是忘不了你

    嘴硬型：
    我早该忘了你……好吧没有

    压抑型：
    我还是
    忘不了你

    emo型：
    我还是忘不了你
    忘不了一点
    """

    # 语气词池
    FILLER_WORDS = ["啊", "呢", "嗯", "呀", "嘛", "哦", "哦对了", "其实", "就是", "那种", "好吧", "嗯……", "就", "真的", "好像"]

    # 自我纠正模式
    SELF_CORRECTION_PATTERNS = [
        ("不是", "是"),
        ("不是", "而是"),
        ("应该", "但又"),
        ("想", "但又不敢"),
        ("以为", "其实"),
        ("早该", "可是"),
        ("早", "……好吧"),
    ]

    def __init__(self, intensity: float = 0.3, profile: HumanProfile = None):
        """
        Args:
            intensity: 噪声强度 0.0-1.0，默认0.3（轻度人类化）
            profile: 人格预设，默认为 emo型（downward_spiral）
        """
        self.intensity = intensity
        self.profile = profile or HumanProfileLibrary.get_profile(HumanProfileType.DOWNWARD_SPIRAL)
        self.last_humanized = None

    def humanize(
        self,
        lyrics: str,
        intensity: float = None,
        emotion_weight: float = 0.5,
        emotion_curve_position: int = 0,
        profile: HumanProfileType = None
    ) -> str:
        """
        人类化歌词（人格驱动版）

        Args:
            lyrics: 原始歌词
            intensity: 噪声强度（覆盖默认值）
            emotion_weight: 情绪权重 0.0-1.0，高情绪会触发更多噪声
            emotion_curve_position: 在情绪曲线中的位置 0-3（0=开头，3=高潮）
            profile: 人格类型（覆盖默认人格）

        Returns:
            人类化后的歌词
        """
        intensity = intensity or self.intensity
        if intensity <= 0:
            return lyrics

        # 使用指定人格或默认人格
        active_profile = profile or self.profile
        if isinstance(profile, HumanProfileType):
            active_profile = HumanProfileLibrary.get_profile(profile)

        # v8.1: 计算 Profile Strength
        # 人格强度 = intensity × emotion_weight
        # 情绪低时人格不明显，情绪高时人格爆发
        profile_strength = intensity * emotion_weight

        lines = lyrics.split("\n")

        # v9.1: 创建语篇上下文（整个段落共享状态）
        discourse_ctx = self.RewriteContext(
            profile=active_profile,
            profile_strength=profile_strength,
            total_lines=len(lines)
        )

        humanized_lines = []

        for i, line in enumerate(lines):
            # 跳过空行
            if not line.strip():
                humanized_lines.append(line)
                continue

            # ✅ Hook保护：跳过Hook行（包含Hook标记的行）
            if HOOK_PREFIX in line or "!" in line or "【Hook】" in line:
                humanized_lines.append(line)
                continue

            # 跳过结构性标记行
            if line.strip().startswith("【"):
                humanized_lines.append(line)
                continue

            # 计算该行的"情绪压力"
            line_emotion_weight = self._calculate_emotion_weight(
                emotion_weight, emotion_curve_position, i, len(lines)
            )

            # ✅ v9.1 语义驱动 Rewrite（context 驱动，替代 v9.0 的纯参数）
            line = self.rewrite_line(
                line, line_emotion_weight, active_profile, profile_strength,
                context=discourse_ctx
            )

            humanized_lines.append(line)

        # ✅ Echo增强（使用人格的echo_keywords）
        humanized_lines = self._apply_echo_enhancement(
            humanized_lines, profile_strength, emotion_weight, active_profile
        )

        result = "\n".join(humanized_lines)
        self.last_humanized = result
        return result

    def _calculate_emotion_weight(
        self,
        base_emotion: float,
        curve_position: int,
        line_index: int,
        total_lines: int
    ) -> float:
        """
        计算单行的情绪权重

        情绪在高潮位置（副歌）最强，在开头和结尾最弱
        """
        # 位置系数：副歌位置（中间）情绪最强
        position_ratio = line_index / max(total_lines, 1)

        # 情绪曲线：中间高，两头低（类正态分布）
        if position_ratio < 0.2:
            position_factor = 0.5  # 开头弱
        elif position_ratio > 0.8:
            position_factor = 0.6  # 结尾稍弱
        else:
            position_factor = 1.0 + (position_ratio - 0.5) * 0.5  # 中间强

        return min(1.0, base_emotion * position_factor)

    def _apply_profile_driven_noise(
        self,
        line: str,
        intensity: float,
        emotion_weight: float,
        profile: HumanProfile,
        prefix_used: bool = False
    ) -> tuple:
        """
        人格驱动的噪声应用 v8.1

        根据人格配置控制不同噪声类型的权重
        v8.1: 使用 profile_strength（intensity × emotion_weight）
        v8.2: 返回 (line, used_prefix) tuple，消除弱检测

        人格影响：
        - tsundere: correction权重高（自打脸）
        - suppressed: fragmentation权重高（短句断行）
        - downward: repetition权重高（重复强化）
        """
        import random

        # 情绪低时只加轻微语气
        if emotion_weight < 0.3:
            if random.random() < intensity * profile.hesitation * 0.3:
                return self._add_profile_filler(line, profile, used_prefix=prefix_used)
            return line, prefix_used

        # 情绪中等：应用人格特征
        if emotion_weight < 0.6:
            # hesitation（只有没用过prefix时才用）
            if not prefix_used and random.random() < intensity * profile.hesitation * 0.4:
                line, used = self._add_profile_filler(line, profile, used_prefix=False)
                prefix_used = prefix_used or used
            # fragmentation
            if random.random() < intensity * profile.fragmentation * 0.3:
                line = self._add_profile_break(line, profile)
            return line, prefix_used

        # 情绪高：应用所有噪声
        # fragmentation（断句）- suppressed型最强
        if random.random() < intensity * profile.fragmentation * 0.6:
            line = self._add_profile_break(line, profile)

        # correction（自我纠正）- tsundere型最强
        if random.random() < intensity * profile.correction * 0.5:
            line = self._add_profile_correction(line, profile)

        # repetition（轻微重复）- downward型最强
        if random.random() < intensity * profile.repetition * 0.5:
            line = self._add_profile_suffix(line, profile)

        # hesitation（语气词）- 所有类型都适用
        if random.random() < intensity * profile.hesitation * 0.4:
            line, used = self._add_profile_filler(line, profile)
            prefix_used = prefix_used or used

        return line, prefix_used

    def _add_profile_filler(self, line: str, profile: HumanProfile, used_prefix: bool = False) -> tuple:
        """
        根据人格添加语气词

        Returns:
            (new_line, used_prefix): 返回新行和是否使用了prefix
        """
        import random
        clean = line.strip()
        if len(clean) < 4:
            return line, False

        # v8.1: 只有没用过prefix时才用前缀模式
        # 且概率降低（0.3而非0.4）
        if profile.prefix_patterns and not used_prefix and random.random() < 0.3:
            prefix = random.choice(profile.prefix_patterns)
            if clean.startswith(("不", "没", "别", "我", "你", "他")):
                return f"{prefix}，{clean}", True
            return f"{prefix}，{clean}", True

        # 标准语气词（轻微停顿）
        fillers = ["……", "嗯", "就", "其实"]
        filler = random.choice(fillers)

        if clean.endswith(("，", "。")):
            return clean[:-1] + f"{filler}，", False
        elif len(clean) > 5 and random.random() < 0.2:
            return clean + f"，{filler}", False
        return clean, False

    def _add_profile_break(self, line: str, profile: HumanProfile) -> str:
        """根据人格添加断句"""
        import random
        clean = line.strip()

        # 句尾变省略号
        if clean.endswith("，"):
            return clean[:-1] + "……"
        elif clean.endswith("。"):
            return clean[:-1] + "……"

        # 句中断句（保留前半）
        if "，" in clean:
            parts = clean.split("，")
            if len(parts) >= 2:
                keep = random.randint(1, min(2, len(parts)))
                return "，".join(parts[:keep]) + "……"

        return line

    def _add_profile_correction(self, line: str, profile: HumanProfile) -> str:
        """根据人格添加自我纠正"""
        import random
        clean = line.strip()

        # 检查是否已有纠正模式
        for before, after in self.SELF_CORRECTION_PATTERNS:
            if before in clean:
                return clean

        # 使用人格的后缀模式
        if profile.suffix_patterns and random.random() < 0.5:
            suffix = random.choice(profile.suffix_patterns)
            if not clean.endswith("……"):
                return clean + suffix

        # 句首加"不是""其实"等
        if profile.correction > 0.5 and len(clean) > 3:
            prefixes = ["其实", "不是", "不过"]
            prefix = random.choice(prefixes)
            return f"{prefix}……{clean}"

        return line

    def _add_profile_suffix(self, line: str, profile: HumanProfile) -> str:
        """根据人格添加句尾变体（重复强化）"""
        import random
        clean = line.strip()

        if len(clean) < 4 or clean.endswith("……"):
            return line

        # 从句尾提取关键词并强化
        for keyword in profile.echo_keywords:
            if keyword in clean:
                # 在关键词后加强调
                idx = clean.rfind(keyword)
                if idx > 0:
                    suffix = random.choice(["啊", "吧", "呢", "……"])
                    return clean[:idx+len(keyword)] + suffix

        return line

    def _add_subtle_filler(self, line: str) -> str:
        """添加轻微语气词（不破坏句子完整性）"""
        import random
        clean = line.strip()
        if len(clean) < 4:
            return line

        filler = random.choice(["其实", "就", "嗯", "……"])

        # 句尾加轻微停顿
        if clean.endswith(("，", "。")):
            return clean[:-1] + f"{filler}，"
        elif random.random() < 0.3:
            return clean + f"，{filler}"

        return line

    def _add_tight_filler(self, line: str) -> str:
        """添加紧凑语气词（句中，不破坏结构）"""
        import random
        clean = line.strip()

        if "，" not in clean:
            return line

        filler = random.choice(["其实", "就是", "好像"])
        parts = clean.split("，")

        # 在后半句加
        if len(parts) >= 2:
            mid = len(parts) // 2 + 1
            parts[mid] = f"{filler}，{parts[mid]}"
            return "，".join(parts)

        return line

    def _add_subtle_break(self, line: str) -> str:
        """轻微断句（不加太多东西）"""
        import random
        clean = line.strip()

        # 句中逗号变省略号（轻微犹豫）
        if "，" in clean and random.random() < 0.3:
            parts = clean.split("，")
            if len(parts) >= 2:
                # 只在最长的停顿后断
                break_idx = len(parts) // 2
                parts[break_idx] = parts[break_idx] + "……"
                return "，".join(parts[:break_idx + 1])

        return line

    def _add_structural_break(self, line: str) -> str:
        """结构断句（情绪高时：说不下去）"""
        import random
        clean = line.strip()

        # 句尾变省略号
        if clean.endswith("，"):
            return clean[:-1] + "……"
        elif clean.endswith("。"):
            return clean[:-1] + "……"

        # 句中制造断裂（半句）
        if "，" in clean:
            parts = clean.split("，")
            if len(parts) >= 2:
                # 只留前半句 + 省略号
                keep = random.randint(1, min(2, len(parts)))
                return "，".join(parts[:keep]) + "……"

        return line

    def _add_self_correction(self, line: str) -> str:
        """自我纠正（推翻刚说的话）"""
        import random
        clean = line.strip()

        corrections = [
            ("不是", "是"),
            ("以为", "其实"),
            ("应该", "但又"),
            ("想", "但又"),
            ("早该", "可惜"),
        ]

        for before, after in corrections:
            if before in clean:
                return clean  # 已经处理过

        # 在句首加"自我否定前缀"
        prefixes = [
            "其实",
            "但",
            "不过",
            "……其实",
            "好吧",
        ]

        if random.random() < 0.4:
            prefix = random.choice(prefixes)
            if clean.startswith(("不", "没", "别")):
                return f"不是……{clean}"
            return f"{prefix}，{clean}"

        # 在句尾加"轻微收回"
        suffixes = [
            "吧",
            "啊……算了",
            "……也没什么",
            "……好吧",
        ]

        if random.random() < 0.3 and len(clean) > 5:
            suffix = random.choice(suffixes)
            if not clean.endswith("……"):
                return clean + suffix

        return line

    # ==================== v9.0 语义驱动 Rewrite ====================

    # 自我矛盾模板库（情绪峰值触发）
    CONTRADICTION_TEMPLATES = [
        "我以为我已经{state}了……但没有",
        "我说不在意，其实{truth}",
        "不是因为{reason}，只是{truth}",
        "我早就{state}了——至少我以为",
    ]

    # 说不清楚模板（人类错误感）
    VAGUE_TEMPLATES = [
        "我也不知道为什么，就是觉得",
        "好像有点不对",
        "说不上来",
        "就是突然觉得……好像不太对了",
    ]

    # ==================== v9.1 Discourse State ====================

    class RewriteContext:
        """
        v9.1 语篇状态：追踪全局一致性

        解决的问题：
        - 每行独立 rewrite → 全局叙事一致性
        - 情绪随机 → 情绪轨迹连续性
        - 自我否定随机触发 → 有节制的叙事节奏
        """

        def __init__(
            self,
            profile: HumanProfile,
            profile_strength: float,
            total_lines: int = 1
        ):
            self.profile = profile
            self.profile_strength = profile_strength
            self.total_lines = total_lines

            # 情绪轨迹
            self.emotion_trace: List[float] = []

            # 已使用的句尾关键词（用于避免重复）
            self.used_keywords: List[str] = []

            # 预算系统（核心升级）
            # 不是"情绪高就触发"，而是"有预算才触发"
            self.contradiction_budget: float = 1.0   # 自我否定预算
            self.asymmetry_budget: float = 1.0        # 不对称预算
            self.repetition_budget: float = 1.0       # 重复卡顿预算

            # 上一次的 rewrite 结果（用于 discourse 引用）
            self.last_line: str = ""
            self.last_result: str = ""

            # 段落内的矛盾使用次数（人类写作不会每句都自打脸）
            self.contradiction_used: int = 0
            self.max_contradictions_per_section: int = 2

        def consume_contradiction(self) -> bool:
            """尝试消耗矛盾预算"""
            if self.contradiction_budget > 0.3 and self.contradiction_used < self.max_contradictions_per_section:
                self.contradiction_budget -= 0.4
                self.contradiction_used += 1
                return True
            return False

        def consume_asymmetry(self) -> bool:
            """尝试消耗不对称预算"""
            if self.asymmetry_budget > 0.3:
                self.asymmetry_budget -= 0.3
                return True
            return False

        def consume_repetition(self) -> bool:
            """尝试消耗重复预算"""
            if self.repetition_budget > 0.2:
                self.repetition_budget -= 0.2
                return True
            return False

        def record_keyword(self, keyword: str):
            """记录已使用的关键词，避免重复"""
            if keyword not in self.used_keywords:
                self.used_keywords.append(keyword)

        def update_emotion(self, emotion_weight: float):
            """更新情绪轨迹"""
            self.emotion_trace.append(emotion_weight)

        def get_trajectory_slope(self) -> float:
            """获取情绪轨迹斜率（上升/下降/平稳）"""
            if len(self.emotion_trace) < 2:
                return 0.0
            recent = self.emotion_trace[-3:]
            if len(recent) < 2:
                return 0.0
            return recent[-1] - recent[0]

        def should_use_contradiction(self, emotion_weight: float) -> bool:
            """
            决定是否使用矛盾表达
            条件：情绪够高 + 有预算 + 还没用超
            """
            if not self.profile:
                return emotion_weight > 0.7

            base_prob = emotion_weight * self.profile.correction
            budget_factor = self.contradiction_budget
            usage_limit = self.contradiction_used < self.max_contradictions_per_section

            return base_prob * budget_factor > 0.3 and usage_limit

        def should_use_asymmetry(self, emotion_weight: float) -> bool:
            """决定是否使用不对称（情绪够高 + 有预算）"""
            if not self.profile:
                return emotion_weight > 0.5

            base_prob = emotion_weight * self.profile.fragmentation
            return base_prob * self.asymmetry_budget > 0.2

        def should_use_repetition(self, emotion_weight: float) -> bool:
            """
            决定是否使用轻微重复
            条件：情绪不低 + 犹豫人格 + 有预算 + 情绪轨迹平稳
            """
            if not self.profile:
                return emotion_weight > 0.4

            # 情绪轨迹下降时不鼓励重复（情绪上升时才卡顿）
            slope = self.get_trajectory_slope()
            if slope < -0.1:
                return False

            base_prob = emotion_weight * self.profile.hesitation * self.repetition_budget
            return base_prob > 0.15

    def rewrite_line(
        self,
        line: str,
        emotion_weight: float,
        profile: HumanProfile,
        profile_strength: float,
        context: 'RewriteContext' = None
    ) -> str:
        """
        v9.0 语义驱动的人类化Rewrite管线

        顺序很重要：
        1. 语义停顿（情绪转折 / 未说完 / 自我修正）
        2. 自我否定（峰值 + 语义触发）
        3. 不对称（打断对称结构）
        4. 轻微卡顿（情绪犹豫时）

        每个步骤都有语义条件，概率只做兜底
        """
        import random

        # v9.1: 如果没有 context，创建一个宽松的默认 context
        if context is None:
            ctx = self.RewriteContext(profile, profile_strength)
        else:
            ctx = context

        # 1. 语义停顿（规则优先，与 context 无关）
        line = self._apply_semantic_pause(line, profile)

        # 2. 自我否定（v9.1: 预算驱动，而非情绪阈值）
        # 不再是 if emotion_weight > 0.6，而是 ctx.should_use_contradiction()
        line = self._apply_contradiction_v9(line, ctx)

        # 3. 不对称句式（v9.1: 预算驱动）
        if ctx.should_use_asymmetry(emotion_weight):
            line = self._apply_asymmetry_v9(line, ctx)

        # 4. 轻微卡顿（v9.1: 情绪轨迹斜率）
        if ctx.should_use_repetition(emotion_weight):
            line = self._apply_imperfect_repetition_v9(line, ctx)

        # 5. 兜底：概率驱动的人格噪声（原有逻辑）
        if random.random() < profile_strength * 0.3:
            line = self._apply_probability_filler(line, profile)

        # 更新 context 状态
        ctx.update_emotion(emotion_weight)
        ctx.last_line = line

        return line

    def _apply_semantic_pause(self, line: str, profile: HumanProfile) -> str:
        """
        语义停顿：只在情绪转折处停顿，不随机乱插

        触发位置：
        1. 情绪转折前（但/可是/只是/其实）
        2. 句子未说完（想/要/该）
        3. 自我修正（不是/应该说）
        """
        import random
        clean = line.strip()
        if len(clean) < 4:
            return line

        # 已经在句尾有省略号的跳过
        if clean.endswith("……"):
            return line

        # 情绪转折前 → 停顿
        turn_words = ["但", "可是", "只是", "其实", "不过"]
        for word in turn_words:
            if word in clean:
                idx = clean.find(word)
                if idx > 2:  # 不是在开头
                    before = clean[:idx]
                    after = clean[idx:]
                    if len(before) > 2 and len(after) > 1:
                        # 只在转折词前加省略号，不破坏转折词本身
                        if random.random() < 0.6:
                            return f"{before}……{after}"
                    break

        # 句子未说完（以"想""要""该"开头或附近）
        unfinished_patterns = ["我想", "我要", "我该", "我应该", "其实我想"]
        for pattern in unfinished_patterns:
            if clean.startswith(pattern) and len(clean) > 6:
                # 句中某个位置截断 + 省略号
                if random.random() < 0.5:
                    mid = len(clean) // 2
                    return clean[:mid] + "……"
                return clean + "……"
                break

        # 自我修正（句中有"不是"但没有"……"）
        if "不是" in clean and "……" not in clean and random.random() < 0.4:
            idx = clean.find("不是")
            if idx >= 0:
                return clean[:idx] + "不是……" + clean[idx+2:]

        return line

    def _apply_contradiction(self, line: str, emotion_weight: float, profile: HumanProfile) -> str:
        """
        自我否定：情绪峰值(>0.6) + 语义触发词 → 使用矛盾模板

        核心：不是随机，是"情绪到位了才有"
        """
        import random
        clean = line.strip()
        if len(clean) < 4:
            return line

        # 已经处理过的跳过
        if "……但没有" in clean or "——至少我以为" in clean or "其实" in clean[:4]:
            return line

        # 语义触发词
        trigger_words = ["以为", "放下", "忘记", "不在意", "算了", "该忘"]
        triggered = any(w in clean for w in trigger_words)

        if not triggered:
            return line

        # 概率：emotion_weight越高越容易触发
        prob = emotion_weight * profile.correction
        if random.random() > prob:
            return line

        # 提取 state 或 truth
        for keyword in trigger_words:
            if keyword in clean:
                idx = clean.find(keyword)
                state = clean[idx:idx+3] if idx + 3 <= len(clean) else clean[idx:]
                templates = [
                    f"我以为我已经{state}了……但没有",
                    f"我说不在意，其实{state}",
                ]
                chosen = random.choice(templates)
                # 替换占位符
                if "{state}" in chosen:
                    chosen = chosen.replace("{state}", state.rstrip("了"))
                return chosen
                break

        return line

    def _apply_asymmetry(self, line: str, profile: HumanProfile) -> str:
        """
        不对称句式：打破AI的工整对仗感

        AI 容易写成：
        你走了，我哭了
        你不在，我难过了

        人类写法：
        你走了
        我后来才开始哭
        或者：
        你走了，我哭了
        只是后来才意识到
        """
        import random
        clean = line.strip()
        if len(clean) < 8:
            return line

        # 检测对称结构："你...，我..."
        对称模式 = ["你", "我"]
        逗号_count = clean.count("，")

        if 逗号_count >= 1 and random.random() < profile.fragmentation * 0.4:
            parts = clean.split("，")
            if len(parts) >= 2:
                first = parts[0].strip()
                second = "，".join(parts[1:]).strip()

                # 如果前后都是"你/我"开头，打破它
                if (first.startswith("你") or first.startswith("我")) and \
                   (second.startswith("你") or second.startswith("我")):
                    # 方案：前半保留，后半加"延迟句"
                    延迟词 = ["只是", "后来才", "过了很久才", "其实"]
                    if random.random() < 0.5:
                        delay = random.choice(延迟词)
                        return f"{first}，{delay}{second[1:]}"

                    # 方案：直接断句，让信息延迟
                    if len(first) > 2 and len(second) > 2:
                        return f"{first}\n{second}"

        # 检测平行结构（"了...了..."）
        if "了" in clean and "，" in clean and random.random() < 0.3:
            parts = clean.split("，")
            if len(parts) >= 2:
                # 找"了"的位置，让第二句信息更模糊
                if "了" in parts[0] and len(parts) > 1:
                    parts[1] = parts[1].replace("了", "……")
                    return "，".join(parts)

        return line

    def _apply_imperfect_repetition(self, line: str, profile: HumanProfile) -> str:
        """
        轻微重复（卡顿感）：不是复读，而是"卡住"

        我想说的是
        想说的不是
        这样

        或者：
        你问我还在不在
        我说在
        其实……
        """
        import random
        clean = line.strip()
        if len(clean) < 6:
            return line

        # 已经处理过的跳过
        重复词 = ["想说", "要说", "想问", "想说"]
        if any(w in clean for w in 重复词):
            for word in 重复词:
                if word in clean:
                    idx = clean.find(word)
                    if idx >= 0:
                        before = clean[:idx]
                        rest = clean[idx:]
                        # 只重复前两个字
                        partial = rest[:min(3, len(rest))]
                        templates = [
                            f"{before}{partial}，{rest}",
                            f"{before}{partial}……{rest}",
                        ]
                        if random.random() < profile.repetition * 0.5:
                            return random.choice(templates)
                    break

        # 句尾关键词重复（卡住感）
        for kw in profile.echo_keywords:
            if kw in clean and len(clean) > 5:
                idx = clean.rfind(kw)
                if idx > 2 and random.random() < profile.repetition * 0.3:
                    before = clean[:idx]
                    after = clean[idx:]
                    return f"{before}……{after}"
                    break

        return line

    # ==================== v9.1 Budget-driven rewrite methods ====================

    def _apply_contradiction_v9(self, line: str, ctx: 'RewriteContext') -> str:
        """
        v9.1 自我否定（预算驱动版）

        替代原来的 emotion_weight > 0.6 硬判断
        现在使用 ctx.should_use_contradiction() 做软判断
        """
        import random
        clean = line.strip()
        if len(clean) < 4:
            return line

        # 已经处理过的跳过
        if "……但没有" in clean or "——至少我以为" in clean or "其实" in clean[:4]:
            return line

        # 语义触发词
        trigger_words = ["以为", "放下", "忘记", "不在意", "算了", "该忘"]
        triggered = any(w in clean for w in trigger_words)

        if not triggered:
            return line

        # v9.1: 预算检查
        if not ctx.should_use_contradiction(ctx.emotion_trace[-1] if ctx.emotion_trace else 0.5):
            return line

        if not ctx.consume_contradiction():
            return line

        # 提取并生成矛盾模板
        for keyword in trigger_words:
            if keyword in clean:
                idx = clean.find(keyword)
                state = clean[idx:idx+3] if idx + 3 <= len(clean) else clean[idx:]
                templates = [
                    f"我以为我已经{state}了……但没有",
                    f"我说不在意，其实{state}",
                    f"不是因为工作忙，只是{state}",
                ]
                chosen = random.choice(templates)
                if "{state}" in chosen:
                    chosen = chosen.replace("{state}", state.rstrip("了"))
                return chosen
                break

        return line

    def _apply_asymmetry_v9(self, line: str, ctx: 'RewriteContext') -> str:
        """
        v9.1 不对称句式（预算驱动版）
        """
        import random
        clean = line.strip()
        if len(clean) < 8:
            return line

        if not ctx.consume_asymmetry():
            return line

        # 检测对称结构
        comma_count = clean.count("，")

        if comma_count >= 1:
            parts = clean.split("，")
            if len(parts) >= 2:
                first = parts[0].strip()
                second = "，".join(parts[1:]).strip()

                # 如果前后都是"你/我"开头，打破它
                if (first.startswith("你") or first.startswith("我")) and \
                   (second.startswith("你") or second.startswith("我")):
                    # 用情绪轨迹斜率决定延迟方式
                    slope = ctx.get_trajectory_slope()
                    if slope > 0.1:
                        # 情绪上升：加"后来才"
                        delay_words = ["只是", "后来才", "过了很久才"]
                        delay = random.choice(delay_words)
                        return f"{first}，{delay}{second[1:]}"
                    else:
                        # 情绪平稳/下降：直接断句
                        if len(first) > 2 and len(second) > 2:
                            return f"{first}\n{second}"

        # 平行结构破坏
        if "了" in clean and comma_count >= 1:
            parts = clean.split("，")
            if len(parts) >= 2 and "了" in parts[0]:
                parts[1] = parts[1].replace("了", "……")
                return "，".join(parts)

        return line

    def _apply_imperfect_repetition_v9(self, line: str, ctx: 'RewriteContext') -> str:
        """
        v9.1 轻微重复（预算+轨迹驱动版）
        """
        import random
        clean = line.strip()
        if len(clean) < 6:
            return line

        if not ctx.consume_repetition():
            return line

        # 记录使用的关键词
        for kw in ctx.profile.echo_keywords:
            if kw in clean and len(clean) > 5:
                idx = clean.rfind(kw)
                if idx > 2:
                    before = clean[:idx]
                    after = clean[idx:]
                    ctx.record_keyword(kw)
                    return f"{before}……{after}"
                    break

        # discourse-level 引用：检查上一句是否有可引用的词
        if ctx.last_result:
            for kw in ctx.profile.echo_keywords:
                if kw in ctx.last_result and kw not in ctx.used_keywords:
                    if kw in clean:
                        idx = clean.rfind(kw)
                        before = clean[:idx]
                        after = clean[idx:]
                        ctx.record_keyword(kw)
                        # 在引用点制造"卡住"
                        templates = [
                            f"{before}……{after}",
                            f"{before}，{after}",
                        ]
                        return random.choice(templates)
                    break

        return line

    def _apply_probability_filler(self, line: str, profile: HumanProfile) -> str:
        """
        兜底：概率驱动的人格语气词
        只有语义触发都没命中时才走这里
        """
        import random
        clean = line.strip()
        if len(clean) < 4:
            return line

        # 轻微语气词
        if random.random() < profile.hesitation * 0.4:
            filler = random.choice(["……", "嗯", "就", "其实"])
            if clean.endswith(("，", "。")):
                return clean[:-1] + f"{filler}，"
            elif len(clean) > 5:
                return clean + f"，{filler}"
        return line

    def _apply_echo_enhancement(
        self,
        lines: list,
        intensity: float,
        emotion_weight: float,
        profile: HumanProfile = None
    ) -> list:
        """
        半句回收增强（echo机制）v8.0

        原理：抽前半句 → 轻微改写 → 插入下一行

        v8.0升级：使用profile.echo_keywords过滤，只对特定关键词生效

        示例：
        原：风吹过来
        下一行：雨也落下来

        变：风吹过来
        吹着吹着
        雨就落下来了
        """
        import random

        if len(lines) < 3 or intensity < 0.2:
            return lines

        # 获取echo关键词（没有则用默认值）
        echo_keywords = profile.echo_keywords if profile else ["走", "等", "看", "想", "爱", "痛", "忘"]

        result = []
        skip_next = False

        for i, line in enumerate(lines):
            result.append(line)

            if skip_next:
                skip_next = False
                continue

            # 跳过空行、标记行、Hook行
            if not line.strip() or line.strip().startswith("【") or HOOK_PREFIX in line or "!" in line:
                continue

            # 检查是否包含echo关键词（语义弱控制）
            has_echo_keyword = any(kw in line for kw in echo_keywords)

            # 情绪高 + 有关键词 + 随机 → 触发echo
            if emotion_weight > 0.4 and has_echo_keyword and random.random() < intensity * 0.35:
                if i + 1 < len(lines):
                    # 抽取前半句
                    words = line.strip().split("，")
                    if len(words) >= 1 and len(words[0]) >= 2:
                        echo_phrase = words[0]

                        # 轻微变化
                        if echo_phrase.startswith("我"):
                            echo_phrase = "走着走着" if random.random() < 0.5 else "过着过着"
                        elif echo_phrase.startswith("你"):
                            echo_phrase = "你" + echo_phrase[1:]
                        elif len(echo_phrase) > 3:
                            # 截取前半
                            echo_phrase = echo_phrase[:2] + random.choice(["着", "着", "的"])

                        # 插入下一行前
                        result.append(echo_phrase)
                        skip_next = True

        return result

    def humanize_aggressive(self, lyrics: str) -> str:
        """激进人类化（intensity=0.6）"""
        return self.humanize(lyrics, intensity=0.6)

    def humanize_mild(self, lyrics: str) -> str:
        """轻度人类化（intensity=0.2）"""
        return self.humanize(lyrics, intensity=0.2)


# ==================== Art Layer: Narrative Builder (v9.2) ====================

# v9.5 语义帧 schema 约束
VALID_CORES = frozenset([
    "silence", "distance", "doubt", "self_doubt",
    "pain", "resignation", "realization"
])
VALID_TENSIONS = frozenset([
    "expectation_fall", "contrast", "reversal", "stable", "rising", "release"
])
VALID_EMOTIONS = frozenset([
    "anxiety", "sadness", "hope", "relief", "anger",
    "nostalgia", "loneliness", "calm", "confusion", "resignation"
])


@dataclass
class SemanticFrame:
    """
    v9.5 语义帧：structured representation of an event

    不再是 (event_type, event_desc) 的二元组
    而是包含完整语义信息的结构：

    - core: 核心事件类型（silence/distance/doubt/self_doubt/pain/resignation/realization）
    - trigger: 聊天原句中的触发短语（"秒回变沉默"）
    - behavior: 叙事行为/心理动作（waiting_anxiously/retrospection/realization）
    - emotion: 情绪标签（anxiety/sadness/hope/relief）
    - tension: 张力类型（expectation_fall/contrast/reversal/stable）
    - direction: 情绪走向（rising/falling/stable）
    """
    core: str
    trigger: str
    behavior: str
    emotion: str
    tension: str
    direction: str = "stable"

    def validate(self) -> 'SemanticFrame':
        """v9.5: 确保 frame 字段合法，防止漂移"""
        if self.core not in VALID_CORES:
            self.core = "pain"  # fallback to neutral
        if not self.behavior:
            self.behavior = "unknown"
        if self.tension not in VALID_TENSIONS:
            self.tension = "stable"
        if self.emotion not in VALID_EMOTIONS:
            self.emotion = "sadness"
        if self.direction not in ("rising", "falling", "stable"):
            self.direction = "stable"
        return self

    def __str__(self):
        return f"SemanticFrame({self.core}|{self.behavior}|{self.tension})"


class NarrativeBuilder:
    """
    v9.2 Narrative Builder - 聊天 → 叙事骨架 → 歌词结构

    解决的核心问题：
    1. 微信是"碎片对话"，歌词需要"完整叙事弧"
    2. 微信是"你/我/他混着"，歌词需要"统一视角"
    3. 微信是"句子"，歌词需要"事件骨架"

    架构：
    WeChat Chat
        ↓
    Event Extraction（事件抽取）
        ↓
    Perspective Unification（视角统一）
        ↓
    Narrative Arc Builder（叙事弧构建）
        ↓
    Lyric-ready Event List
    """

    def __init__(self):
        self.last_narrative = None
        self._expansion_cache = set()  # v9.5: 防止同一行重复出现

    # 事件模板：从聊天行为映射到歌词事件
    EVENT_TEMPLATES = {
        "distance": [
            "{target}开始变得冷淡",
            "{target}不再像以前那样",
            "{target}的回复越来越慢",
        ],
        "doubt": [
            "{self}反复确认关系",
            "{self}开始患得患失",
            "{self}想问又不敢问",
        ],
        "silence": [
            "{target}突然不说话了",
            "{target}开始已读不回",
            "{target}不回消息的那天",
        ],
        "self_doubt": [
            "{self}开始怀疑自己",
            "{self}觉得是自己的问题",
            "{self}反复回想哪里做错了",
        ],
        "resignation": [
            "{self}不再追问了",
            "{self}假装什么都没发生",
            "{self}假装一切如常",
        ],
        "realization": [
            "{self}后来才明白",
            "原来不是{self}的问题",
            "{self}终于懂了",
        ],
        "pain": [
            "{self}那晚哭了很久",
            "{self}一个人想了很久",
            "那种痛说不出来",
        ],
    }

    # 叙事弧线结构
    NARRATIVE_ARCS = {
        "heartbreak": ["distance", "doubt", "silence", "self_doubt", "resignation", "realization"],
        "nostalgia": ["distance", "pain", "doubt", "realization"],
        "regret": ["self_doubt", "pain", "realization"],
        "longing": ["distance", "doubt", "pain"],
    }

    # v9.3: 转折句模板（在 verse2 前插入）
    TURNING_POINT_TEMPLATES = [
        "后来我才明白",
        "那一刻我才懂",
        "原来不是这样",
        "直到你走了我才",
    ]

    # v9.6: 意象词库 - 让歌词从"解释"变成"有画面"
    IMAGERY = {
        "silence": ["已读不回的对话框", "灰掉的头像", "凌晨三点的屏幕", "消息框空空的"],
        "distance": ["两条平行线", "越走越远的背影", "中间隔着的沉默", "再也够不到的距离"],
        "doubt": ["那句话的语气", "那天的表情", "反复回味的细节", "说不出口的疑问"],
        "self_doubt": ["那句话", "那天的语气", "自己的影子", "越来越小的自己"],
        "pain": ["喉咙里的哽咽", "眼眶里打转的泪", "深夜醒来的时刻", "抱紧自己的手臂"],
        "resignation": ["算了这两个字", "假装没发生过", "笑着说没事", "不再追问的沉默"],
        "realization": ["碎掉的东西", "回不去的那天", "醒过来的早晨", "空荡荡的房间"],
    }

    # v9.6: 画面句模板 - 替换原来的解释句
    VISUAL_TEMPLATES = {
        ("silence", "waiting_anxiously"): [
            "我把聊天框翻了一遍又一遍",
            "屏幕亮着 却等不到一个表情",
        ],
        ("silence", "refresh_repeatedly"): [
            "我一遍遍刷新 看你有没有上线",
            "每一条消息 都石沉大海",
        ],
        ("silence", "staring_screen"): [
            "我盯着那个对话框发了很久的呆",
            "输入法打了一半 又全部删掉",
        ],
        ("distance", "retrospection"): [
            "那些天的聊天记录 我翻到屏幕都发烫",
            "以为这样就能回到从前",
        ],
        ("distance", "realizing_change"): [
            "原来你早就不是我认识的那个人了",
            "只是我后知后觉",
        ],
        ("distance", "reaching_out"): [
            "我试着靠近 你却往后退了一步",
            "距离这种东西 我终于看清了",
        ],
        ("doubt", "retrospection"): [
            "我问了自己一百遍",
            "是不是我想太多了",
        ],
        ("doubt", "overthinking"): [
            "那些细节在脑子里翻来覆去",
            "想得越多 越没有答案",
        ],
        ("self_doubt", "self_blame"): [
            "我把那天的话翻了又翻",
            "还是找不到沉默的原因",
        ],
        ("self_doubt", "carrying_alone"): [
            "好像只有我一个人在乎这段关系",
            "撑得好累 但不敢放手",
        ],
        ("pain", "crying"): [
            "眼泪在眼眶里打转",
            "却不知道该怪谁",
        ],
        ("pain", "overthinking"): [
            "想到睡不着 想到天亮",
            "想到连做梦都在想",
        ],
        ("resignation", "giving_up"): [
            "我跟自己说算了",
            "想多了也只是为难自己",
        ],
        ("resignation", "pretending"): [
            "我假装什么都没发生",
            "假装一切如常",
        ],
        ("realization", "sudden_awakening"): [
            "原来从头到尾",
            "只是我一个人在撑",
        ],
        ("realization", "seeing_clearly"): [
            "我终于看清了",
            "只是看清了也回不去了",
        ],
    }

    # v9.6: turning punch lines（爆点句）
    TURNING_PUNCH_LINES = [
        "你不是没回 只是没想回我",
        "原来早就散了 只是我不愿承认",
        "不是距离远了 是心远了",
        "那句话之后 我们就没再说过话了",
        "不是你不回 是你早就不想回了",
    ]

    # v9.7: Hook模板 - 按core分组的爆款候选句
    HOOK_TEMPLATES = {
        "silence": [
            "你不是没回\n只是没想回我",
            "那条消息\n你看到了也没回",
            "我删了又打的那句话\n你永远都不会看见",
        ],
        "distance": [
            "我们不是吵散的\n是慢慢不说话了",
            "不是距离远了\n是心远了",
            "你一句“在忙”\n我等了一整晚",
        ],
        "self_doubt": [
            "我反复想的那句话\n其实根本不重要",
            "我以为是我不够好\n后来才知道不是",
            "我把错都给了自己\n却不知道问题不在我",
        ],
        "doubt": [
            "我问了自己一百遍\n是不是我想太多",
            "那些细节在脑子里\n翻来覆去睡不着",
        ],
        "pain": [
            "眼泪在眼眶里打转\n却不知道该怪谁",
            "想到天亮\n想到连梦都在想",
        ],
        "resignation": [
            "算了这两个字\n我说了无数次",
            "我假装没事\n假装一切如常",
        ],
        "realization": [
            "原来从头到尾\n只是我一个人在撑",
            "看清了也回不去\n回不去也只能认",
        ],
    }

    # v9.3: 事件扩展模板
    EVENT_EXPANSION_TEMPLATES = {
        "silence": [
            "我盯着屏幕等了很久",
            "消息框亮了又灭",
            "像你对我那点耐心",
        ],
        "distance": [
            "我以为一切都没变",
            "直到那天才发现",
        ],
        "doubt": [
            "我反复问自己",
            "是不是我想太多",
        ],
        "self_doubt": [
            "我开始怀疑自己",
            "是不是我真的不够好",
        ],
        "pain": [
            "那种感觉说不出来",
            "只有自己知道有多痛",
        ],
        "resignation": [
            "我告诉自己别想了",
            "算了，就这样吧",
        ],
        "realization": [
            "原来从头到尾",
            "只是我一个人在撑",
        ],
    }

    # ==================== v9.3 Event Rewrite ====================

    def _build_semantic_frame(self, event_type: str) -> 'SemanticFrame':
        """
        v9.5 核心升级：从聊天上下文构建语义帧

        不再返回字符串，而是返回完整的 SemanticFrame
        包含：trigger（事件短语）、behavior（心理动作）、emotion、tension、direction

        这使得 expand 时能基于"语义帧"而非"关键词匹配"
        """
        if not self._chat_context:
            return SemanticFrame(
                core=event_type,
                trigger=f"这{event_type}的情绪",
                behavior="unknown",
                emotion="sadness",
                tension="stable"
            )

        combined = " ".join(self._chat_context)

        # === 根据 event_type 和聊天内容构建语义帧 ===

        if event_type == "silence":
            if "秒回" in combined:
                return SemanticFrame(
                    core="silence",
                    trigger="你从秒回变成沉默",
                    behavior="waiting_anxiously",
                    emotion="anxiety",
                    tension="expectation_fall",
                    direction="rising"
                )
            elif "突然" in combined:
                return SemanticFrame(
                    core="silence",
                    trigger="你突然就不再说话",
                    behavior="refresh_repeatedly",
                    emotion="anxiety",
                    tension="contrast",
                    direction="rising"
                )
            elif "不回" in combined or "已读" in combined:
                return SemanticFrame(
                    core="silence",
                    trigger="你开始不回消息",
                    behavior="staring_screen",
                    emotion="sadness",
                    tension="stable",
                    direction="stable"
                )
            else:
                return SemanticFrame(
                    core="silence",
                    trigger="你不再像以前那样",
                    behavior="waiting_hopefully",
                    emotion="hope",
                    tension="expectation_fall",
                    direction="falling"
                )

        elif event_type == "distance":
            if "以前" in combined or "那时候" in combined:
                return SemanticFrame(
                    core="distance",
                    trigger="你以前不是这样的",
                    behavior="retrospection",
                    emotion="nostalgia",
                    tension="contrast",
                    direction="falling"
                )
            elif "变了" in combined:
                return SemanticFrame(
                    core="distance",
                    trigger="我们好像都变了",
                    behavior="realizing_change",
                    emotion="sadness",
                    tension="reversal",
                    direction="falling"
                )
            else:
                return SemanticFrame(
                    core="distance",
                    trigger="你离我越来越远",
                    behavior="reaching_out",
                    emotion="sadness",
                    tension="stable",
                    direction="falling"
                )

        elif event_type == "doubt":
            if "是不是" in combined or "确认" in combined:
                return SemanticFrame(
                    core="doubt",
                    trigger="是不是我哪里做错了",
                    behavior="retrospection",
                    emotion="anxiety",
                    tension="stable",
                    direction="rising"
                )
            elif "等" in combined or "期待" in combined:
                return SemanticFrame(
                    core="doubt",
                    trigger="我在等一个解释",
                    behavior="hoping",
                    emotion="hope",
                    tension="stable",
                    direction="stable"
                )
            else:
                return SemanticFrame(
                    core="doubt",
                    trigger="我开始怀疑这一切",
                    behavior="overthinking",
                    emotion="anxiety",
                    tension="rising",
                    direction="rising"
                )

        elif event_type == "self_doubt":
            if "我哪里" in combined or "是不是我" in combined:
                return SemanticFrame(
                    core="self_doubt",
                    trigger="是不是我哪里做错了",
                    behavior="self_blame",
                    emotion="sadness",
                    tension="stable",
                    direction="rising"
                )
            elif "凭什么" in combined:
                return SemanticFrame(
                    core="self_doubt",
                    trigger="我凭什么要受这些",
                    behavior="questioning_fairness",
                    emotion="anger",
                    tension="rising",
                    direction="rising"
                )
            else:
                return SemanticFrame(
                    core="self_doubt",
                    trigger="只有我一个人在撑着",
                    behavior="carrying_alone",
                    emotion="loneliness",
                    tension="stable",
                    direction="stable"
                )

        elif event_type == "pain":
            if "哭" in combined:
                return SemanticFrame(
                    core="pain",
                    trigger="那晚我哭到喘不上气",
                    behavior="crying",
                    emotion="sadness",
                    tension="release",
                    direction="rising"
                )
            elif "想" in combined or "想不通" in combined:
                return SemanticFrame(
                    core="pain",
                    trigger="想到天亮也没想通",
                    behavior="overthinking",
                    emotion="confusion",
                    tension="rising",
                    direction="stable"
                )
            else:
                return SemanticFrame(
                    core="pain",
                    trigger="那种感觉说不出来",
                    behavior="suppressing",
                    emotion="sadness",
                    tension="stable",
                    direction="stable"
                )

        elif event_type == "resignation":
            if "算了" in combined:
                return SemanticFrame(
                    core="resignation",
                    trigger="我告诉自己算了",
                    behavior="giving_up",
                    emotion="relief",
                    tension="release",
                    direction="falling"
                )
            elif "假装" in combined:
                return SemanticFrame(
                    core="resignation",
                    trigger="我假装什么都没发生",
                    behavior="pretending",
                    emotion="sadness",
                    tension="stable",
                    direction="stable"
                )
            else:
                return SemanticFrame(
                    core="resignation",
                    trigger="我不再问你了",
                    behavior="withdrawing",
                    emotion="resignation",
                    tension="falling",
                    direction="falling"
                )

        elif event_type == "realization":
            if "才明白" in combined or "才懂" in combined:
                return SemanticFrame(
                    core="realization",
                    trigger="后来我才明白",
                    behavior="sudden_awakening",
                    emotion="relief",
                    tension="reversal",
                    direction="falling"
                )
            elif "原来" in combined:
                return SemanticFrame(
                    core="realization",
                    trigger="原来不是我的问题",
                    behavior="understanding",
                    emotion="relief",
                    tension="release",
                    direction="falling"
                )
            else:
                return SemanticFrame(
                    core="realization",
                    trigger="我终于看清了",
                    behavior="seeing_clearly",
                    emotion="calm",
                    tension="stable",
                    direction="stable"
                )

        # fallback
        return SemanticFrame(
            core=event_type,
            trigger=f"这{event_type}的情绪",
            behavior="unknown",
            emotion="sadness",
            tension="stable"
        ).validate()

    def build_from_chat(
        self,
        chat_messages: list,
        emotion_vector: 'EmotionVector',
        profile: 'HumanProfile' = None
    ) -> dict:
        """
        从聊天构建叙事骨架（v9.5: 返回 List[SemanticFrame]）

        Returns:
            {
                "events": [SemanticFrame, ...],  # 歌词事件列表
                "speaker": "我",  # 叙事视角
                "target": "你",  # 叙述对象
                "arc": "heartbreak",  # 叙事弧线
                "perspective": "second_person",  # 第一/第二人称
            }
        """
        # v9.5: 每次构建清空 expansion 缓存
        self._expansion_cache.clear()

        # 1. v9.5: 语义帧抽取（视角已在 frame 内统一）
        frames = self._extract_events(chat_messages, emotion_vector)

        # 2. 选择叙事弧线
        arc_type = self._detect_arc_type(emotion_vector)

        # 3. 构建叙事骨架
        narrative = self._build_narrative_arc(frames, arc_type, profile)

        self.last_narrative = narrative
        return narrative

    def _extract_events(self, chat_messages: list, emotion_vector: 'EmotionVector') -> list:
        """
        从聊天抽取关键事件（v9.5: 返回 List[SemanticFrame]）

        输出格式：[SemanticFrame, ...]
        """
        frames = []

        # v9.3: 保留原始聊天上下文
        message_texts = []
        for msg in chat_messages:
            if isinstance(msg, dict):
                message_texts.append(msg.get('content', ''))
            else:
                message_texts.append(str(msg))
        self._chat_context = message_texts

        combined = " ".join(message_texts)

        # v9.5: 情绪信号 → 语义帧映射
        primary, intensity = emotion_vector.get_primary()

        # sadness / regret → 分离/失落事件
        if emotion_vector.sadness > 0.4 or emotion_vector.regret > 0.4:
            if any(w in combined for w in ['分手', '分开', '离开']):
                frames.append(self._build_semantic_frame('distance'))
            if any(w in combined for w in ['不回复', '不回', '已读', '秒回']):
                frames.append(self._build_semantic_frame('silence'))
            if any(w in combined for w in ['哭', '难过', '难受']):
                frames.append(self._build_semantic_frame('pain'))

        # nostalgia → 回忆事件
        if emotion_vector.nostalgia > 0.4:
            if any(w in combined for w in ['以前', '以前会', '那时候']):
                frames.append(self._build_semantic_frame('distance'))
            frames.append(self._build_semantic_frame('pain'))

        # anger → 积累/爆发事件
        if emotion_vector.anger > 0.3:
            if any(w in combined for w in ['凭什么', '为什么', '不公平']):
                frames.append(self._build_semantic_frame('self_doubt'))

        # loneliness → 孤立事件
        if emotion_vector.loneliness > 0.4:
            frames.append(self._build_semantic_frame('self_doubt'))

        # hope → 期待/失望事件
        if emotion_vector.hope > 0.3:
            if any(w in combined for w in ['等', '期待', '希望']):
                frames.append(self._build_semantic_frame('doubt'))

        # 如果没有提取到，用情绪本身作为事件
        if not frames:
            frames.append(self._build_semantic_frame(primary))

        # 去重但保留顺序（按 trigger 去重）
        seen = set()
        deduped = []
        for f in frames:
            if f.trigger not in seen:
                seen.add(f.trigger)
                deduped.append(f)

        return deduped

    def _expand_from_frame(self, frame: 'SemanticFrame') -> list:
        """
        v9.6 画面化升级：根据语义帧展开为"有画面的歌词句"

        关键升级：
        - 使用 VISUAL_TEMPLATES 替代解释句
        - 注入 IMAGERY 意象词增加"身临其境"感
        - 保证每行都是"让人看到画面"而非"在解释"

        Returns:
            [line1, line2] 展开行列表
        """
        lines = []
        core = frame.core
        behavior = frame.behavior
        tension = frame.tension
        emotion = frame.emotion

        # v9.6: 优先用画面句模板
        key = (core, behavior)
        if key in self.VISUAL_TEMPLATES:
            lines.extend(self.VISUAL_TEMPLATES[key])
        else:
            # fallback 到原有逻辑（仍然画面化）
            # silence 事件族
            if core == "silence":
                if behavior == "waiting_anxiously":
                    lines.append("消息发出去 期待着回复")
                    lines.append("等到的只是已读")
                elif behavior == "refresh_repeatedly":
                    lines.append("我一遍遍刷新聊天框")
                    lines.append("以为下一秒你就会回来")
                elif behavior == "staring_screen":
                    lines.append("我盯着那个对话框发呆")
                    lines.append("输入法打了又删 删了又打")
                elif behavior == "waiting_hopefully":
                    lines.append("消息框空了很久")
                    lines.append("我不敢再发第二条")
                else:
                    lines.append("消息框一直空着")
                    lines.append("我假装没在等")

            # distance 事件族
            elif core == "distance":
                if behavior == "retrospection":
                    lines.append("我把聊天记录翻了一遍又一遍")
                    lines.append("屏幕都发烫了")
                elif behavior == "realizing_change":
                    lines.append("只是我后知后觉")
                    lines.append("你早就不是原来的你了")
                elif behavior == "reaching_out":
                    lines.append("我试着去靠近你")
                    lines.append("却发现距离越来越远")
                else:
                    lines.append("我们之间好像隔了什么")
                    lines.append("说不上来")

            # doubt 事件族
            elif core == "doubt":
                if behavior == "retrospection":
                    lines.append("我问了自己一百遍")
                    lines.append("到底是我想太多了吗")
                elif behavior == "hoping":
                    lines.append("我在等一个解释")
                    lines.append("等到连自己都不信了")
                elif behavior == "overthinking":
                    lines.append("那些细节在脑子里翻来覆去")
                    lines.append("想得越多 越没有答案")
                else:
                    lines.append("我想抓住每个细节")
                    lines.append("却只抓到自己的不安")

            # self_doubt 事件族
            elif core == "self_doubt":
                if behavior == "self_blame":
                    lines.append("我把那天的话翻了又翻")
                    lines.append("还是找不到沉默的原因")
                elif behavior == "questioning_fairness":
                    lines.append("我凭什么要受这些")
                    lines.append("但我还是选择了忍")
                elif behavior == "carrying_alone":
                    lines.append("好像只有我一个人在撑")
                    lines.append("撑得好累 但不敢说")
                else:
                    lines.append("我开始怀疑自己")
                    lines.append("是不是我真的不够好")

            # pain 事件族
            elif core == "pain":
                if behavior == "crying":
                    lines.append("眼泪在眼眶里打转")
                    lines.append("却不知道该怪谁")
                elif behavior == "overthinking":
                    lines.append("想到睡不着 想到天亮")
                    lines.append("想到连做梦都在想")
                elif behavior == "suppressing":
                    lines.append("那种痛说不出来")
                    lines.append("只有自己知道有多痛")
                else:
                    lines.append("好多话想说")
                    lines.append("却一句都说不出口")

            # resignation 事件族
            elif core == "resignation":
                if behavior == "giving_up":
                    lines.append("我跟自己说算了")
                    lines.append("想多了也只是为难自己")
                elif behavior == "pretending":
                    lines.append("我假装什么都没发生")
                    lines.append("假装一切如常")
                elif behavior == "withdrawing":
                    lines.append("我不再问你了")
                    lines.append("问了也不会有答案")
                else:
                    lines.append("算了 就这样吧")
                    lines.append("想多了也没用")

            # realization 事件族
            elif core == "realization":
                if behavior == "sudden_awakening":
                    lines.append("原来从头到尾")
                    lines.append("只是我一个人在撑")
                elif behavior == "understanding":
                    lines.append("原来不是我不够好")
                    lines.append("只是你不想继续了")
                elif behavior == "seeing_clearly":
                    lines.append("我终于看清了")
                    lines.append("只是看清了也回不去了")
                else:
                    lines.append("我以为我懂了")
                    lines.append("其实还是没有")

        # v9.6: 注入意象词 - 随机替换一句加入 imagery
        imagery_list = self.IMAGERY.get(core, [])
        if imagery_list and lines:
            import random
            img = random.choice(imagery_list)
            # 随机替换一行或在某行后追加
            if len(lines) >= 2 and random.random() > 0.5:
                # 替换第二行（保留第一行作为钩子）
                lines[1] = f"看着{img} 我发了很久的呆"
            else:
                # 在最后追加一行 imagery
                lines.append(f"我盯着{img} 不知道说什么")

        # v9.5: 去重 - 防止同一行在多事件展开时重复
        deduped = []
        for line in lines:
            if line not in self._expansion_cache:
                self._expansion_cache.add(line)
                deduped.append(line)

        # v9.7: 去除句内相似感（，相邻行前6字相同则去重）
        filtered = []
        for line in deduped:
            if not filtered or line[:6] != filtered[-1][:6]:
                filtered.append(line)
        return filtered

    def _detect_arc_type(self, emotion_vector: 'EmotionVector') -> str:
        """根据情绪向量选择叙事弧线"""
        if emotion_vector.sadness > 0.5 and emotion_vector.regret > 0.4:
            return "heartbreak"
        elif emotion_vector.nostalgia > 0.5:
            return "nostalgia"
        elif emotion_vector.regret > 0.5:
            return "regret"
        elif emotion_vector.hope > 0.3 and emotion_vector.loneliness > 0.3:
            return "longing"
        return "heartbreak"

    def _build_narrative_arc(
        self,
        frames: list,
        arc_type: str,
        profile: 'HumanProfile' = None
    ) -> dict:
        """
        v9.5 构建叙事弧：基于语义帧展开，加转折句

        歌词结构：
        [开场] - 场景设定
        [主歌1] - 事件展开（每个事件扩2-3行）
        [转折句] - 情绪转折点
        [主歌2] - 情绪升级 + 矛盾爆发
        [结尾] - 情绪收束
        """
        import random
        arc_sequence = self.NARRATIVE_ARCS.get(arc_type, self.NARRATIVE_ARCS["heartbreak"])

        lyric_lines = []

        # v9.5: 每个 frame 展开
        for i, frame in enumerate(frames):
            # 开场用 frame.trigger（语义帧的触发短语）
            if i == 0:
                lyric_lines.append(('intro', frame.trigger))
            # 后续事件根据位置分配 verse1 / verse2
            else:
                # v9.5: 第一个后续事件归 verse1，其余归 verse2
                section = 'verse1' if i == 1 else 'verse2'
                lyric_lines.append((section, frame.trigger))

                # v9.5: 用语义帧展开（behavior/tension 驱动）
                expansions = self._expand_from_frame(frame)
                if expansions:
                    for exp in expansions[:2]:
                        lyric_lines.append((section, exp))

        # v9.3: 在 verse2 前插入转折句（如果 verse2 不存在则加在 verse1 后）
        verse2_indices = [i for i, (s, _) in enumerate(lyric_lines) if s == 'verse2']
        if verse2_indices:
            # verse2 存在，插在 verse2 开头
            insert_pos = verse2_indices[0]
        elif len(frames) >= 2:
            # verse2 不存在但有足够事件，插在 verse1 最后之后
            verse1_end = max([i for i, (s, _) in enumerate(lyric_lines) if s == 'verse1'] + [0])
            insert_pos = verse1_end + 1
        else:
            insert_pos = None

        if insert_pos is not None:
            # v9.7: Hook由frame.conditioned生成，而非随机
            # 使用verse1最末帧的core来选hook（最成熟的情绪点）
            hook_frame = frames[-1] if frames else None
            if hook_frame and hook_frame.core in self.HOOK_TEMPLATES:
                hooks = self.HOOK_TEMPLATES[hook_frame.core]
                turning_point = random.choice(hooks)
            else:
                turning_point = random.choice(self.TURNING_PUNCH_LINES)
            lyric_lines.insert(insert_pos, ('turning', turning_point))

        # 结尾（情绪收束）
        if frames:
            last_frame = frames[-1]
            outro_options = [
                "原来已经回不去了",
                "你已经不是从前的你了",
                "我们早就散了",
            ]
            lyric_lines.append(('outro', random.choice(outro_options)))

        return {
            "events": frames,  # v9.5: List[SemanticFrame]
            "arc_type": arc_type,
            "lyric_lines": lyric_lines,
            "speaker": "我",
            "target": "你",
        }

    def events_to_lines(self, narrative: dict) -> list:
        """
        把叙事骨架转换成歌词行（供 LyricRenderer 使用）

        输入：narrative["lyric_lines"]
        输出：[line1, line2, ...] 歌词行列表
        """
        lines = []
        current_section = None

        section_markers = {
            'intro': '【开场】',
            'verse1': '【主歌1】',
            'verse2': '【主歌2】',
            'turning': '【转折】',
            'hook': '【Hook】',
            'outro': '【结尾】',
        }

        for section, text in narrative["lyric_lines"]:
            if section != current_section:
                marker = section_markers.get(section, f'【{section}】')
                lines.append(marker)
                current_section = section
            lines.append(text)

        return lines


# ==================== Art Layer: Lyric Renderer ====================

class LyricRenderer:
    """
    LyricRenderer - final lyric rendering
    """

    def __init__(self):
        self.last_output: Optional[str] = None

    def render(
        self,
        prompt_parts: Dict,
        emotion_vector: EmotionVector,
        rhythm_spec: LyricRhythmSpec,
        user_feedback: str = ""
    ) -> str:
        prompt = self._build_prompt(prompt_parts, user_feedback)
        temp = self._get_temperature(emotion_vector)
        output = llm(prompt, temp)
        output = self._post_process(output, rhythm_spec)
        self.last_output = output
        return output

    def _build_prompt(self, parts: Dict, feedback: str) -> str:
        prompt = f"""创作歌词：

{parts['theme']}
{parts['emotion']}
{parts['imagery']}

{parts['structure']}
{parts['rhythm']}
{parts['hook']}

要求：
1. 主歌4句+副歌4句+主歌2 4句+副歌4句
2. 意象清晰，画面感强
3. 情感真挚，不过度堆砌

{feedback if feedback else ''}

歌词："""

        return prompt

    def _get_temperature(self, emotion_vector: EmotionVector) -> float:
        if not emotion_vector:
            return 0.8

        primary, intensity = emotion_vector.get_primary()
        if intensity > 0.7:
            return 0.7
        elif intensity > 0.4:
            return 0.8
        return 0.9

    def _post_process(self, output: str, spec: LyricRhythmSpec) -> str:
        lines = [l.strip() for l in output.split("\n") if l.strip()]
        structured = []
        section_map = {
            0: "【主歌1】",
            4: "【副歌】",
            8: "【主歌2】",
            12: "【副歌】"
        }

        for i, line in enumerate(lines):
            if i in section_map:
                structured.append(section_map[i])
            structured.append(line)

        return "\n".join(structured)

    def render_with_bias(
        self,
        prompt_parts: Dict,
        emotion_vector: EmotionVector,
        rhythm_spec: LyricRhythmSpec,
        emotion_bias,
        user_feedback: str = ""
    ) -> str:
        """
        v7.8: 使用 EmotionBias 约束渲染
        """
        # 使用 bias 的温度控制
        temp = emotion_bias.to_art_constraints()["temperature"]

        # 构建增强的 prompt
        prompt = self._build_bias_prompt(prompt_parts, emotion_bias, user_feedback)

        output = llm(prompt, temp)
        output = self._post_process(output, rhythm_spec)
        self.last_output = output
        return output

    def _build_bias_prompt(
        self,
        parts: Dict,
        bias,
        feedback: str
    ) -> str:
        """v7.8: 构建受 bias 约束的 prompt"""
        prompt = f"""创作歌词：

{parts.get('theme', '')}
{parts.get('emotion', '')}
{parts.get('emotion_bias', '')}
{parts.get('imagery', '')}

{parts.get('structure', '')}
{parts.get('rhythm', '')}
{parts.get('hook', '')}
{parts.get('intensity_curve', '')}
{parts.get('compression_note', '')}

要求：
1. 主歌4句+副歌4句+主歌2 4句+副歌4句
2. 意象清晰，画面感强
3. 情感真挚，不过度堆砌
4. 遵循{parts.get('compression_note', '标准')}的表达方式
5. 呈现{parts.get('intensity_curve', '标准')}的情感曲线

{feedback if feedback else ''}

歌词："""

        return prompt


# ==================== Art Pipeline ====================

class ArtPipeline:
    """
    ArtPipeline - integrated art generation pipeline
    v8.1: 爆款歌词生成 + 人格化人类层

    新增（用户可见）：
    - HookGenerator: 记忆点制造器（v8.1: Hook人格化）
    - EmotionCurve: 情绪起伏控制
    - StylePreset: 风格模板
    - HumanRewriteLayer: 人类化算子（v8.1: Profile Strength）
    - HumanProfile: 人格控制（v8.0）
    """

    def __init__(self, rhythm_spec: LyricRhythmSpec = None, humanize: bool = True):
        self.compression = ChatCompressionLayer()
        self.emotion_engine = EmotionEngine()
        self.planner = LyricPlanner(rhythm_spec or LyricRhythmSpec())
        self.renderer = LyricRenderer()
        self.hook_generator = HookGenerator()
        self.humanizer = HumanRewriteLayer(intensity=0.3)  # v7.9: 人类化算子
        self.narrative_builder = NarrativeBuilder()  # v9.2: 叙事构建器
        self.enable_humanize = humanize
        self.generation_count = 0
        self.last_emotion_bias = None
        self.last_hook = None
        self.last_style = None
        self.last_emotion_curve = None
        self.last_humanized = None
        self.last_profile = None
        self.last_narrative = None

    def run(self, chat_messages: List[Dict], user_feedback: str = "") -> Dict:
        """
        标准运行模式（向后兼容）
        v8.1: 自动检测人格并应用
        """
        self.generation_count += 1

        compression_result = self.compression.compress(chat_messages)
        emotion_vector = compression_result["emotion_vector"]
        self.emotion_engine.set_emotion(emotion_vector)

        # v8.1: 自动检测人格
        profile_type = HumanProfileLibrary.detect_from_emotion(emotion_vector)
        profile = HumanProfileLibrary.get_profile(profile_type)
        self.last_profile = profile

        # v9.2: 构建叙事骨架（事件抽取 + 视角统一）
        narrative = self.narrative_builder.build_from_chat(
            chat_messages, emotion_vector, profile
        )
        self.last_narrative = narrative

        # v7.8: 自动检测风格和情绪曲线
        style = StylePresetLibrary.detect_from_emotion(emotion_vector)
        emotion_curve = self._detect_emotion_curve(emotion_vector)
        self.last_style = style
        self.last_emotion_curve = emotion_curve

        # 生成 hook（v8.1: 传入profile使Hook人格化）
        hook = self.hook_generator.generate_hook(
            theme=compression_result["core_theme"],
            emotion=emotion_vector,
            imagery=compression_result["imagery_tokens"],
            style=style,
            emotion_curve=emotion_curve,
            profile=profile
        )
        self.last_hook = hook

        lyric_plan = self.planner.plan(emotion_vector, compression_result["imagery_tokens"])
        # v9.2: 把叙事骨架传给 prompt 生成
        prompt_parts = self.planner.generate_prompt_parts(
            compression_result, lyric_plan, narrative=narrative
        )
        lyrics = self.renderer.render(
            prompt_parts,
            emotion_vector,
            self.planner.rhythm_spec,
            user_feedback
        )

        # v7.8: 在歌词中加入 hook
        lyrics = self._inject_hook(lyrics, hook, emotion_curve)

        # v8.1: 应用人类化噪声（使用profile和profile_strength）
        raw_lyrics = lyrics
        if self.enable_humanize:
            lyrics = self.humanizer.humanize(
                lyrics,
                emotion_weight=emotion_vector.get_primary()[1],
                profile=profile
            )
            self.last_humanized = lyrics

        return {
            "lyrics": lyrics,
            "raw_lyrics": raw_lyrics,  # v7.9: 保留原始歌词
            "compression": compression_result,
            "emotion_vector": emotion_vector,
            "profile": profile,  # v8.1: 返回使用的人格
            "narrative": narrative,  # v9.2: 叙事骨架
            "plan": lyric_plan,
            "prompt_parts": prompt_parts,
            "imagery": compression_result["imagery_tokens"],
            "theme": compression_result["core_theme"],
            "generation_count": self.generation_count,
            "hook": hook,
            "style": style.value,
            "emotion_curve": emotion_curve.value,
            "hook_variants": self.hook_generator.enhance_hook_variants(hook, emotion_vector),
            "humanized": self.enable_humanize  # v7.9: 是否应用了人类化
        }

    def run_with_style(
        self,
        chat_messages: List[Dict],
        style: StylePreset,
        emotion_curve: EmotionCurve = None,
        user_feedback: str = ""
    ) -> Dict:
        """
        v7.8: 指定风格的歌词生成
        """
        self.generation_count += 1
        self.last_style = style

        compression_result = self.compression.compress(chat_messages)
        emotion_vector = compression_result["emotion_vector"]
        self.emotion_engine.set_emotion(emotion_vector)

        # 使用指定的情绪曲线
        emotion_curve = emotion_curve or self._detect_emotion_curve(emotion_vector)
        self.last_emotion_curve = emotion_curve

        # 生成 hook（使用风格预设）
        hook = self.hook_generator.generate_hook(
            theme=compression_result["core_theme"],
            emotion=emotion_vector,
            imagery=compression_result["imagery_tokens"],
            style=style,
            emotion_curve=emotion_curve
        )
        self.last_hook = hook

        lyric_plan = self.planner.plan(emotion_vector, compression_result["imagery_tokens"])
        prompt_parts = self._generate_style_prompt_parts(
            compression_result, lyric_plan, style, emotion_curve
        )
        lyrics = self.renderer.render(
            prompt_parts,
            emotion_vector,
            self.planner.rhythm_spec,
            user_feedback
        )

        lyrics = self._inject_hook(lyrics, hook, emotion_curve)

        # v7.9: 应用人类化噪声
        raw_lyrics = lyrics
        if self.enable_humanize:
            lyrics = self.humanizer.humanize(lyrics)
            self.last_humanized = lyrics

        return {
            "lyrics": lyrics,
            "raw_lyrics": raw_lyrics,
            "compression": compression_result,
            "emotion_vector": emotion_vector,
            "plan": lyric_plan,
            "prompt_parts": prompt_parts,
            "imagery": compression_result["imagery_tokens"],
            "theme": compression_result["core_theme"],
            "generation_count": self.generation_count,
            "hook": hook,
            "style": style.value,
            "emotion_curve": emotion_curve.value,
            "hook_variants": self.hook_generator.enhance_hook_variants(hook, emotion_vector),
            "humanized": self.enable_humanize
        }

    def run_with_humanize(
        self,
        chat_messages: List[Dict],
        style: StylePreset = None,
        humanize_intensity: float = 0.3,
        user_feedback: str = ""
    ) -> Dict:
        """
        v7.9 核心接口：带人类化控制的歌词生成

        Args:
            chat_messages: 聊天记录
            style: 风格预设（可选，自动检测）
            humanize_intensity: 人类化强度 0.0-1.0，默认0.3
                - 0.0: 不应用人类化（原始AI歌词）
                - 0.3: 轻度人类化（推荐）
                - 0.6: 激进人类化
            user_feedback: 用户反馈

        Returns:
            {
                "lyrics": "人类化后的歌词",
                "raw_lyrics": "原始AI歌词",
                "diff": "人类化差异对比",
                "humanized": True,
                ...
            }
        """
        # 临时设置人类化强度
        original_intensity = self.humanizer.intensity
        self.humanizer.intensity = humanize_intensity
        self.enable_humanize = humanize_intensity > 0

        # 生成歌词
        if style:
            result = self.run_with_style(chat_messages, style, user_feedback=user_feedback)
        else:
            result = self.run(chat_messages, user_feedback)

        # 恢复原始设置
        self.humanizer.intensity = original_intensity
        self.enable_humanize = original_intensity > 0

        # v7.9: 添加人类化差异信息
        result["humanize_intensity"] = humanize_intensity
        if result.get("raw_lyrics") and result["raw_lyrics"] != result["lyrics"]:
            result["diff"] = self._compute_diff(result["raw_lyrics"], result["lyrics"])

        return result

    def _compute_diff(self, raw: str, humanized: str) -> Dict:
        """计算人类化差异"""
        raw_lines = raw.split("\n")
        human_lines = humanized.split("\n")

        changed = 0
        for r, h in zip(raw_lines, human_lines):
            if r != h:
                changed += 1

        return {
            "total_lines": len(raw_lines),
            "changed_lines": changed,
            "change_rate": round(changed / max(len(raw_lines), 1), 2)
        }

    def run_with_bias(
        self,
        chat_messages: List[Dict],
        emotion_bias,
        user_feedback: str = ""
    ) -> Dict:
        """
        v7.8: EmotionBias 驱动的自适应生成
        """
        self.generation_count += 1
        self.last_emotion_bias = emotion_bias

        # 1. 使用 bias 约束压缩行为
        if emotion_bias.compression_mode == "fragmented":
            # 碎片化压缩：更激进的意象提取
            compression_result = self._compress_fragmented(chat_messages)
        elif emotion_bias.compression_mode == "associative":
            # 联想压缩：强调意象跳跃
            compression_result = self._compress_associative(chat_messages)
        elif emotion_bias.compression_mode == "chronological":
            # 时序压缩：保持时间顺序
            compression_result = self._compress_chronological(chat_messages)
        else:
            # 标准压缩
            compression_result = self.compression.compress(chat_messages)

        # 2. 使用 bias 覆盖情绪
        emotion_vector = compression_result["emotion_vector"]
        self.emotion_engine.set_emotion(emotion_vector)

        # 3. 使用 bias 生成节奏规格
        rhythm_spec = LyricRhythmSpec.from_emotion_bias(emotion_bias)

        # 4. 生成歌词计划
        lyric_plan = self.planner.plan(emotion_vector, compression_result["imagery_tokens"])
        prompt_parts = self._generate_bias_prompt_parts(
            compression_result, lyric_plan, emotion_bias
        )

        # 5. 渲染时使用 bias 约束的温度
        lyrics = self.renderer.render_with_bias(
            prompt_parts,
            emotion_vector,
            rhythm_spec,
            emotion_bias,
            user_feedback
        )

        return {
            "lyrics": lyrics,
            "compression": compression_result,
            "emotion_vector": emotion_vector,
            "plan": lyric_plan,
            "prompt_parts": prompt_parts,
            "imagery": compression_result["imagery_tokens"],
            "theme": compression_result["core_theme"],
            "generation_count": self.generation_count,
            "emotion_bias": emotion_bias,  # v7.8: 返回 bias 记录
            "bias_constraints": emotion_bias.to_art_constraints()
        }

    def _compress_fragmented(self, chat_messages: List[Dict]) -> Dict:
        """碎片化压缩：高情绪强度，保留断裂感"""
        result = self.compression.compress(chat_messages)
        # 增加意象冲突性
        result["imagery_tokens"] = result["imagery_tokens"][:3] + ["碎片", "裂痕"]
        result["core_theme"] = "破碎的连接"
        return result

    def _compress_associative(self, chat_messages: List[Dict]) -> Dict:
        """联想压缩：跳跃性强，意象关联"""
        result = self.compression.compress(chat_messages)
        # 增加联想意象
        result["imagery_tokens"] = result["imagery_tokens"] + ["涟漪", "折射", "光斑"]
        result["core_theme"] = "记忆的折射"
        return result

    def _compress_chronological(self, chat_messages: List[Dict]) -> Dict:
        """时序压缩：保持时间顺序感"""
        result = self.compression.compress(chat_messages)
        # 强化时间意象
        result["imagery_tokens"] = result["imagery_tokens"] + ["倒带", "时钟"]
        result["core_theme"] = "时光的痕迹"
        return result

    def _generate_bias_prompt_parts(
        self,
        compression_result: Dict,
        lyric_plan: Dict,
        bias: 'EmotionBias'
    ) -> Dict:
        """v7.8: 使用 bias 生成增强的 prompt parts"""
        emotion_vector = compression_result["emotion_vector"]
        imagery = compression_result["imagery_tokens"]

        # 构建情绪描述（使用 bias 的描述符）
        emotion_desc = f"情绪：{bias.emotion_descriptor.replace('_', ' ')}"

        # 构建节奏描述
        rhythm_desc_map = {
            "steady": "节奏：平稳推进",
            "build": "节奏：渐强",
            "pulse": "节奏：脉冲式",
            "fade": "节奏：消散式"
        }
        rhythm_desc = rhythm_desc_map.get(bias.rhythm_bias, "节奏：标准")

        parts = {
            "theme": f"主题：{compression_result['core_theme']}",
            "emotion": emotion_desc,
            "emotion_bias": f"创作指引：{bias.emotion_descriptor}",
            "imagery": f"意象：{'、'.join(imagery[:4])}" if imagery else "意象：待定",
            "structure": self.planner._format_structure(lyric_plan),
            "rhythm": rhythm_desc,
            "hook": self.planner._format_hook(lyric_plan),
            "intensity_curve": f"情感曲线：{bias.intensity_curve}",
            "compression_note": f"表达方式：{bias.compression_mode}式叙述"
        }

        return parts

    def _detect_emotion_curve(self, emotion_vector: EmotionVector) -> EmotionCurve:
        """从情绪向量检测情绪曲线"""
        primary, intensity = emotion_vector.get_primary()

        # 悲伤 + 怀旧 → 低→高→消散
        if emotion_vector.sadness > 0.4 and emotion_vector.nostalgia > 0.3:
            return EmotionCurve.LOW_PEAK_FADE
        # 希望 → V型（先低后高）
        elif emotion_vector.hope > 0.4:
            return EmotionCurve.V_SHAPE
        # 愤怒 → 波浪
        elif emotion_vector.anger > 0.4:
            return EmotionCurve.WAVE
        # 温暖 → 平稳
        elif emotion_vector.warmth > 0.4:
            return EmotionCurve.STEADY
        # 高强度情绪 → 渐强
        elif intensity > 0.6:
            return EmotionCurve.BUILD_PEAK
        return EmotionCurve.STEADY

    def _inject_hook(self, lyrics: str, hook: str, curve: EmotionCurve) -> str:
        """v7.8: 将 hook 注入到歌词中（根据情绪曲线决定位置）"""
        if not hook:
            return lyrics

        lines = lyrics.split("\n")

        # 根据情绪曲线决定 hook 插入位置
        hook_positions = {
            EmotionCurve.LOW_PEAK_FADE: -1,     # 结尾
            EmotionCurve.BUILD_PEAK: 3,          # 副歌位置
            EmotionCurve.WAVE: 0,                # 开头
            EmotionCurve.STEADY: -1,             # 结尾
            EmotionCurve.V_SHAPE: 7,             # V型底部之后
        }

        pos = hook_positions.get(curve, -1)

        # 构建 hook 行（防止双 prefix：_apply_profile_to_hook 已加过）
        # 只判断开头，不扫全文，避免内容本身含"!"被误判
        if not hook.lstrip().startswith((HOOK_PREFIX, "!")):
            hook = f"{HOOK_PREFIX} {hook}"
        hook_line = f"\n{hook}\n"

        if 0 <= pos < len(lines):
            lines.insert(pos, hook_line)
        elif pos == -1 and lines:
            lines.insert(len(lines) - 1, hook_line)

        return "\n".join(lines)

    def _generate_style_prompt_parts(
        self,
        compression_result: Dict,
        lyric_plan: Dict,
        style: StylePreset,
        emotion_curve: EmotionCurve
    ) -> Dict:
        """v7.8: 使用风格预设生成 prompt"""
        emotion_vector = compression_result["emotion_vector"]
        imagery = compression_result["imagery_tokens"]
        style_config = StylePresetLibrary.get_preset(style)
        arc = EmotionArc.from_curve(emotion_curve)

        parts = {
            "theme": f"主题：{compression_result['core_theme']}",
            "emotion": f"情绪：{style_config.name}风格",
            "style": f"风格：{style_config.name}",
            "style_desc": f"特点：{', '.join(style_config.emotional_keywords[:3])}",
            "imagery": f"意象：{', '.join(style_config.typical_imagery[:3])}",
            "structure": self.planner._format_structure(lyric_plan),
            "rhythm": f"节奏：{arc.curve_type.value}",
            "arc": f"情感弧线：{' → '.join(arc.sections)}",
            "hook": self.planner._format_hook(lyric_plan)
        }

        return parts

    def get_last_emotion(self) -> Optional[EmotionVector]:
        return self.emotion_engine.emotion_vector


# ==================== Melody Layer: 歌词 → 音符序列 ====================
# v9.9: MelodyPlanner - 歌词 → Melody IR（中间协议层）


@dataclass
class Note:
    """
    Melody IR - 单音符表示
    一字一音（最简版本）
    """
    pitch: str       # 音高，如 "C4", "D#4", "REST"
    duration: float  # 持续秒数
    lyric: str       # 对应的字


@dataclass
class PerformanceNote(Note):
    """
    Performance IR - 带表现力的音符
    v10: 在 Note 基础上增加人声表现力细节

    区别于 Note：
    - Note: 离散的"该唱什么"
    - PerformanceNote: 连续的"怎么唱"
    """
    pitch_curve: list = None     # 音高曲线 [(time_offset, pitch), ...]
    vibrato: float = 0.0        # 颤音强度 0.0-1.0
    breathiness: float = 0.0    # 气声强度 0.0-1.0
    stress: float = 0.0         # 力度 0.0-1.0（句首强/句尾弱）
    attack: float = 0.5        # 起音速度 0.0-1.0（快/慢）


@dataclass
class MelodyPlan:
    """完整旋律规划"""
    key: str         # 调式，如 "C_major", "A_minor"
    bpm: int         # 节拍，如 70, 85, 110
    notes: list      # List[Note]


@dataclass
class PerformancePlan:
    """
    v10 Performance Plan - 完整表演规划
    包含音符的表现力参数（气声/颤音/力度/起音）
    """
    key: str            # 调式
    bpm: int            # 节拍
    emotion: str        # 主情绪（用于 vocal style）
    notes: list         # List[PerformanceNote]


class PerformancePlanner:
    """
    v10 PerformancePlanner - 旋律 IR → 表演 IR

    功能：
    1. 将 MelodyPlan 转换为 PerformancePlan
    2. 添加人声表现力细节（气声/颤音/力度/起音）
    3. 时序人类化（±30~80ms 微偏移）
    4. 情绪 → 声线风格映射（核心差异化）

    这是你系统从"歌词工具"变成"音乐引擎"的关键层
    """

    # 情绪 → 气声强度映射（气声越多越"倾诉感"）
    BREATHINESS_MAP = {
        "sadness": 0.6,
        "nostalgia": 0.5,
        "loneliness": 0.7,
        "regret": 0.5,
        "anger": 0.2,
        "joy": 0.2,
        "warmth": 0.3,
        "hope": 0.3,
        "default": 0.4,
    }

    # 情绪 → 颤音强度映射
    VIBRATO_MAP = {
        "sadness": 0.4,
        "nostalgia": 0.5,
        "loneliness": 0.3,
        "regret": 0.4,
        "anger": 0.2,
        "joy": 0.2,
        "warmth": 0.3,
        "hope": 0.3,
        "default": 0.3,
    }

    # 情绪 → 起音速度映射（越慢越"压抑"，越快越"爆发"）
    ATTACK_MAP = {
        "sadness": 0.3,    # 慢起音（压抑）
        "nostalgia": 0.4,
        "loneliness": 0.3,
        "regret": 0.4,
        "anger": 0.8,      # 快起音（爆发）
        "joy": 0.7,
        "warmth": 0.6,
        "hope": 0.6,
        "default": 0.5,
    }

    # 情绪 → 力度映射
    STRESS_MAP = {
        "sadness": 0.4,
        "nostalgia": 0.5,
        "loneliness": 0.4,
        "regret": 0.4,
        "anger": 0.8,      # 高力度（爆发）
        "joy": 0.7,
        "warmth": 0.6,
        "hope": 0.6,
        "default": 0.5,
    }

    def plan(self, melody_plan: MelodyPlan, emotion_vector: 'EmotionVector') -> PerformancePlan:
        """
        将 MelodyPlan 转换为 PerformancePlan（添加表现力）

        Args:
            melody_plan: MelodyPlanner 输出的旋律规划
            emotion_vector: 情绪向量

        Returns:
            PerformancePlan: 包含表演细节的完整规划
        """
        import random

        primary, intensity = emotion_vector.get_primary()

        # 获取当前情绪的参数
        breathiness = self.BREATHINESS_MAP.get(primary, self.BREATHINESS_MAP["default"])
        vibrato = self.VIBRATO_MAP.get(primary, self.VIBRATO_MAP["default"])
        attack = self.ATTACK_MAP.get(primary, self.ATTACK_MAP["default"])
        stress = self.STRESS_MAP.get(primary, self.STRESS_MAP["default"])

        # 强度影响参数微调
        intensity_factor = 0.5 + intensity * 0.5  # 0.5-1.0

        performance_notes = []
        for i, note in enumerate(melody_plan.notes):
            if note.pitch == "REST":
                performance_notes.append(PerformanceNote(
                    pitch=note.pitch,
                    duration=note.duration,
                    lyric=note.lyric,
                ))
                continue

            # 计算表现力参数

            # 1. 句首 → 句尾力度衰减
            note_stress = stress * intensity_factor
            if i > 0:
                # 越靠后力度越低（句尾衰减）
                note_stress = max(0.2, note_stress - (i * 0.02))

            # 2. 起音速度：句首快/句尾慢
            note_attack = attack
            if i > 2:
                note_attack = max(0.2, note_attack - (i * 0.015))

            # 3. Hook/副歌位置用更高力度
            is_hook_position = (i % 8 < 4)  # 前半拍强
            if is_hook_position:
                note_stress = min(1.0, note_stress * 1.2)
                note_attack = min(1.0, note_attack * 1.1)

            # 4. 颤音：情绪强时更多
            note_vibrato = vibrato
            if intensity > 0.6:
                note_vibrato = min(0.8, vibrato * 1.3)

            # 5. 气声：sadness/loneliness 用更多
            note_breathiness = breathiness
            if primary in ("sadness", "loneliness"):
                note_breathiness = min(0.9, breathiness * 1.2)

            # 6. 音高曲线（连音滑向下一个音）
            pitch_curve = self._build_pitch_curve(note, melody_plan.notes, i)

            performance_notes.append(PerformanceNote(
                pitch=note.pitch,
                duration=note.duration,
                lyric=note.lyric,
                pitch_curve=pitch_curve,
                vibrato=note_vibrato,
                breathiness=note_breathiness,
                stress=note_stress,
                attack=note_attack,
            ))

        # 时序人类化
        performance_notes = self._humanize_timing(performance_notes, intensity)

        return PerformancePlan(
            key=melody_plan.key,
            bpm=melody_plan.bpm,
            emotion=primary,
            notes=performance_notes,
        )

    def _build_pitch_curve(self, note: Note, all_notes: list, index: int) -> list:
        """
        构建音高曲线（连音滑向下一个音）

        简单实现：从当前音高开始，微小波动
        """
        if note.pitch == "REST":
            return []

        # 检查下一个音是否存在
        if index + 1 < len(all_notes):
            next_note = all_notes[index + 1]
            if next_note.pitch != "REST":
                # 音高曲线：从当前音滑向下一个音（简化：不变）
                return [(0.0, note.pitch), (note.duration * 0.8, next_note.pitch)]

        # 单音：轻微波动模拟人声
        return [(0.0, note.pitch), (note.duration, note.pitch)]

    def _humanize_timing(self, notes: list, intensity: float) -> list:
        """
        时序人类化：±30~80ms 微偏移

        规则：
        - 随机偏移 ±30~80ms
        - 句尾延迟 50~100ms
        - Hook 位置提前 20~50ms
        """
        import random

        humanized = []
        cumulative_offset = 0.0

        for i, note in enumerate(notes):
            if note.pitch == "REST":
                cumulative_offset += note.duration
                humanized.append(note)
                continue

            # 随机微偏移 ±40ms（0.04秒）
            offset = random.uniform(-0.04, 0.04) * (0.5 + intensity * 0.5)

            # 句尾延迟 50~100ms
            is_sentence_end = (i == len(notes) - 1 or all_notes_rest_after(i, notes))
            if is_sentence_end:
                offset += random.uniform(0.05, 0.1)

            # Hook 位置提前 20~50ms
            is_hook_pos = (i % 8 < 4)
            if is_hook_pos:
                offset -= random.uniform(0.02, 0.05)

            humanized_note = PerformanceNote(
                pitch=note.pitch,
                duration=note.duration,
                lyric=note.lyric,
                pitch_curve=note.pitch_curve,
                vibrato=note.vibrato,
                breathiness=note.breathiness,
                stress=note.stress,
                attack=note.attack,
            )
            humanized.append(humanized_note)

        return humanized


def all_notes_rest_after(index: int, notes: list) -> bool:
    """检查某个音符之后是否全是 REST"""
    for j in range(index + 1, len(notes)):
        if notes[j].pitch != "REST":
            return False
    return True


# ==================== Melody Layer: 歌词 → 音符序列 ====================
# v9.9: MelodyPlanner - 歌词 → Melody IR（中间协议层）

"""
MelodyPlanner - 歌词 → 旋律 IR

功能：
1. 将歌词行转换为音符序列（Melody IR）
2. 情绪 → 调式/BPM 映射（核心差异化）
3. 是 DiffSinger / So-VITS-SVC 的前置协议层

使用方式：
    planner = MelodyPlanner()
    plan = planner.plan([('verse1', '你不是没回'), ('turning', '只是没想回')], emotion_vector)
    # plan.key → "A_minor"
    # plan.bpm → 70
    # plan.notes → [Note(pitch="C4", duration=0.5, lyric="你"), ...]
"""

class MelodyPlanner:
    """
    v9.9 MelodyPlanner - 歌词 → 旋律 IR
    """

    # 调式音阶
    SCALES = {
        "C_major": ["C4", "D4", "E4", "F4", "G4", "A4", "B4"],
        "G_major": ["G4", "A4", "B4", "C5", "D5", "E5", "F#5"],
        "A_minor": ["A4", "B4", "C5", "D5", "E5", "F5", "G5"],
        "E_minor": ["E4", "F#4", "G4", "A4", "B4", "C5", "D5"],
        "D_minor": ["D4", "E4", "F4", "G4", "A4", "Bb4", "C5"],
    }

    # 和弦音（锚点音 - 强拍用）
    CHORD_TONES = {
        "C_major": ["C4", "E4", "G4"],
        "G_major": ["G4", "B4", "D5"],
        "A_minor": ["A4", "C5", "E5"],
        "E_minor": ["E4", "G4", "B4"],
        "D_minor": ["D4", "F4", "A4"],
    }

    # 情绪 → 调式映射
    KEY_MAP = {
        "sadness": "A_minor",
        "nostalgia": "E_minor",
        "loneliness": "D_minor",
        "regret": "A_minor",
        "anger": "E_minor",
        "joy": "C_major",
        "warmth": "G_major",
        "hope": "G_major",
        "default": "C_major",
    }

    # 情绪 → BPM 映射
    BPM_MAP = {
        "sadness": 70,
        "nostalgia": 75,
        "loneliness": 68,
        "regret": 72,
        "anger": 110,
        "joy": 95,
        "warmth": 85,
        "hope": 90,
        "default": 85,
    }

    # 节奏模板（不均匀，制造"歌感"而非"念稿感"）
    RHYTHM_PATTERNS = [
        [0.5, 0.5, 1.0],         # 短-短-长（最常用）
        [0.25, 0.25, 0.5, 1.0], # 短短短-长（切分感）
        [0.5, 1.0, 0.5],         # 短-长-短（起伏）
        [0.375, 0.375, 0.75],    # 三连音变体
    ]

    # Hook 乐句模板（AABA 结构）
    # 4字小节为单位：motif A / motif A / motif B / motif A（回归）
    HOOK_MOTIFS = {
        "A": [("C4", 0.5), ("E4", 0.5), ("G4", 0.5), ("E4", 0.5)],
        "B": [("G4", 0.5), ("A4", 0.5), ("B4", 0.5), ("A4", 0.5)],
    }

    def plan(self, lyric_lines: list, emotion_vector: 'EmotionVector') -> MelodyPlan:
        """
        将歌词行列表转换为旋律规划

        Args:
            lyric_lines: [(section, text), ...] 如 [('verse1', '你不是没回'), ('turning', '只是没想回')]
            emotion_vector: EmotionVector 实例

        Returns:
            MelodyPlan: {
                "key": "A_minor",
                "bpm": 70,
                "notes": [Note(...), ...]
            }
        """
        import random

        primary, intensity = emotion_vector.get_primary()

        # 1. 选择调式和 BPM
        key = self.KEY_MAP.get(primary, self.KEY_MAP["default"])
        bpm = self.BPM_MAP.get(primary, self.BPM_MAP["default"])

        # 2. 获取音阶 + 和弦音
        scale = self.SCALES.get(key, self.SCALES["C_major"])
        chord_tones = self.CHORD_TONES.get(key, self.CHORD_TONES.get("C_major"))

        notes = []
        rhythm_pattern_idx = 0

        for section, text in lyric_lines:
            # Hook 句使用 AABA 结构重复
            if section == "turning" or "hook" in section:
                section_notes = self._generate_hook_melody(text, chord_tones)
            else:
                # 普通句使用节奏模板 + 和弦音机制
                section_notes = self._generate_line_melody(
                    text, scale, chord_tones, section, rhythm_pattern_idx
                )
                rhythm_pattern_idx = (rhythm_pattern_idx + 1) % len(self.RHYTHM_PATTERNS)
            notes.extend(section_notes)

        return MelodyPlan(key=key, bpm=bpm, notes=notes)

    def _generate_line_melody(
        self, line: str, scale: list, chord_tones: list, section: str, pattern_idx: int
    ) -> list:
        """将一行歌词转换为音符序列（使用节奏模板 + 和弦音机制）"""
        import random

        notes = []
        pattern = self.RHYTHM_PATTERNS[pattern_idx % len(self.RHYTHM_PATTERNS)]
        pattern_pos = 0

        for i, char in enumerate(line):
            # 标点停顿
            if char in "，。！？":
                notes.append(Note(pitch="REST", duration=0.5, lyric=char))
                pattern_pos = 0
                continue
            if char.strip() == "":
                continue

            # 获取当前节奏值
            duration = pattern[pattern_pos % len(pattern)]

            # 8% 概率随机 REST（呼吸感），不消耗节奏拍
            if random.random() < 0.08:
                notes.append(Note(pitch="REST", duration=duration, lyric=""))
                continue

            # 消耗节奏拍（只有实际音符才推进）
            pattern_pos = (pattern_pos + 1) % len(pattern)

            # 和弦音机制：强拍用和弦音（每4字一个强拍）
            is_strong_beat = (i % 4 == 0)
            if is_strong_beat:
                # 强拍 → 锚点音（和弦音）
                pitch = random.choice(chord_tones)
            else:
                # 弱拍 → 音阶经过音
                idx = min(i, len(scale) - 1)
                pitch = scale[idx]

            notes.append(Note(pitch=pitch, duration=duration, lyric=char))

        return notes

    def _generate_hook_melody(self, line: str, chord_tones: list) -> list:
        """
        Hook 句使用 AABA 乐句结构（制造洗脑感）
        不是逐字循环模板，而是乐句级别的重复

        结构：
        第1句 → motif A（4字）
        第2句 → motif A repeat（4字）
        第3句 → motif B（变化）
        第4句 → motif A（回归）
        """
        import random

        notes = []
        motif_len = 4  # 4字一个小节
        chars = [c for c in line if c.strip() and c not in "，。！？"]

        if len(chars) < 4:
            # 句子太短，退化成普通旋律
            return self._generate_line_melody(line, chord_tones, chord_tones, "hook", 0)

        # AABA 结构：第1/2/4句用 motif A，第3句用 motif B
        section_map = []  # (motif_key, char_range)
        total_chars = len(chars)

        pos = 0
        # 第1句 A
        section_map.append(("A", (pos, min(pos + motif_len, total_chars))))
        pos += motif_len
        # 第2句 A（重复）
        if pos < total_chars:
            section_map.append(("A", (pos, min(pos + motif_len, total_chars))))
            pos += motif_len
        # 第3句 B（变化）
        if pos < total_chars:
            section_map.append(("B", (pos, min(pos + motif_len, total_chars))))
            pos += motif_len
        # 第4句 A（回归）
        if pos < total_chars:
            section_map.append(("A", (pos, min(pos + motif_len, total_chars))))
            pos += motif_len

        # 生成每个乐句的音符
        motif_idx = 0
        for motif_key, (start, end) in section_map:
            motif = self.HOOK_MOTIFS[motif_key]
            motif_idx = 0
            for i in range(start, end):
                if i >= len(chars):
                    break
                template = motif[motif_idx % len(motif)]
                pitch = template[0]
                duration = 0.5  # Hook 固定短音有节奏感
                notes.append(Note(pitch=pitch, duration=duration, lyric=chars[i]))
                motif_idx += 1

            # 乐句之间加 REST（呼吸）
            if start + motif_len < end:
                notes.append(Note(pitch="REST", duration=0.5, lyric=""))

        return notes

    def to_midi_events(self, plan: MelodyPlan) -> list:
        """
        将 MelodyPlan 转换为 MIDI 事件列表（供合成器使用）

        Returns:
            [(time_sec, pitch, duration, lyric), ...]
        """
        events = []
        current_time = 0.0
        for note in plan.notes:
            if note.pitch == "REST":
                current_time += note.duration
            else:
                events.append((current_time, note.pitch, note.duration, note.lyric))
                current_time += note.duration
        return events


# ==================== Audio Layer: TTS + BGM + Composition ====================
# v9.8: 歌词 → 有声作品（TTS + 背景乐 + 合成）


class AudioLayer:
    """
    v9.8 Audio Layer - 歌词 → 有声作品

    功能：
    1. TTS：将歌词转为语音（edge-tts）
    2. BGM：根据情绪向量选择背景乐
    3. Composition：合成最终音频

    使用方式：
        audio = AudioLayer()
        audio.synthesize(lyric_lines, emotion_vector, output_path="song.mp3")
    """

    # 情绪 → BGM 文件名映射（需要配合实际BGM资源）
    BGM_MAP = {
        "sadness": "sad_piano",
        "nostalgia": "lofi_regret",
        "anger": "dark_beat",
        "loneliness": "empty_room",
        "regret": "lofi_slow",
        "hope": "soft_warm",
        "joy": "upbeat_light",
    }

    # TTS 角色映射
    TTS_VOICE_MAP = {
        "sadness": "zh-CN-XiaoyiNeural",      # 温柔女声
        "nostalgia": "zh-CN-YunxiNeural",     # 成熟男声
        "anger": "zh-CN-YunyangNeural",       # 沉稳男声
        "loneliness": "zh-CN-XiaoyiNeural",   # 温柔女声
        "regret": "zh-CN-YunxiNeural",         # 成熟男声
        "hope": "zh-CN-XiaoxiaoNeural",       # 清新女声
        "default": "zh-CN-XiaoyiNeural",
    }

    def __init__(self, bgm_dir: str = "assets/bgm"):
        self.bgm_dir = bgm_dir
        self.temp_dir = "temp_audio"
        import os
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(bgm_dir, exist_ok=True)

    def synthesize(
        self,
        lyric_lines: list,
        emotion_vector: 'EmotionVector',
        output_path: str = "output/song.mp3",
        voice_over_bgm: float = 0.7,
        bgm_volume: float = 0.3,
    ) -> dict:
        """
        将歌词列表合成为音频文件

        Args:
            lyric_lines: [(section, text), ...] 如 [('verse1', '我不是没回你'), ('turning', '只是没想回')]
            emotion_vector: EmotionVector 实例
            output_path: 输出文件路径
            voice_over_bgm: 人声音量 (0-1)
            bgm_volume: BGM 音量 (0-1)

        Returns:
            dict: {
                "lyric_lines": 原始歌词,
                "tts_files": TTS临时文件列表,
                "bgm_file": 背景乐文件,
                "final_output": 最终文件路径,
                "duration_sec": 总时长(秒),
            }
        """
        import os
        import asyncio

        import os as os_mod
        os_mod.makedirs(os_mod.path.dirname(output_path) or "output", exist_ok=True)

        # 1. 获取主情绪和TTS音色
        primary, intensity = emotion_vector.get_primary()
        voice = self.TTS_VOICE_MAP.get(primary, self.TTS_VOICE_MAP["default"])

        # 2. 收集所有歌词文本（按行）
        all_text_lines = []
        for _, text in lyric_lines:
            if text:
                all_text_lines.extend(text.split("\n"))

        # 过滤空行
        all_text_lines = [l.strip() for l in all_text_lines if l.strip()]
        if not all_text_lines:
            return {"error": "No lyric lines to synthesize"}

        # 3. 为每句歌词生成TTS
        tts_files = []
        for i, line_text in enumerate(all_text_lines):
            tts_file = os.path.join(self.temp_dir, f"tts_{i:03d}.mp3")
            tts_files.append(tts_file)
            asyncio.run(self._tts_async(line_text, tts_file, voice))

        # 4. 选择BGM
        bgm_key = self.BGM_MAP.get(primary, self.BGM_MAP["sadness"])
        bgm_file = os.path.join(self.bgm_dir, f"{bgm_key}.mp3")

        # 5. 合成最终音频
        if all(os.path.exists(f) for f in tts_files) and os.path.exists(bgm_file):
            final_output = self._compose_audio(tts_files, bgm_file, output_path, voice_over_bgm, bgm_volume)
            total_duration = len(tts_files) * 3.5  # 估算每句3.5秒
            return {
                "lyric_lines": lyric_lines,
                "tts_files": tts_files,
                "bgm_file": bgm_file,
                "final_output": final_output,
                "duration_sec": total_duration,
                "primary_emotion": primary,
                "voice": voice,
            }
        else:
            # TTS成功但BGM不存在时，只返回TTS文件列表
            return {
                "lyric_lines": lyric_lines,
                "tts_files": tts_files,
                "bgm_file": None,
                "final_output": None,
                "duration_sec": len(tts_files) * 3.5,
                "primary_emotion": primary,
                "voice": voice,
                "note": "BGM not found, TTS generated successfully",
            }

    async def _tts_async(self, text: str, output_path: str, voice: str):
        """异步生成TTS"""
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, voice=voice)
            await communicate.save(output_path)
        except Exception as e:
            import warnings
            warnings.warn(f"TTS generation failed for '{text}': {e}")

    def _compose_audio(
        self,
        tts_files: list,
        bgm_file: str,
        output_path: str,
        voice_vol: float,
        bgm_vol: float,
    ) -> str:
        """使用 moviepy 合成多轨音频"""
        try:
            from moviepy.editor import (
                AudioFileClip, CompositeAudioClip,
                concatenate_audioclips
            )
        except ImportError:
            return None

        # TTS 文件按顺序拼接
        tts_clips = []
        for f in tts_files:
            if os.path.exists(f):
                clip = AudioFileClip(f)
                tts_clips.append(clip)

        if not tts_clips:
            return None

        voice_track = concatenate_audioclips(tts_clips).volumex(voice_vol)

        # BGM
        bgm_track = AudioFileClip(bgm_file)
        # BGM 循环到与语音同长度
        bgm_loop = bgm_track.loop(duration=voice_track.duration)
        bgm_track_final = bgm_loop.volumex(bgm_vol)

        # 混音
        final = CompositeAudioClip([bgm_track_final, voice_track])
        final.write_audiofile(output_path, fps=44100)
        return output_path

    def synthesize_verse(
        self,
        verse_lines: list,
        emotion_vector: 'EmotionVector',
        output_path: str,
    ) -> str:
        """
        简化版：合成单个段落（如Hook句单独使用）
        用于快速生成一句可听的内容
        """
        import os
        import asyncio
        from shutil import copy

        primary, _ = emotion_vector.get_primary()
        voice = self.TTS_VOICE_MAP.get(primary, self.TTS_VOICE_MAP["default"])

        # 单句直接合成
        text = " ".join([l for _, l in verse_lines if l])
        if not text.strip():
            return None

        tts_file = os.path.join(self.temp_dir, "hook_tts.mp3")
        try:
            import edge_tts
            asyncio.run(self._tts_async(text, tts_file, voice))
            if os.path.exists(tts_file):
                os.makedirs(os.path.dirname(output_path) or "output", exist_ok=True)
                copy(tts_file, output_path)
                return output_path
        except Exception as e:
            import warnings
            warnings.warn(f"Verse TTS failed: {e}")
        return None


# ==================== Phoneme Alignment Layer ====================
# v11: 歌词 → 音素序列（接 DiffSinger / SVC 的关键层）


class PhonemeAligner:
    """
    v11 PhonemeAligner - 歌词 → 音素序列

    功能：
    将汉字歌词转换为音素序列，供 singing model 使用

    使用方式：
        aligner = PhonemeAligner()
        phonemes = aligner.align("你不是没回")
        # → ["ni3", "bu4", "shi4", "mei2", "hui2"]
    """

    # 声母映射
    INITIALS = {
        'b': 'b', 'p': 'p', 'm': 'm', 'f': 'f',
        'd': 'd', 't': 't', 'n': 'n', 'l': 'l',
        'g': 'g', 'k': 'k', 'h': 'h',
        'j': 'j', 'q': 'q', 'x': 'x',
        'zh': 'zh', 'ch': 'ch', 'sh': 'sh', 'r': 'r',
        'z': 'z', 'c': 'c', 's': 's', 'y': 'y', 'w': 'w',
    }

    # 韵母映射（带声调）
    FINALS = {
        'a': 'a1', 'ai': 'ai4', 'an': 'an1', 'ang': 'ang1', 'ao': 'ao1',
        'e': 'e4', 'ei': 'ei4', 'en': 'en1', 'eng': 'eng1', 'er': 'er2',
        'i': 'i1', 'ia': 'ia1', 'ian': 'ian1', 'iang': 'iang1', 'iao': 'iao1',
        'ie': 'ie1', 'in': 'in1', 'ing': 'ing1', 'iong': 'iong1', 'iu': 'iu1',
        'o': 'o2', 'ong': 'ong1', 'ou': 'ou1',
        'u': 'u1', 'ua': 'ua1', 'uai': 'uai4', 'uan': 'uan1', 'uang': 'uang1',
        'ui': 'ui1', 'un': 'un1', 'uo': 'uo2',
        'v': 'v0', 've': 've4',
    }

    # 单字读音库（常用字）
    PINYIN_DICT = {
        '你': 'ni3', '不': 'bu4', '是': 'shi4', '没': 'mei2', '回': 'hui2',
        '我': 'wo3', '们': 'men5', '在': 'zai4', '说': 'shuo1', '什': 'shen2',
        '么': 'me5', '来': 'lai2', '了': 'le5', '这': 'zhe4', '那': 'na4',
        '个': 'ge4', '人': 'ren2', '有': 'you3', '一': 'yi1', '个': 'ge4',
        '爱': 'ai4', '好': 'hao4', '吗': 'ma5', '想': 'xiang3', '要': 'yao4',
        '去': 'qu4', '看': 'kan4', '知': 'zhi1', '道': 'dao4',
        '距': 'ju4', '离': 'li2', '远': 'yuan3', '心': 'xin1', '了': 'le5',
        '只': 'zhi3', '想': 'xiang3', '等': 'deng3', '候': 'hou4',
        '错': 'cuo4', '过': 'guo4', '已': 'yi3', '经': 'jing1', '早': 'zao3',
        '从': 'cong2', '开': 'kai1', '始': 'shi3', '就': 'jiu4', '最': 'zui4',
        '后': 'hou4', '知': 'zhi1', '觉': 'jue2',
    }

    def align(self, text: str) -> list:
        """
        将中文文本转换为音素序列

        Args:
            text: 中文文本，如 "你不是没回"

        Returns:
            音素列表，如 ["ni3", "bu4", "shi4", "mei2", "hui2"]
        """
        phonemes = []
        for char in text:
            char = char.strip()
            if not char:
                continue
            if char in "，。！？、；：":
                phonemes.append('SP')  # silence phoneme
                continue
            pinyin = self._get_pinyin(char)
            phonemes.append(pinyin)
        return phonemes

    def align_with_timing(self, text: str, durations: list) -> list:
        """
        带时长信息的音素对齐

        Args:
            text: 中文文本
            durations: 每个字的持续时间列表（秒）

        Returns:
            [(phoneme, duration), ...]
        """
        phonemes = self.align(text)
        result = []
        for i, (phoneme, dur) in enumerate(zip(phonemes, durations)):
            if phoneme == 'SP':
                result.append((phoneme, dur))
            else:
                result.append((phoneme, dur))
        return result

    def _get_pinyin(self, char: str) -> str:
        """获取单个汉字的拼音"""
        if char in self.PINYIN_DICT:
            return self.PINYIN_DICT[char]

        # 尝试通过规则推断（简化版）
        # 实际生产环境应该用 pypinyin 库
        return f"{char}_unk"

    def phonemes_to_model_input(self, phonemes: list, pitch_curve: list) -> dict:
        """
        将音素序列 + 音高曲线转换为模型输入格式

        Args:
            phonemes: ["ni3", "bu4", "shi4", ...]
            pitch_curve: [(time, pitch), ...] 如 [(0.0, "C4"), (0.5, "D4")]

        Returns:
            适合 DiffSinger / SVC 的输入格式
        """
        # 构建音素时长序列
        note_durations = []
        total_time = 0
        for p in pitch_curve:
            if isinstance(p, tuple) and len(p) >= 2:
                dur = p[1] if len(p) == 3 else 0.5
            else:
                dur = 0.5
            note_durations.append(dur)
            total_time += dur

        # 构建 model-ready 结构
        return {
            "phonemes": phonemes,
            "durations": note_durations,
            "pitch_curve": pitch_curve,
            "total_duration": total_time,
        }


# ==================== DiffSinger Adapter ====================
# v11: PerformancePlan → DiffSinger 输入格式


class DiffSingerAdapter:
    """
    v11 DiffSingerAdapter - 将 PerformancePlan 转换为 DiffSinger 可用格式

    功能：
    1. PhonemeAligner 对齐音素
    2. 将 PerformanceNote 序列转换为 pitch curve
    3. 输出 DiffSinger / So-VITS-SVC 可消费的格式

    使用方式：
        adapter = DiffSingerAdapter()
        model_input = adapter.adapt(performance_plan)
        # → {"phonemes": [...], "f0": [...], "durations": [...]}
    """

    # DiffSinger 音素表（简化版）
    PHONEME_SET = [
        'SP', 'sil',  # silence
        'a', 'ai', 'an', 'ang', 'ao', 'e', 'ei', 'en', 'eng', 'er',
        'i', 'ia', 'ian', 'iang', 'iao', 'ie', 'in', 'ing', 'iong', 'iu',
        'o', 'ong', 'ou', 'u', 'ua', 'uai', 'uan', 'uang', 'ui', 'un', 'uo', 'v', 've',
        'b', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'm', 'n', 'p', 'q', 'r', 's', 't', 'w', 'x', 'y', 'z',
        'zh', 'ch', 'sh', 'c', 's',
        'ny', 'thy', 'ey', 'oy', 'gn',
    ]

    def adapt(self, performance_plan: 'PerformancePlan') -> dict:
        """
        将 PerformancePlan 转换为 DiffSinger 输入格式

        Args:
            performance_plan: PerformancePlan 实例

        Returns:
            dict: {
                "phonemes": [...],
                "f0": [...],  # 音高曲线 (time, f0_hz)
                "durations": [...],
                "breathiness": [...],
                "vibrato": [...],
            }
        """
        phoneme_aligner = PhonemeAligner()

        # 提取音素序列（从 lyric 字段）
        all_phonemes = []
        all_f0 = []
        all_durations = []
        all_breathiness = []
        all_vibrato = []
        all_stress = []
        all_attack = []

        time_offset = 0.0
        for note in performance_plan.notes:
            if note.pitch == "REST":
                time_offset += note.duration
                continue

            # 获取拼音音素
            char_phonemes = phoneme_aligner.align(note.lyric)
            if not char_phonemes or char_phonemes[0] == f"{note.lyric}_unk":
                char_phonemes = [note.lyric]

            # 音素时长（均分）
            phoneme_dur = note.duration / len(char_phonemes) if char_phonemes else note.duration

            for ph in char_phonemes:
                all_phonemes.append(ph)
                all_durations.append(phoneme_dur)
                all_breathiness.append(note.breathiness)
                all_vibrato.append(note.vibrato)
                all_stress.append(note.stress)
                all_attack.append(note.attack)

                # 音高曲线
                pitch_hz = self._pitch_to_hz(note.pitch)
                all_f0.append((time_offset, pitch_hz))
                time_offset += phoneme_dur

        return {
            "phonemes": all_phonemes,
            "f0": all_f0,  # [(time_sec, f0_hz), ...]
            "durations": all_durations,
            "breathiness": all_breathiness,
            "vibrato": all_vibrato,
            "stress": all_stress,
            "attack": all_attack,
            "key": performance_plan.key,
            "bpm": performance_plan.bpm,
        }

    def _pitch_to_hz(self, pitch: str) -> float:
        """将音高名称转换为 Hz"""
        pitch_freq = {
            "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23,
            "G4": 392.00, "A4": 440.00, "B4": 493.88,
            "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46,
            "G5": 783.99, "A5": 880.00, "B5": 987.77,
        }
        return pitch_freq.get(pitch, 440.0)


# ==================== DiffSinger Runner ====================
# v11: 真实唱歌模型推理


class DiffSingerRunner:
    """
    v11 DiffSingerRunner - 使用真实 DiffSinger 模型生成唱歌

    功能：
    1. 接收 Adapter 输出的 model_input
    2. 写入 DiffSinger 需要的中间格式（txt / json / npy）
    3. 调用 DiffSinger 推理
    4. 输出波形文件

    使用方式：
        runner = DiffSingerRunner()
        wav_path = runner.run(model_input, output_dir="output/diffsinger")
    """

    def __init__(self, diffsinger_path: str = None, device: str = "cpu"):
        """
        Args:
            diffsinger_path: DiffSinger 代码路径（默认从环境变量读取）
            device: 推理设备 "cpu" / "cuda"
        """
        self.diffsinger_path = diffsinger_path or os.environ.get("DIFFSINGER_PATH", "")
        self.device = device

    def run(self, model_input: dict, output_dir: str = "output/diffsinger") -> str:
        """
        执行 DiffSinger 推理

        Args:
            model_input: DiffSingerAdapter.adapt() 输出的格式
            output_dir: 输出目录

        Returns:
            生成的音频文件路径
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        # 1. 准备输入文件
        phoneme_file = os.path.join(output_dir, "phonemes.txt")
        f0_file = os.path.join(output_dir, "f0.npy")
        durations_file = os.path.join(output_dir, "durations.txt")

        self._write_phonemes(model_input["phonemes"], phoneme_file)
        self._write_f0(model_input["f0"], f0_file)
        self._write_durations(model_input["durations"], durations_file)

        # 2. 调用 DiffSinger 推理
        wav_path = os.path.join(output_dir, "generated.wav")
        success = self._run_diffsinger(
            phoneme_file, f0_file, durations_file,
            wav_path, model_input
        )

        if success and os.path.exists(wav_path):
            return wav_path

        # 降级：返回说明无法执行
        return None

    def _write_phonemes(self, phonemes: list, filepath: str):
        """写入音素序列"""
        with open(filepath, "w", encoding="utf-8") as f:
            for ph in phonemes:
                f.write(f"{ph}\n")

    def _write_f0(self, f0_curve: list, filepath: str):
        """写入 f0 曲线（numpy格式）"""
        try:
            import numpy as np
            times = [t for t, _ in f0_curve]
            freqs = [f for _, f in f0_curve]
            np.save(filepath, np.array([times, freqs]))
        except ImportError:
            # 没有 numpy 时写入 txt 格式
            with open(filepath.replace(".npy", ".txt"), "w", encoding="utf-8") as f:
                for t, f_hz in f0_curve:
                    f.write(f"{t:.4f} {f_hz:.2f}\n")

    def _write_durations(self, durations: list, filepath: str):
        """写入音素时长"""
        with open(filepath, "w", encoding="utf-8") as f:
            for d in durations:
                f.write(f"{d:.4f}\n")

    def _run_diffsinger(self, phoneme_file: str, f0_file: str,
                       durations_file: str, output_wav: str,
                       model_input: dict) -> bool:
        """
        调用 DiffSinger 推理脚本

        实际使用时需要：
        1. 安装 DiffSinger: pip install diffsinger
        2. 下载预训练权重
        3. 替换此方法中的调用逻辑
        """
        if not self.diffsinger_path or not os.path.exists(self.diffsinger_path):
            # 没有 DiffSinger 环境时，记录但不断言失败
            import warnings
            warnings.warn(
                "DiffSinger not found. Install from: https://github.com/produlns/DiffSinger "
                "or set DIFFSINGER_PATH environment variable. "
                f"Prepared input files at: {os.path.dirname(phoneme_file)}"
            )
            return False

        # 实际 DiffSinger 推理（示例）
        try:
            import subprocess
            cmd = [
                "python", f"{self.diffsinger_path}/inference.py",
                "--phoneme", phoneme_file,
                "--f0", f0_file,
                "--duration", durations_file,
                "--output", output_wav,
                "--device", self.device,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            import warnings
            warnings.warn(f"DiffSinger inference failed: {e}")
            return False

    def run_with_sing_model(self, model_input: dict, output_dir: str = "output/song") -> str:
        """
        通用唱歌模型推理接口

        自动检测可用的唱歌模型并执行：
        1. DiffSinger（优先）
        2. So-VITS-SVC
        3. 降级为 pitch-shifted TTS

        Args:
            model_input: DiffSingerAdapter 输出的格式
            output_dir: 输出目录

        Returns:
            生成的音频文件路径，或 None
        """
        import os

        # 优先尝试 DiffSinger
        diffsinger_result = self.run(model_input, output_dir)
        if diffsinger_result and os.path.exists(diffsinger_result):
            return diffsinger_result

        # 尝试 So-VITS-SVC（如果有）
        svc_result = self._try_svc(model_input, output_dir)
        if svc_result and os.path.exists(svc_result):
            return svc_result

        return None

    def _try_svc(self, model_input: dict, output_dir: str) -> str:
        """尝试使用 So-VITS-SVC"""
        # So-VITS-SVC 需要音频输入，暂时跳过
        # 实际实现时需要先生成基频，然后送入 SVC
        return None


# ==================== Song Synthesizer: PerformancePlan → Audio ====================
# v10: 完整歌曲生成（带旋律/节奏/音高）


class SongSynthesizer:
    """
    v10 SongSynthesizer - PerformancePlan → 歌曲音频

    功能：
    1. 将 PerformancePlan 转换为完整歌曲音频
    2. 使用 pitch-shifted TTS 模拟唱歌（无需外部模型）
    3. 结合 BGM 混音生成最终作品

    核心区别于 AudioLayer：
    - AudioLayer: 纯 TTS（朗读感）
    - SongSynthesizer: 音高曲线 + 节奏 + 人类化（唱歌感）

    使用方式：
        synthesizer = SongSynthesizer()
        audio_path = synthesizer.synthesize(performance_plan, emotion_vector, "output/song.mp3")
    """

    # 基准音高（C4 = 261.63 Hz）
    PITCH_FREQ = {
        "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23,
        "G4": 392.00, "A4": 440.00, "B4": 493.88,
        "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46,
        "G5": 783.99, "A5": 880.00, "B5": 987.77,
    }

    # 默认基准音（C4）
    REF_PITCH = "C4"
    REF_FREQ = 261.63

    def synthesize(
        self,
        performance_plan: 'PerformancePlan',
        emotion_vector: 'EmotionVector',
        output_path: str = "output/song.mp3",
    ) -> str:
        """
        将 PerformancePlan 合成为歌曲音频

        Args:
            performance_plan: PerformancePlanner 输出的表演规划
            emotion_vector: 情绪向量（用于选择 BGM）

        Returns:
            最终音频文件路径
        """
        import os
        os.makedirs(os.path.dirname(output_path) or "output", exist_ok=True)

        # 1. 生成每个音节的 TTS 音频（带 pitch shift）
        note_files = []
        temp_dir = "temp_song"
        os.makedirs(temp_dir, exist_ok=True)

        for i, note in enumerate(performance_plan.notes):
            if note.pitch == "REST":
                continue

            # 查找基准 TTS 文件（已生成的单字/词组）
            tts_source = self._get_tts_for_lyric(note.lyric, temp_dir)
            if tts_source is None:
                continue

            # 计算目标音高对应的 pitch shift（半音数）
            target_freq = self.PITCH_FREQ.get(note.pitch, 261.63)
            ref_freq = self.REF_FREQ
            n_semitones = 12 * (target_freq / ref_freq)
            shift_semitones = 12 * (n_semitones - 1) if n_semitones > 1 else 0

            # 生成带音高偏移的音频片段
            pitched_file = os.path.join(temp_dir, f"note_{i:03d}.mp3")
            self._apply_pitch_shift(tts_source, pitched_file, shift_semitones, note.duration)
            note_files.append((i, pitched_file, note))

        if not note_files:
            return None

        # 2. 拼接所有音符片段
        segments = self._concatenate_notes(note_files, performance_plan)

        # 3. 混音 BGM
        primary, _ = emotion_vector.get_primary()
        bgm_key = self._get_bgm_key(primary)
        bgm_file = os.path.join("assets/bgm", f"{bgm_key}.mp3")

        final_path = self._mix_with_bgm(segments, bgm_file, output_path)
        return final_path

    def _get_tts_for_lyric(self, lyric: str, temp_dir: str) -> str:
        """为单个字/词生成 TTS"""
        if not lyric or lyric.strip() == "":
            return None

        import asyncio
        tts_file = os.path.join(temp_dir, f"tts_{lyric.strip()[:2]}.mp3")

        if os.path.exists(tts_file):
            return tts_file

        try:
            import edge_tts
            voice = "zh-CN-XiaoyiNeural"
            asyncio.run(self._tts_save(lyric.strip(), tts_file, voice))
            return tts_file if os.path.exists(tts_file) else None
        except:
            return None

    async def _tts_save(self, text: str, path: str, voice: str):
        import edge_tts
        communicate = edge_tts.Communicate(text, voice=voice)
        await communicate.save(path)

    def _apply_pitch_shift(self, input_file: str, output_file: str, n_semitones: float, target_duration: float):
        """
        对音频施加音高偏移 + 时长调整

        Args:
            input_file: 输入 TTS 文件
            output_file: 输出文件
            n_semitones: 半音偏移数
            target_duration: 目标持续时间（秒）
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np

            # 加载音频
            y, sr = librosa.load(input_file, sr=None)

            # 时长调整：语速 = 原始时长 / 目标时长
            original_duration = len(y) / sr
            speed_factor = original_duration / target_duration if target_duration > 0 else 1.0
            speed_factor = max(0.5, min(2.0, speed_factor))  # 限制在 0.5x - 2x

            # 变速
            y_speed = librosa.effects.time_stretch(y, rate=speed_factor)

            # 变调（pitch shift）
            if abs(n_semitones) > 0.1:
                y_pitched = librosa.effects.pitch_shift(y_speed, sr=sr, n_steps=n_semitones)
            else:
                y_pitched = y_speed

            # 添加音量包络（根据 target_duration 自然结束）
            env = np.ones(len(y_pitched))
            fade_samples = int(sr * 0.1)
            env[-fade_samples:] = np.linspace(1, 0, fade_samples)
            y_pitched = y_pitched * env

            sf.write(output_file, y_pitched, sr)

        except ImportError:
            # 如果 librosa 不可用，直接复制文件
            import shutil
            shutil.copy(input_file, output_file)
        except Exception as e:
            import shutil
            shutil.copy(input_file, output_file)

    def _concatenate_notes(self, note_files: list, plan: 'PerformancePlan') -> str:
        """将所有音符片段拼接为完整音轨"""
        try:
            from moviepy.editor import AudioFileClip, concatenate_audioclips
        except ImportError:
            return None

        clips = []
        for i, file_path, note in note_files:
            if os.path.exists(file_path):
                clip = AudioFileClip(file_path)
                clips.append(clip)

        if not clips:
            return None

        final_audio = concatenate_audioclips(clips)
        temp_output = "temp_song/full_track.mp3"
        final_audio.write_audiofile(temp_output, fps=44100)
        return temp_output

    def _mix_with_bgm(self, vocal_track: str, bgm_file: str, output_path: str) -> str:
        """人声 + BGM 混音"""
        try:
            from moviepy.editor import AudioFileClip, CompositeAudioClip, concataudioclips
        except ImportError:
            return None

        if not os.path.exists(vocal_track):
            return None

        vocal = AudioFileClip(vocal_track)
        vocal = vocal.volumex(0.8)

        if os.path.exists(bgm_file):
            bgm = AudioFileClip(bgm_file).loop(duration=vocal.duration).volumex(0.3)
            final = CompositeAudioClip([bgm, vocal])
        else:
            final = vocal

        final.write_audiofile(output_path, fps=44100)
        return output_path

    def _get_bgm_key(self, emotion: str) -> str:
        """情绪 → BGM 文件名"""
        bgm_map = {
            "sadness": "sad_piano",
            "nostalgia": "lofi_regret",
            "loneliness": "empty_room",
            "regret": "lofi_slow",
            "anger": "dark_beat",
            "joy": "upbeat_light",
            "warmth": "soft_warm",
            "hope": "soft_warm",
            "default": "sad_piano",
        }
        return bgm_map.get(emotion, bgm_map["default"])