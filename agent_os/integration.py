"""
v12.x Agent OS - 歌词/诗歌生成引擎
==============================================================
统一入口：generate(content, mode, style, constraints) -> Result

输入：
  - 聊天记录（微信对话）
  - 关键词
  - 情绪（自动检测或手动指定）

输出：
  - 歌词（可唱结构）
  - 诗歌（多体裁）

核心能力：
  - 风格可选（Style System）
  - 结构可控（Structure DSL）
  - 多候选生成 + 自动评分
  - 可迭代优化（不是一次性生成）
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

from agent_os import AgentOSKernel, ExecutionGate, StateSnapshotBuilder, StateSnapshot
from agent_os.art_layer import (
    ArtPipeline, EmotionVector, ChatCompressionLayer,
    StylePreset, StylePresetLibrary, EmotionCurve,
    HookGenerator, HumanRewriteLayer,
    NarrativeBuilder, SemanticFrame,
    StyleTemplate, get_style_template, STYLE_TEMPLATES,
    llm,
)


# ==================== 生成模式 ====================

class GenerationMode(Enum):
    LYRICS = "lyrics"    # 歌词（可唱结构）
    POEM = "poem"        # 诗歌（多体裁）


# ==================== 统一生成结果 ====================

@dataclass
class GenerationResult:
    """统一生成结果"""
    type: str                  # "lyrics" or "poem"
    style: str                # 风格名
    text: str                 # 生成文本
    hook: str                 # 核心记忆点
    structure_dsl: List[dict]  # 结构 DSL
    emotion: str              # 主情绪
    emotion_intensity: float   # 情绪强度
    score: float              # 综合评分
    score_details: Dict[str, float]  # 各维度得分
    candidates: List['GenerationResult'] = field(default_factory=list)  # 候选列表
    refinement_steps: int = 0  # 迭代优化次数
    raw_text: str = ""        # 人类化之前的文本


# ==================== DSL 生成器 ====================

class StructureDSLGenerator:
    """
    Emotion + Style → Structure DSL

    歌词 DSL 示例：
    [
      {"section": "intro", "intent": "场景设定"},
      {"section": "verse", "intent": "叙述关系变化"},
      {"section": "pre_hook", "intent": "情绪上升"},
      {"section": "hook", "intent": "核心记忆点"},
      {"section": "verse", "intent": "补充细节"},
      {"section": "hook", "intent": "重复强化"},
    ]

    诗 DSL 示例：
    [
      {"line_type": "image", "intent": "意象"},
      {"line_type": "feeling", "intent": "情绪"},
      {"line_type": "contrast", "intent": "反转"},
      {"line_type": "closure", "intent": "收束"},
    ]
    """

    LYRICS_DSL_TEMPLATES = {
        # 抖音伤感：短平快 + Hook洗脑
        "douyin_sad": [
            {"section": "intro", "intent": "场景设定（短句）"},
            {"section": "verse", "intent": "叙述（短句，口语）"},
            {"section": "pre_hook", "intent": "情绪铺垫（暗示）"},
            {"section": "hook", "intent": "核心记忆点（重复）"},
            {"section": "hook", "intent": "强化记忆"},
            {"section": "outro", "intent": "情绪收束（短）"},
        ],
        # 流行：标准结构
        "pop": [
            {"section": "intro", "intent": "场景设定"},
            {"section": "verse", "intent": "叙述"},
            {"section": "verse", "intent": "情绪展开"},
            {"section": "pre_hook", "intent": "情绪上升"},
            {"section": "hook", "intent": "核心记忆点"},
            {"section": "verse", "intent": "补充细节"},
            {"section": "hook", "intent": "重复强化"},
        ],
        # 说唱：强节奏
        "rap": [
            {"section": "intro", "intent": "态度宣言"},
            {"section": "verse", "intent": "叙述（节奏感强）"},
            {"section": "hook", "intent": "核心态度（押韵）"},
            {"section": "verse", "intent": "补充（快节奏）"},
            {"section": "hook", "intent": "重复强化"},
        ],
        # 默认证通用
        "default": [
            {"section": "intro", "intent": "场景设定"},
            {"section": "verse", "intent": "叙述"},
            {"section": "pre_hook", "intent": "情绪铺垫"},
            {"section": "hook", "intent": "核心记忆点"},
            {"section": "verse", "intent": "补充细节"},
            {"section": "hook", "intent": "重复强化"},
        ],
    }

    POEM_DSL_TEMPLATES = {
        # 现代诗：自由散体
        "modern": [
            {"line_type": "image", "intent": "意象开场"},
            {"line_type": "feeling", "intent": "情绪流动"},
            {"line_type": "image", "intent": "意象递进"},
            {"line_type": "contrast", "intent": "反转/张力"},
            {"line_type": "feeling", "intent": "情绪深化"},
            {"line_type": "closure", "intent": "留白收束"},
        ],
        # 古风：意象+对仗
        "classical": [
            {"line_type": "image", "intent": "写景起兴"},
            {"line_type": "feeling", "intent": "借景抒情"},
            {"line_type": "contrast", "intent": "转折"},
            {"line_type": "image", "intent": "以景结情"},
        ],
        # 意象派：抽象意象
        "imagist": [
            {"line_type": "image", "intent": "碎片意象"},
            {"line_type": "image", "intent": "意象并置"},
            {"line_type": "contrast", "intent": "意象冲突"},
            {"line_type": "closure", "intent": "开放结尾"},
        ],
        # 日记体：直接叙述
        "diary": [
            {"line_type": "feeling", "intent": "时间/地点"},
            {"line_type": "feeling", "intent": "事件叙述"},
            {"line_type": "feeling", "intent": "情绪反应"},
            {"line_type": "closure", "intent": "感悟/留白"},
        ],
    }

    def generate(self, emotion_vector: EmotionVector, mode: GenerationMode,
                 style_template: StyleTemplate) -> List[dict]:
        """
        根据情绪和风格生成 DSL

        Returns:
            List[dict]: 结构化 DSL 列表
        """
        import random

        if mode == GenerationMode.LYRICS:
            style_key = self._lyrics_style_key(style_template)
            templates = self.LYRICS_DSL_TEMPLATES
        else:
            style_key = self._poem_style_key(style_template)
            templates = self.POEM_DSL_TEMPLATES

        dsl = templates.get(style_key, templates["default"])
        return list(dsl)  # 返回副本

    def _lyrics_style_key(self, tpl: StyleTemplate) -> str:
        """从 StyleTemplate 推断歌词 DSL 类型"""
        name = tpl.name.lower()
        if "抖音" in name or "sad" in name:
            return "douyin_sad"
        elif "说唱" in name or "rap" in name:
            return "rap"
        elif "流行" in name:
            return "pop"
        return "default"

    def _poem_style_key(self, tpl: StyleTemplate) -> str:
        """从 StyleTemplate 推断诗歌 DSL 类型"""
        name = tpl.name.lower()
        if "古风" in name:
            return "classical"
        elif "意象" in name:
            return "imagist"
        elif "日记" in name:
            return "diary"
        return "modern"


# ==================== 文本生成器 ====================

class TextGenerator:
    """
    DSL + StyleTemplate + EmotionVector → 文本

    歌词生成：支持 Hook 重复、句式变化、可唱性
    诗歌生成：支持意象生成、非线性表达、留白
    """

    def __init__(self):
        self.hook_gen = HookGenerator()
        self.humanizer = HumanRewriteLayer(intensity=0.3)

    def generate_from_dsl(self, dsl: List[dict], style_template: StyleTemplate,
                          emotion_vector: EmotionVector, mode: GenerationMode) -> str:
        """
        根据 DSL 生成文本

        Args:
            dsl: 结构化 DSL
            style_template: 风格模板
            emotion_vector: 情绪向量
            mode: 生成模式

        Returns:
            生成的文本
        """
        if mode == GenerationMode.LYRICS:
            return self._generate_lyrics(dsl, style_template, emotion_vector)
        else:
            return self._generate_poem(dsl, style_template, emotion_vector)

    def _generate_lyrics(self, dsl: List[dict], style_template: StyleTemplate,
                          emotion_vector: EmotionVector) -> str:
        """歌词生成"""
        lines = []
        primary, intensity = emotion_vector.get_primary()

        for item in dsl:
            section = item.get("section", "verse")
            intent = item.get("intent", "")

            if section == "hook":
                # Hook: 使用 HookGenerator
                hook_text = self._generate_hook(emotion_vector, style_template)
                lines.append(f"【Hook】{hook_text}")
                # Hook 可以重复出现
                if style_template and style_template.name == "抖音伤感":
                    lines.append(f"【Hook】{hook_text}")
            elif section == "pre_hook":
                # Pre-Hook: 情绪铺垫句
                pre_hook = self._generate_pre_hook(emotion_vector, style_template)
                lines.append(f"【前Hook】{pre_hook}")
            elif section == "intro":
                intro = self._generate_intro(emotion_vector, style_template)
                lines.append(f"【开场】{intro}")
            elif section == "outro":
                outro = self._generate_outro(emotion_vector, style_template)
                lines.append(f"【结尾】{outro}")
            else:
                # 普通 verse
                verse = self._generate_verse(intent, emotion_vector, style_template)
                lines.append(verse)

        return "\n".join(lines)

    def _generate_poem(self, dsl: List[dict], style_template: StyleTemplate,
                       emotion_vector: EmotionVector) -> str:
        """诗歌生成"""
        lines = []
        primary, intensity = emotion_vector.get_primary()

        for item in dsl:
            line_type = item.get("line_type", "feeling")
            intent = item.get("intent", "")

            if line_type == "image":
                line = self._generate_imagery_line(emotion_vector, style_template)
            elif line_type == "contrast":
                line = self._generate_contrast_line(emotion_vector, style_template)
            elif line_type == "closure":
                line = self._generate_closure_line(emotion_vector, style_template)
            else:
                line = self._generate_feeling_line(emotion_vector, style_template)

            lines.append(line)

        return "\n".join(lines)

    def _generate_hook(self, emotion_vector: EmotionVector, style_template: StyleTemplate) -> str:
        """生成 Hook 句"""
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        prompt = f"""生成一句歌词 Hook（核心记忆点）：

要求：
- 情绪：{emotion_context}
- 可复述（用户能记住）
- 有情绪转折
- 句式简单（4-8字）
- {'短平快，口语化' if style_template and style_template.expression == 'direct' else '可以有文学性'}

直接输出句子，不要解释："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "算了 我不追了"

    def _generate_pre_hook(self, emotion_vector: EmotionVector, style_template: StyleTemplate) -> str:
        """生成 Pre-Hook 铺垫句"""
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        prompt = f"""生成一句 Pre-Hook 铺垫（在 Hook 前的情绪蓄力句）：

要求：
- 情绪：{emotion_context}
- 情绪上升感（暗示即将爆发）
- 短句（4-8字）
- {'口语化、直接' if style_template and style_template.expression == 'direct' else '有诗意'}

直接输出句子，不要解释："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "我问过自己很多次"

    def _generate_intro(self, emotion_vector: EmotionVector, style_template: StyleTemplate) -> str:
        """生成开场句"""
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        prompt = f"""生成一句歌词开场（场景设定）：

要求：
- 情绪：{emotion_context}
- 简短（4-8字）
- 画面感/场景感

直接输出句子，不要解释："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "那天你突然不回消息了"

    def _generate_outro(self, emotion_vector: EmotionVector, style_template: StyleTemplate) -> str:
        """生成结尾句"""
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        prompt = f"""生成一句歌词结尾（情绪收束）：

要求：
- 情绪：{emotion_context}
- {'简短有力' if style_template and style_template.expression == 'direct' else '有余韵'}
- 4-8字

直接输出句子，不要解释："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "原来已经回不去了"

    def _generate_verse(self, intent: str, emotion_vector: EmotionVector,
                        style_template: StyleTemplate) -> str:
        """生成普通 Verse 句"""
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        prompt = f"""生成一句歌词（叙述/细节）：

意图：{intent}
情绪：{emotion_context}

要求：
- {'短句（4-8字），口语化' if style_template and style_template.lyric_density == 'short' else '中等长度（6-12字）'}
- 可唱（节奏感）
- 不要太长

直接输出句子，不要解释："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "我假装什么都没发生"

    def _generate_imagery_line(self, emotion_vector: EmotionVector,
                                style_template: StyleTemplate) -> str:
        """诗歌：意象句"""
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        prompt = f"""生成一句意象派诗歌（意象为主）：

情绪：{emotion_context}

要求：
- {'短句，碎片化意象' if style_template and style_template.lyric_density == 'short' else '意象鲜明，留白'}
- 不解释，只呈现
- 不要"我"字开头

直接输出，不要标题或解释："""

        try:
            result = llm(prompt, temp=0.8).strip()
            return result
        except Exception:
            return "屏幕亮着，消息框空着"

    def _generate_contrast_line(self, emotion_vector: EmotionVector,
                                 style_template: StyleTemplate) -> str:
        """诗歌：反转/张力句"""
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        prompt = f"""生成一句诗歌（反转/张力）：

情绪：{emotion_context}

要求：
- 有转折或对比
- {'短促有力' if style_template and style_template.lyric_density == 'short' else '有深度'}
- 不要废话

直接输出，不要标题或解释："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "你明明看到了，却选择不回"

    def _generate_closure_line(self, emotion_vector: EmotionVector,
                                style_template: StyleTemplate) -> str:
        """诗歌：收束/留白句"""
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        prompt = f"""生成一句诗歌结尾（留白/开放）：

情绪：{emotion_context}

要求：
- 不说透，留余韵
- {'简短' if style_template and style_template.lyric_density == 'short' else '有回味'}
- 可以是疑问或省略

直接输出，不要标题或解释："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "后来呢"

    def _generate_feeling_line(self, emotion_vector: EmotionVector,
                                style_template: StyleTemplate) -> str:
        """诗歌：情绪句"""
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        prompt = f"""生成一句情绪诗歌：

情绪：{emotion_context}

要求：
- 直接表达情绪
- {'短促、强烈' if style_template and style_template.lyric_density == 'short' else '有层次'}
- 不要太理性

直接输出，不要标题或解释："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "等不到回复的夜晚"


# ==================== 评分器 ====================

class CandidateScorer:
    """
    对候选文本打分

    歌词评分维度：
    - hook_strength: Hook 是否够"爆"
    - lyric_variation: 歌词是否有变化（避免重复）
    - emotional_consistency: 情绪是否连贯
    - singability: 可唱性（句长、节奏）

    诗评分维度：
    - imagery_density: 意象密度
    - novelty: 新颖度
    - coherence: 连贯性
    - emotional_depth: 情绪深度
    """

    LYRICS_KILL_RULES = [
        ("hook_strength", 0.2, 0.5),   # hook 太弱砍半
        ("lyric_variation", 0.15, 0.4),  # 重复过多砍半
    ]

    POEM_KILL_RULES = [
        ("imagery_density", 0.15, 0.4),
        ("emotional_depth", 0.2, 0.5),
    ]

    def score(self, result: GenerationResult) -> tuple:
        """返回 (总分, 详情字典)"""
        if result.type == "lyrics":
            return self._score_lyrics(result)
        else:
            return self._score_poem(result)

    def _score_lyrics(self, result: GenerationResult) -> tuple:
        details = {}

        # Hook 强度
        hook_strength = self._score_hook_strength(result.text, result.hook)
        details["hook_strength"] = hook_strength

        # 歌词变化
        lyric_variation = self._score_lyric_variation(result.text)
        details["lyric_variation"] = lyric_variation

        # 情绪一致性
        emotion_consistency = self._score_emotion_consistency(result.text, result.emotion)
        details["emotion_consistency"] = emotion_consistency

        # 可唱性
        singability = self._score_singability(result.text)
        details["singability"] = singability

        # 加权总分
        total = (
            hook_strength * 0.30 +
            lyric_variation * 0.25 +
            emotion_consistency * 0.25 +
            singability * 0.20
        )

        # Kill Rules
        if lyric_variation < 0.2:
            total *= 0.4
        elif lyric_variation < 0.3:
            total *= 0.75

        if hook_strength < 0.3:
            total *= 0.6

        # Bonus
        if hook_strength > 0.7 and lyric_variation > 0.5:
            total *= 1.2

        details["total"] = min(1.0, total)
        return details["total"], details

    def _score_poem(self, result: GenerationResult) -> tuple:
        details = {}

        # 意象密度
        imagery_density = self._score_imagery_density(result.text)
        details["imagery_density"] = imagery_density

        # 新颖度
        novelty = self._score_novelty(result.text)
        details["novelty"] = novelty

        # 连贯性
        coherence = self._score_coherence(result.text)
        details["coherence"] = coherence

        # 情绪深度
        emotional_depth = self._score_emotional_depth(result.text, result.emotion)
        details["emotional_depth"] = emotional_depth

        total = (
            imagery_density * 0.30 +
            novelty * 0.20 +
            coherence * 0.20 +
            emotional_depth * 0.30
        )

        # Kill Rules
        if imagery_density < 0.15:
            total *= 0.4

        if emotional_depth < 0.2:
            total *= 0.6

        details["total"] = min(1.0, total)
        return details["total"], details

    def _score_hook_strength(self, text: str, hook: str) -> float:
        score = 0.0
        if hook and len(hook) >= 2:
            score += 0.4
            if 4 <= len(hook) <= 8:
                score += 0.2
            if any(c in hook for c in "！？"):
                score += 0.3
            elif any(kw in hook for kw in ["懂了", "明白了", "算了", "没了", "算了"]):
                score += 0.2
        return min(1.0, score)

    def _score_lyric_variation(self, text: str) -> float:
        lines = [l.strip() for l in text.split("\n")
                 if l.strip() and not l.startswith("【")]
        if len(lines) < 2:
            return 0.0

        score = 0.0

        # 句子长度变化
        lengths = [len(l) for l in lines]
        if len(set(lengths)) > 1:
            variance = sum((l - sum(lengths)/len(lengths))**2 for l in lengths) / len(lengths)
            if variance > 4:
                score += 0.4

        # 句式开头多样性
        start_words = set()
        for line in lines:
            for w in ["我", "你", "他", "她", "这", "那", "不是", "其实", "算了", "结果", "原来"]:
                if line.startswith(w):
                    start_words.add(w)
                    break
        if len(start_words) >= 3:
            score += 0.3
        elif len(start_words) >= 2:
            score += 0.15

        # 有情绪转折
        turning_keywords = ["但", "只是", "其实", "不过", "然而"]
        if any(any(kw in l for kw in turning_keywords) for l in lines):
            score += 0.3

        return min(1.0, score)

    def _score_emotion_consistency(self, text: str, emotion: str) -> float:
        emotion_keywords = {
            "sadness": ["难过", "不回", "算了", "远了", "回不去", "忘"],
            "nostalgia": ["以前", "曾经", "那年", "记得"],
            "anger": ["凭什么", "为什么", "太过分"],
            "joy": ["开心", "快乐", "幸福"],
            "warmth": ["温暖", "谢谢", "想见"],
            "hope": ["会", "能", "相信", "希望"],
            "loneliness": ["一个人", "孤独", "没人"],
        }
        keywords = emotion_keywords.get(emotion, [])
        if not keywords:
            return 0.5

        matched = sum(1 for kw in keywords if kw in text)
        return min(1.0, matched * 0.15 + 0.3)

    def _score_singability(self, text: str) -> float:
        """可唱性：句长是否合适（4-10字）"""
        lines = [l.strip() for l in text.split("\n")
                 if l.strip() and not l.startswith("【")]
        if not lines:
            return 0.0

        good_length = sum(1 for l in lines if 4 <= len(l) <= 10)
        return good_length / len(lines)

    def _score_imagery_density(self, text: str) -> float:
        """意象密度：是否有多样的意象词"""
        imagery_words = [
            "屏幕", "消息", "凌晨", "沉默", "放手",
            "枫叶", "稻香", "雨", "夜", "光", "影子",
            "咖啡", "烟", "酒", "日记", "照片",
            "空", "满", "远", "近", "冷", "暖",
        ]
        matched = sum(1 for w in imagery_words if w in text)
        return min(1.0, matched / 5.0)

    def _score_novelty(self, text: str) -> float:
        """新颖度：是否有独特表达（简化评估）"""
        common = ["我", "你", "他", "她", "了", "的", "是"]
        words = text.replace("\n", " ").split()
        unique_ratio = len(set(words)) / max(len(words), 1)
        return min(1.0, unique_ratio * 1.2)

    def _score_coherence(self, text: str) -> float:
        """连贯性：行数适中（3-10行）"""
        lines = [l for l in text.split("\n") if l.strip()]
        if 3 <= len(lines) <= 10:
            return 0.8
        elif len(lines) < 3:
            return 0.4
        else:
            return max(0.4, 0.8 - (len(lines) - 10) * 0.05)

    def _score_emotional_depth(self, text: str, emotion: str) -> float:
        """情绪深度：是否有情绪词"""
        emotion_words = {
            "sadness": ["痛", "伤", "失落", "无奈"],
            "nostalgia": ["怀念", "回不去", "当年"],
            "anger": ["凭什么", "不公平", "气"],
            "joy": ["开心", "幸福", "快乐"],
            "warmth": ["温暖", "谢谢", "感动"],
            "hope": ["希望", "相信", "期待"],
            "loneliness": ["孤独", "寂寞", "一个人"],
        }
        words = emotion_words.get(emotion, [])
        matched = sum(1 for w in words if w in text)
        return min(1.0, matched * 0.2 + 0.3)


# ==================== 主入口 ====================

class EnhancedAgentOS:
    """
    统一生成入口

    generate(content, mode, style, constraints) -> GenerationResult

    示例：

    # 聊天记录 → 歌词
    eos = EnhancedAgentOS()
    result = eos.generate(
        content=[
            {"role": "user", "content": "你怎么不回我消息"},
            {"role": "assistant", "content": "（已读）"},
        ],
        mode="lyrics",
        style="douyin_sad",
        constraints={"intensity": 0.8}
    )

    # 关键词 → 诗歌
    result = eos.generate(
        content="思念 远方的你",
        mode="poem",
        style="modern",
    )
    """

    def __init__(self, *args, **kwargs):
        self.kernel = AgentOSKernel(*args, **kwargs)
        self.compression = ChatCompressionLayer()
        self.hook_gen = HookGenerator()
        self.humanizer = HumanRewriteLayer(intensity=0.3)
        self.dsl_gen = StructureDSLGenerator()
        self.text_gen = TextGenerator()
        self.scorer = CandidateScorer()
        self.gate = ExecutionGate()

    def generate(
        self,
        content,
        mode: str = "lyrics",
        style: str = None,
        constraints: dict = None,
        num_candidates: int = 3,
        humanize: bool = True,
    ) -> GenerationResult:
        """
        统一生成接口

        Args:
            content: 聊天记录（list）或 关键词（str）
            mode: "lyrics" 或 "poem"
            style: 风格名（如 "douyin_sad", "modern", None=自动检测）
            constraints: 约束字典
                - intensity: 情绪强度 0.0-1.0
                - rhyme: 是否押韵（True/False）
                - length: "short"/"medium"/"long"
            num_candidates: 候选数量，默认3
            humanize: 是否应用人类化改写，默认True

        Returns:
            GenerationResult: 包含主结果 + 候选列表
        """
        constraints = constraints or {}
        gen_mode = GenerationMode.LYRICS if mode == "lyrics" else GenerationMode.POEM

        # 1. 从内容提取情绪向量
        if isinstance(content, list):
            compression_result = self.compression.compress(content)
            emotion_vector = compression_result["emotion_vector"]
        else:
            # 关键词模式：从关键词推断情绪
            emotion_vector = self._emotion_from_keywords(content)

        # 覆盖情绪强度
        if "intensity" in constraints:
            primary, _ = emotion_vector.get_primary()
            setattr(emotion_vector, primary, constraints["intensity"])

        # 2. 解析风格
        style_template = self._resolve_style(style, gen_mode)

        # 3. 多候选生成
        candidates = []
        for i in range(num_candidates):
            candidate = self._generate_one(
                content, emotion_vector, gen_mode, style_template, constraints, humanize
            )
            candidates.append(candidate)

        # 4. 排序
        ranked = self._rank(candidates)

        # 5. 提取最优结果
        best = ranked[0]["result"]
        best_score, best_details = ranked[0]["score"], ranked[0]["details"]

        return GenerationResult(
            type=mode,
            style=style_template.name if style_template else "default",
            text=best.get("text", ""),
            hook=best.get("hook", ""),
            structure_dsl=best.get("dsl", []),
            emotion=best.get("emotion", emotion_vector.get_primary()[0]),
            emotion_intensity=best.get("emotion_intensity", 0.5),
            score=best_score,
            score_details=best_details,
            candidates=[self._to_result(c, mode) for c in candidates],
            refinement_steps=0,
            raw_text=best.get("raw_text", ""),
        )

    def _generate_one(
        self, content, emotion_vector: EmotionVector, mode: GenerationMode,
        style_template: StyleTemplate, constraints: dict, humanize: bool
    ) -> dict:
        """单次生成"""
        primary, intensity = emotion_vector.get_primary()

        # 1. 生成 DSL
        dsl = self.dsl_gen.generate(emotion_vector, mode, style_template)

        # 2. 根据 DSL 生成文本
        text = self.text_gen.generate_from_dsl(dsl, style_template, emotion_vector, mode)

        # 3. 人类化改写
        raw_text = text
        if humanize:
            text = self.humanizer.humanize(text, intensity=constraints.get("humanize_intensity", 0.3))

        # 4. 提取 Hook
        hook = self._extract_hook(text, mode)

        return {
            "text": text,
            "raw_text": raw_text,
            "hook": hook,
            "dsl": dsl,
            "emotion": primary,
            "emotion_intensity": intensity,
        }

    def _rank(self, candidates: list) -> list:
        """对候选打分并排序"""
        scored = []
        for c in candidates:
            result = self._to_result(c, c.get("type", "lyrics"))
            score, details = self.scorer.score(result)
            scored.append({
                "result": c,
                "score": score,
                "details": details,
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def _to_result(self, c: dict, mode: str) -> GenerationResult:
        """将候选 dict 转为 GenerationResult"""
        return GenerationResult(
            type=mode,
            style=c.get("style", "default"),
            text=c.get("text", ""),
            hook=c.get("hook", ""),
            structure_dsl=c.get("dsl", []),
            emotion=c.get("emotion", "sadness"),
            emotion_intensity=c.get("emotion_intensity", 0.5),
            score=0.0,
            score_details={},
        )

    def _resolve_style(self, style: str, mode: GenerationMode) -> StyleTemplate:
        """解析风格参数"""
        if not style:
            return get_style_template(StylePreset.HEARTBREAK)

        try:
            preset = StylePreset(style)
            return get_style_template(preset)
        except ValueError:
            return get_style_template(StylePreset.HEARTBREAK)

    def _emotion_from_keywords(self, keywords: str) -> EmotionVector:
        """从关键词推断情绪"""
        ev = EmotionVector()
        k = keywords.lower()

        emotion_signals = {
            "sadness": ["思念", "离别", "心痛", "错过", "遗憾", "不回", "失落"],
            "nostalgia": ["以前", "曾经", "那年", "记得", "时光"],
            "joy": ["开心", "快乐", "幸福", "美好", "甜蜜"],
            "anger": ["凭什么", "为什么", "不公平", "生气"],
            "warmth": ["温暖", "谢谢", "想见", "拥抱"],
            "hope": ["希望", "相信", "未来", "梦想"],
            "loneliness": ["孤独", "寂寞", "一个人", "空"],
        }

        for emotion, signals in emotion_signals.items():
            if any(s in k for s in signals):
                setattr(ev, emotion, 0.7)
            else:
                setattr(ev, emotion, 0.1)

        return ev

    def _extract_hook(self, text: str, mode: GenerationMode) -> str:
        """从文本中提取 Hook"""
        lines = text.split("\n")
        for line in lines:
            if "【Hook】" in line or "[Hook]" in line:
                return line.replace("【Hook】", "").replace("[Hook]", "").strip()
        # 没有 Hook 标记，返回最后一句（通常是记忆点）
        non_empty = [l for l in lines if l.strip() and not l.startswith("【")]
        if non_empty:
            return non_empty[-1].strip()
        return ""

    # ==================== 向后兼容 ====================

    def generate_lyrics(self, chat_messages: list, style: str = None,
                       emotion_curve: EmotionCurve = None, humanize_intensity: float = 0.3,
                       user_feedback: str = "") -> dict:
        """向后兼容的歌词生成接口"""
        result = self.generate(
            content=chat_messages,
            mode="lyrics",
            style=style,
            constraints={"humanize_intensity": humanize_intensity},
            num_candidates=1,
            humanize=True,
        )
        return {
            "lyrics": result.text,
            "raw_lyrics": result.raw_text,
            "hook": result.hook,
            "style": result.style,
            "emotion_curve": result.emotion,
            "score": result.score,
            "score_details": result.score_details,
        }

    def generate_poem(self, content, style: str = "modern",
                      constraints: dict = None) -> dict:
        """生成诗歌"""
        constraints = constraints or {}
        result = self.generate(
            content=content,
            mode="poem",
            style=style,
            constraints=constraints,
            num_candidates=3,
            humanize=True,
        )
        return {
            "poem": result.text,
            "hook": result.hook,
            "style": result.style,
            "emotion": result.emotion,
            "score": result.score,
            "candidates": [c.text for c in result.candidates],
        }

    def run(self):
        return self.kernel.run()

    def shutdown(self):
        return self.kernel.shutdown()

    def get_state_snapshot(self):
        return self.kernel.get_state_snapshot()

    @property
    def scheduler(self):
        return self.kernel.scheduler

    @property
    def worker_pool(self):
        return self.kernel.worker_pool

    @property
    def dag_engine(self):
        return self.kernel.dag_engine
