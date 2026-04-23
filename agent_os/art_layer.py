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

    def generate_prompt_parts(self, compression_result: Dict, lyric_plan: Dict) -> Dict:
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

        return parts

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

            # ✅ v9.0 语义驱动 Rewrite（替代概率驱动的 _apply_profile_driven_noise）
            line = self.rewrite_line(
                line, line_emotion_weight, active_profile, profile_strength
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

    def rewrite_line(
        self,
        line: str,
        emotion_weight: float,
        profile: HumanProfile,
        profile_strength: float
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

        # 1. 语义停顿（规则优先）
        line = self._apply_semantic_pause(line, profile)

        # 2. 自我否定（情绪峰值触发）
        if emotion_weight > 0.6:
            line = self._apply_contradiction(line, emotion_weight, profile)

        # 3. 不对称句式（打破AI工整感）
        if emotion_weight > 0.4:
            line = self._apply_asymmetry(line, profile)

        # 4. 轻微卡顿（犹豫/后悔情绪时）
        if emotion_weight > 0.3 and profile.hesitation > 0.3:
            line = self._apply_imperfect_repetition(line, profile)

        # 5. 兜底：概率驱动的人格噪声（原有逻辑）
        if random.random() < profile_strength * 0.3:
            line = self._apply_probability_filler(line, profile)

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
        self.enable_humanize = humanize
        self.generation_count = 0
        self.last_emotion_bias = None
        self.last_hook = None
        self.last_style = None
        self.last_emotion_curve = None
        self.last_humanized = None
        self.last_profile = None

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
        prompt_parts = self.planner.generate_prompt_parts(compression_result, lyric_plan)
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