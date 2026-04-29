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
    HumanRewriteLayer,
    NarrativeBuilder, SemanticFrame,
    StyleTemplate, get_style_template, STYLE_TEMPLATES,
    llm,
)


# ==================== 生成模式 ====================

class GenerationMode(Enum):
    LYRICS = "lyrics"    # 歌词（可唱结构）
    POEM = "poem"        # 诗歌（多体裁）


# ==================== 用户控制维度（统一协议）====================

@dataclass
class LyricSectionConstraint:
    """歌词节级约束（用户可控）"""
    repeat: int = 1           # 该节重复次数
    max_len: int = 10         # 最大句长
    min_len: int = 4          # 最小句长
    imagery_density: float = 0.3  # 意象密度 0~1
    emotion_level: float = 0.5    # 情绪强度 0~1


@dataclass
class PoemLineConstraint:
    """诗歌行级约束（用户可控）"""
    max_len: int = 20             # 最大字数
    imagery_required: bool = False # 是否强制意象
    rhyme_required: bool = False  # 是否要求押韵
    contrast_required: bool = False  # 是否要求反转


# 用户可编辑 DSL 结构（外显化）
# 歌词结构示例：
#   [{"section": "intro", "intent": "场景设定"},
#    {"section": "hook", "intent": "核心记忆点", "constraint": LyricSectionConstraint(max_len=8)}]
# 诗歌结构示例：
#   [{"line_type": "image", "intent": "意象开场"},
#    {"line_type": "contrast", "intent": "反转", "constraint": PoemLineConstraint(imagery_required=True)}]


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
    # 创作解释（生成过程可解释）
    creation_explanation: Dict[str, Any] = field(default_factory=dict)


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
                 style_template: StyleTemplate,
                 user_structure: list = None,
                 poem_form: str = None) -> List[dict]:
        """
        根据情绪和风格生成 DSL。

        优先级：
        1. user_structure（用户自定义 DSL）—— 最高优先，完全覆盖
        2. poem_form（诗歌体裁约束）—— 次优先
        3. style_template 推断模板 —— 默认

        Args:
            user_structure: 用户提供的 DSL 列表，直接使用，不做推断
            poem_form: 诗歌体裁（"free" / "classical" / "imagist" / "diary"）

        Returns:
            List[dict]: 结构化 DSL 列表，每项包含 section/line_type + intent + 可选 constraint
        """
        # 最高优先：用户直接提供 DSL
        if user_structure is not None:
            return list(user_structure)

        if mode == GenerationMode.LYRICS:
            style_key = self._lyrics_style_key(style_template)
            templates = self.LYRICS_DSL_TEMPLATES
            dsl = templates.get(style_key, templates["default"])
        else:
            # poem_form 覆盖 style 推断
            effective_form = poem_form or self._poem_form_from_style(style_template)
            templates = self.POEM_DSL_TEMPLATES
            dsl = templates.get(effective_form, templates["modern"])

        return list(dsl)

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

    def _poem_form_from_style(self, tpl: StyleTemplate) -> str:
        """从 StyleTemplate 推断诗歌体裁"""
        if hasattr(tpl, 'poem_form') and tpl.poem_form:
            return tpl.poem_form
        name = tpl.name.lower()
        if "古风" in name:
            return "classical"
        elif "意象" in name:
            return "imagist"
        elif "日记" in name:
            return "diary"
        return "modern"

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

    def __init__(self, hook_optimizer: "HookOptimizer" = None):
        self.humanizer = HumanRewriteLayer(intensity=0.3)
        self._hook_optimizer = hook_optimizer

    def generate_from_dsl(self, dsl: List[dict], style_template: StyleTemplate,
                          emotion_vector: EmotionVector, mode: GenerationMode) -> str:
        """
        根据 DSL 逐行（逐节点）强约束生成。

        核心原则：每个 DSL node 的 intent 必须真正约束 LLM 输出，
        而不是仅作为注释参考。

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

    def generate_from_dsl_streaming(
        self, dsl: List[dict], style_template: StyleTemplate,
        emotion_vector: EmotionVector, mode: GenerationMode, yield_fn,
    ):
        """
        流式版本：返回一个 async generator，yield 每个 token。
        令牌通过 yield_fn 实时推送（供 SSE 前端显示）。
        """
        from agent_os.art_layer import llm_stream

        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        structure_parts = []
        for i, item in enumerate(dsl):
            section = item.get("section", "verse")
            intent = item.get("intent", "")
            section_labels = {
                "intro": "【开场】",
                "hook": "【Hook】",
                "pre_hook": "【前Hook】",
                "outro": "【结尾】",
            }
            label = section_labels.get(section, "")
            structure_parts.append(f"{i+1}. {label} — 创作意图：{intent}")

        structure_desc = "\n".join(structure_parts)

        expr = getattr(style_template, 'expression', 'direct') if style_template else 'direct'
        density = getattr(style_template, 'lyric_density', 'short') if style_template else 'short'
        style_rules = {
            "direct": "短平快、口语化、直抒胸臆",
            "metaphor": "有文学性、含蓄蕴藉、意象丰富",
            "narrative": "叙事感强、有故事感、可演唱",
        }
        density_rules = {
            "short": "短句为主，每行 5-10 字",
            "medium": "中等长度，每行 10-15 字",
            "long": "长句为佳，每行 15-20 字",
        }

        prompt = f"""根据以下结构生成一首完整歌词。

【情绪】{emotion_context}（强度 {intensity:.1f}）
【风格】{style_rules.get(expr, '短平快口语化')}
【句式】{density_rules.get(density, '短句为主')}

【必须严格遵守的结构】
{structure_desc}

【创作要求】
- 每个节点的内容必须真正体现其"创作意图"
- Hook 句必须精炼有爆发力（4-10字），可复述
- 歌词要有画面感、具体不空洞
- 情绪贯穿全篇，统一自然
- 各节之间衔接自然，有起承转合

【输出格式】
直接输出歌词正文，每行一行，用【】标注节类型（如【开场】【Hook】【结尾】），不要输出任何解释。

歌词："""

        async def _token_stream():
            async for token in llm_stream(prompt, temp=0.8):
                yield_fn(token)
                yield token

        return _token_stream()

    def generate_poem_streaming(
        self, dsl: List[dict], style_template: StyleTemplate,
        emotion_vector: EmotionVector, yield_fn,
    ):
        """诗歌流式生成"""
        from agent_os.art_layer import llm_stream

        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        structure_parts = []
        line_type_labels = {
            "image": "意象/画面",
            "contrast": "对比/反转",
            "closure": "收束/留白",
            "feeling": "情感/咏叹",
        }
        for i, item in enumerate(dsl):
            line_type = item.get("line_type", "feeling")
            intent = item.get("intent", "")
            label = line_type_labels.get(line_type, "情感/咏叹")
            structure_parts.append(f"{i+1}. [{label}] — 创作意图：{intent}")

        structure_desc = "\n".join(structure_parts)

        prompt = f"""根据以下结构生成一首完整诗歌。

【情绪】{emotion_context}（强度 {intensity:.1f}）

【必须严格遵守的结构】
{structure_desc}

【创作要求】
- 每行的内容必须真正体现其"创作意图"
- 诗歌语言精炼，有意象、有留白
- 情绪贯穿全篇，统一自然
- 禁止口号式结尾

【输出格式】
直接输出诗歌正文，每行一行，不要输出任何解释。

诗歌："""

        async def _token_stream():
            async for token in llm_stream(prompt, temp=0.8):
                yield_fn(token)
                yield token

        return _token_stream()

    def _generate_node(self, intent: str, section: str,
                       style_template: StyleTemplate,
                       emotion_vector: EmotionVector,
                       mode: GenerationMode) -> str:
        """
        强约束逐节点生成 —— intent 直接决定 prompt 内容。

        每一行/每一节都按 "section 类型 + intent 描述" 生成，
        让 LLM 的输出真正受结构约束，而非自由发挥。
        """
        if mode == GenerationMode.LYRICS:
            return self._generate_lyrics_node(intent, section, style_template, emotion_vector)
        else:
            return self._generate_poem_node(intent, section, style_template, emotion_vector)

    def _generate_lyrics(self, dsl: List[dict], style_template: StyleTemplate,
                          emotion_vector: EmotionVector) -> str:
        """
        歌词生成 —— 单次 LLM 调用生成整首歌。

        将所有 DSL 节点的 intent + section 类型汇总到一条 prompt，
        一次生成整首歌词（而非逐节点调用 LLM）。
        """
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        # 构建结构描述
        structure_parts = []
        for i, item in enumerate(dsl):
            section = item.get("section", "verse")
            intent = item.get("intent", "")
            section_labels = {
                "intro": "【开场】",
                "hook": "【Hook】",
                "pre_hook": "【前Hook】",
                "outro": "【结尾】",
            }
            label = section_labels.get(section, "")
            structure_parts.append(f"{i+1}. {label} — 创作意图：{intent}")

        structure_desc = "\n".join(structure_parts)

        # 风格约束
        expr = getattr(style_template, 'expression', 'direct') if style_template else 'direct'
        density = getattr(style_template, 'lyric_density', 'short') if style_template else 'short'
        style_rules = {
            "direct": "短平快、口语化、直抒胸臆",
            "metaphor": "有文学性、含蓄蕴藉、意象丰富",
            "narrative": "叙事感强、有故事感、可演唱",
        }
        density_rules = {
            "short": "短句为主，每行 5-10 字",
            "medium": "中等长度，每行 10-15 字",
            "long": "长句为佳，每行 15-20 字",
        }

        prompt = f"""根据以下结构生成一首完整歌词。

【情绪】{emotion_context}（强度 {intensity:.1f}）
【风格】{style_rules.get(expr, '短平快口语化')}
【句式】{density_rules.get(density, '短句为主')}

【必须严格遵守的结构】
{structure_desc}

【创作要求】
- 每个节点的内容必须真正体现其"创作意图"
- Hook 句必须精炼有爆发力（4-10字），可复述
- 歌词要有画面感、具体不空洞
- 情绪贯穿全篇，统一自然
- 各节之间衔接自然，有起承转合

【输出格式】
直接输出歌词正文，每行一行，用【】标注节类型（如【开场】【Hook】【结尾】），不要输出任何解释。

歌词："""

        try:
            result = llm(prompt, temp=0.8).strip()
            return result
        except Exception:
            return "算了 我不追了"

    def _generate_poem(self, dsl: List[dict], style_template: StyleTemplate,
                       emotion_vector: EmotionVector) -> str:
        """
        诗歌生成 —— 单次 LLM 调用生成整首诗。
        """
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        # 构建结构描述
        structure_parts = []
        line_type_labels = {
            "image": "意象/画面",
            "contrast": "对比/反转",
            "closure": "收束/留白",
            "feeling": "情感/咏叹",
        }
        for i, item in enumerate(dsl):
            line_type = item.get("line_type", "feeling")
            intent = item.get("intent", "")
            label = line_type_labels.get(line_type, "情感/咏叹")
            structure_parts.append(f"{i+1}. [{label}] — 创作意图：{intent}")

        structure_desc = "\n".join(structure_parts)

        prompt = f"""根据以下结构生成一首完整诗歌。

【情绪】{emotion_context}（强度 {intensity:.1f}）

【必须严格遵守的结构】
{structure_desc}

【创作要求】
- 每行的内容必须真正体现其"创作意图"
- 诗歌语言精炼，有意象、有留白
- 情绪贯穿全篇，统一自然
- 禁止口号式结尾

【输出格式】
直接输出诗歌正文，每行一行，不要输出任何解释。

诗歌："""

        try:
            result = llm(prompt, temp=0.8).strip()
            return result
        except Exception:
            return "算了 我不写了"

    def _generate_lyrics_node(self, intent: str, section: str,
                              style_template: StyleTemplate,
                              emotion_vector: EmotionVector) -> str:
        """
        歌词节点强约束生成。

        核心原则：intent 直接决定生成方向，section 决定句式约束。
        - intro: 场景设定 → 画面感强，短句
        - verse: 按 intent 叙述 → 可唱、有节奏
        - pre_hook: 情绪蓄力 → 暗示即将爆发
        - hook: 核心记忆点 → 可复述、有反转
        - outro: 情绪收束 → 有余韵
        """
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        # intent 作为核心约束，section 作为辅助约束
        if section == "hook":
            return self._generate_hook_node(intent, emotion_context, style_template, intensity, emotion_vector)
        elif section == "pre_hook":
            return self._generate_pre_hook_node(intent, emotion_context, style_template, intensity)
        elif section == "intro":
            return self._generate_intro_node(intent, emotion_context, style_template, intensity)
        elif section == "outro":
            return self._generate_outro_node(intent, emotion_context, style_template, intensity)
        else:  # verse
            return self._generate_verse_node(intent, emotion_context, style_template, intensity)

    def _generate_hook_node(self, intent: str, emotion_context: str,
                            style_template: StyleTemplate, intensity: float,
                            emotion_vector: EmotionVector = None) -> str:
        """Hook 节点：intent（核心记忆点/重复强化）直接约束方向"""
        # 如果有 HookOptimizer，使用多候选优化
        if self._hook_optimizer and emotion_vector is not None:
            # 把 intent 注入到 emotion_context 中引导 optimizer
            hook_text = self._hook_optimizer.generate(emotion_vector, style_template, num_variants=5)
            return hook_text

        # Fallback：直接 LLM 生成
        prompt = f"""生成一句歌词 Hook（核心记忆点）。

本句的创作意图：{intent}
情绪状态：{emotion_context}

约束：
- 必须体现本句的创作意图"{intent}"
- 可复述（4-8字，用户能记住）
- 情绪转折感（"却"/"才"/"原来"/"但"等关键词加分）
- {'短平快、口语化' if style_template and style_template.expression == 'direct' else '有文学性'}
- 不要空洞，要具体

直接输出句子，不要任何前缀："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "算了 我不追了"

    def _generate_pre_hook_node(self, intent: str, emotion_context: str,
                                 style_template: StyleTemplate, intensity: float) -> str:
        """Pre-Hook 节点：intent（情绪铺垫/暗示）直接约束方向"""
        prompt = f"""生成一句 Pre-Hook 铺垫句（Hook 前的情绪蓄力）。

本句的创作意图：{intent}
情绪状态：{emotion_context}

约束：
- 必须体现"{intent}"这个意图
- 情绪上升暗示感（暗示即将爆发）
- 短句（4-8字）
- {'口语化、直接' if style_template and style_template.expression == 'direct' else '有诗意'}
- 不要说透，留悬念

直接输出句子，不要任何前缀："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "我问过自己很多次"

    def _generate_intro_node(self, intent: str, emotion_context: str,
                              style_template: StyleTemplate, intensity: float) -> str:
        """Intro 节点：intent（场景设定）直接约束方向"""
        prompt = f"""生成一句歌词开场（场景设定/定调）。

本句的创作意图：{intent}
情绪状态：{emotion_context}

约束：
- 必须体现"{intent}"这个意图
- 画面感强，交代场景或氛围
- 简短（4-8字）
- 不要主观情绪，要呈现

直接输出句子，不要任何前缀："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "那天你突然不回消息了"

    def _generate_outro_node(self, intent: str, emotion_context: str,
                              style_template: StyleTemplate, intensity: float) -> str:
        """Outro 节点：intent（情绪收束）直接约束方向"""
        prompt = f"""生成一句歌词结尾（情绪收束）。

本句的创作意图：{intent}
情绪状态：{emotion_context}

约束：
- 必须体现"{intent}"这个意图
- {'简短有力' if style_template and style_template.expression == 'direct' else '有余韵'}
- 4-8字
- 可以是疑问、留白或感叹

直接输出句子，不要任何前缀："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "原来已经回不去了"

    def _generate_verse_node(self, intent: str, emotion_context: str,
                              style_template: StyleTemplate, intensity: float) -> str:
        """Verse 节点：intent 直接约束叙述方向"""
        prompt = f"""生成一句歌词（叙述/细节）。

本句的创作意图：{intent}
情绪状态：{emotion_context}

约束：
- 本句必须完成这个意图："{intent}"
- {'短句（4-8字），口语化，可唱' if style_template and style_template.lyric_density == 'short' else '中等长度（6-12字），有节奏感'}
- 不要太长，一句说清一件事
- 不要空洞感慨，要具体叙述

直接输出句子，不要任何前缀："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "我假装什么都没发生"

    def _generate_poem_node(self, intent: str, line_type: str,
                            style_template: StyleTemplate,
                            emotion_vector: EmotionVector) -> str:
        """
        诗歌节点强约束生成。

        核心原则：intent 直接决定这行要写什么，line_type 决定表达方式。
        - image: 用意象呈现，而非解释
        - feeling: 直接但克制地表达情绪
        - contrast: 反转或对比，制造张力
        - closure: 留白收束，不说透
        """
        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        if line_type == "image":
            return self._generate_image_node(intent, emotion_context, style_template, intensity)
        elif line_type == "contrast":
            return self._generate_contrast_node(intent, emotion_context, style_template, intensity)
        elif line_type == "closure":
            return self._generate_closure_node(intent, emotion_context, style_template, intensity)
        else:
            return self._generate_feeling_node(intent, emotion_context, style_template, intensity)

    def _generate_image_node(self, intent: str, emotion_context: str,
                             style_template: StyleTemplate, intensity: float) -> str:
        """意象句：intent 直接约束意象选择"""
        prompt = f"""生成一句意象派诗歌。

本句创作意图：{intent}
情绪状态：{emotion_context}

约束：
- 必须完成"{intent}"这个意图
- 用意象（物/景/动作）呈现，不解释
- {'短句、碎片化' if style_template and style_template.lyric_density == 'short' else '意象鲜明，留白'}
- 不要"我"字开头
- 不要直接说情绪

直接输出句子，不要任何前缀："""

        try:
            result = llm(prompt, temp=0.8).strip()
            return result
        except Exception:
            return "屏幕亮着，消息框空着"

    def _generate_contrast_node(self, intent: str, emotion_context: str,
                                  style_template: StyleTemplate, intensity: float) -> str:
        """反转/张力句：intent 直接约束反转方向"""
        prompt = f"""生成一句诗歌（反转/张力）。

本句创作意图：{intent}
情绪状态：{emotion_context}

约束：
- 必须完成"{intent}"这个意图
- 有转折或对比（"却"/"只是"/"然而"/"明明"等）
- {'短促有力' if style_template and style_template.lyric_density == 'short' else '有深度'}
- 不要废话，要一针见血

直接输出句子，不要任何前缀："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "你明明看到了，却选择不回"

    def _generate_closure_node(self, intent: str, emotion_context: str,
                                style_template: StyleTemplate, intensity: float) -> str:
        """收束/留白句：intent 直接约束收束方向"""
        prompt = f"""生成一句诗歌结尾（留白/开放）。

本句创作意图：{intent}
情绪状态：{emotion_context}

约束：
- 必须完成"{intent}"这个意图
- 不说透，留余韵
- {'简短' if style_template and style_template.lyric_density == 'short' else '有回味'}
- 可以是疑问、省略或无声的叹息

直接输出句子，不要任何前缀："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "后来呢"

    def _generate_feeling_node(self, intent: str, emotion_context: str,
                                style_template: StyleTemplate, intensity: float) -> str:
        """情绪句：intent 直接约束情绪表达方向"""
        prompt = f"""生成一句情绪诗歌。

本句创作意图：{intent}
情绪状态：{emotion_context}

约束：
- 必须完成"{intent}"这个意图
- 直接表达，但要克制
- {'短促、强烈' if style_template and style_template.lyric_density == 'short' else '有层次'}
- 不要太理性

直接输出句子，不要任何前缀："""

        try:
            result = llm(prompt, temp=0.7).strip()
            return result
        except Exception:
            return "等不到回复的夜晚"



# ==================== Hook 优化器 ====================

class HookOptimizer:
    """
    多候选 Hook 生成 + 评分选最优。

    策略：直接多生成（不同 hook_type 模板 + 不同温度采样），
    而非在单一本上变异 —— 保证变体多样性。
    """

    HOOK_TYPES = [
        "contrast",    # 反转型：前半句陈述，后半句反转
        "shock",       # 冲击型：出人意料的结论
        "question",    # 疑问型：以问句收尾，留悬念
        "image_alone", # 意象型：用画面代替情绪
        "time_marker", # 时间型：标记性的时间/动作
    ]

    def generate(self, emotion_vector: EmotionVector,
                 style_template: StyleTemplate,
                 num_variants: int = 5) -> str:
        """
        生成多个 Hook 变体，评分后返回最优。

        Args:
            emotion_vector: 情绪向量
            style_template: 风格模板
            num_variants: 变体数量

        Returns:
            最优 Hook 句
        """
        import random

        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        # 从 HOOK_TYPES 中随机选 num_variants 个（允许重复）
        selected_types = random.choices(self.HOOK_TYPES, k=num_variants)
        # 加上不同温度采样
        temps = [0.5, 0.7, 0.9]
        hook_texts = []

        for hook_type in set(selected_types):
            hook_texts.append(self._generate_one_hook(
                emotion_context, style_template, hook_type=hook_type
            ))

        for temp in temps:
            hook_texts.append(self._generate_one_hook(
                emotion_context, style_template, temp=temp
            ))

        # 去重
        hook_texts = list(dict.fromkeys(hook_texts))

        # 评分排序
        scored = [(h, self._score_hook(h)) for h in hook_texts]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def _generate_one_hook(self, emotion_context: str,
                            style_template: StyleTemplate,
                            hook_type: str = None,
                            temp: float = 0.7) -> str:
        """生成单个 Hook"""
        type_instruction = {
            "contrast": "有明显的情绪反转（前半句陈述事实，后半句转折）",
            "shock": "出人意料的结论，让人一读就愣住",
            "question": "以疑问句结尾，让人思考",
            "image_alone": "用意象/画面收尾，不直接说情绪",
            "time_marker": "用具体时间/动作标记，增强记忆点",
        }.get(hook_type, "有情绪共鸣")

        prompt = f"""生成一句歌词 Hook（核心记忆点）。

情绪状态：{emotion_context}

约束：
- {type_instruction}
- 4-8字，可复述
- {'短平快、口语化' if style_template and style_template.expression == 'direct' else '可以有文学性'}
- 不要空洞感慨，要具体

直接输出句子，不要任何前缀："""

        try:
            result = llm(prompt, temp=temp).strip()
            return result
        except Exception:
            return "算了 我不追了"

    def _score_hook(self, hook: str) -> float:
        """
        Hook 评分：
        - 可复述性（4-8字）: 0.4
        - 情绪冲击/转折: 0.3
        - 对称/反转结构: 0.3
        """
        score = 0.0

        # 可复述性
        if 4 <= len(hook) <= 8:
            score += 0.4
        elif 3 <= len(hook) <= 10:
            score += 0.2

        # 情绪冲击（疑问/感叹/转折词）
        if any(c in hook for c in "！？"):
            score += 0.3
        elif any(kw in hook for kw in ["却", "才", "原来", "但", "只是", "然而"]):
            score += 0.25

        # 对称/反转结构（前后有对比感）
        contrast_pairs = [("你", "我"), ("他", "她"), ("明明", "却"), ("以为", "结果")]
        has_contrast = any(a in hook and b in hook for a, b in contrast_pairs)
        if has_contrast:
            score += 0.3
        elif len(hook) >= 4 and (hook[0] == hook[-1]):
            score += 0.15  # 简单的首尾呼应

        return min(1.0, score)


# ==================== 目标函数 ====================

class ObjectiveFunction:
    """
    可驱动优化的目标函数。

    与 CandidateScorer 的区别：
    - CandidateScorer：评估已知候选，给出分数
    - ObjectiveFunction：驱动优化过程，可比较多个候选

    设计原则：
    - 权重可配置（不硬编码）
    - 可对原始文本直接打分（无需 GenerationResult）
    - 返回 (总分, 详情)，详情可直接用于比较
    """

    LYRICS_WEIGHTS = {
        "hook_strength": 0.35,
        "lyric_variation": 0.20,
        "emotion_consistency": 0.25,
        "singability": 0.20,
    }

    POEM_WEIGHTS = {
        "imagery_density": 0.30,
        "novelty": 0.20,
        "coherence": 0.20,
        "emotional_depth": 0.30,
    }

    def __init__(self, mode: "GenerationMode" = None, weights: dict = None):
        """
        Args:
            mode: GenerationMode.LYRICS 或 POEM，决定使用哪套权重
            weights: 可选，覆盖默认权重，如 {"hook_strength": 0.4, ...}
        """
        self._mode = mode
        self._weights = weights

    def _get(self, result, attr, default=None):
        """支持 dict 或 GenerationResult 对象"""
        if isinstance(result, dict):
            return result.get(attr, default)
        return getattr(result, attr, default)

    def score(self, result: "GenerationResult") -> float:
        """
        对 GenerationResult 打目标分（用于 rank）。
        支持 dict 或 GenerationResult 对象。
        """
        result_type = self._get(result, "type", "lyrics")
        score_details = self._get(result, "score_details") or {}
        if result_type == "lyrics":
            weights = self._resolve_weights("lyrics")
            total = sum(
                score_details.get(k, 0.0) * w
                for k, w in weights.items()
            )
        else:
            weights = self._resolve_weights("poem")
            total = sum(
                score_details.get(k, 0.0) * w
                for k, w in weights.items()
            )
        return total

    def score_text(self, text: str, hook: str, emotion: str,
                   mode: "GenerationMode") -> float:
        """
        对原始文本打分（无需 GenerationResult）。
        用于 RefineLoop 中比较多候选/变体。
        """
        scorer = CandidateScorer()
        dummy_result = GenerationResult(
            type="lyrics" if mode == GenerationMode.LYRICS else "poem",
            style="", text=text, hook=hook,
            structure_dsl=[], emotion=emotion,
            emotion_intensity=0.5, score=0.0, score_details={},
        )
        _, details = scorer.score(dummy_result)
        weights = self._resolve_weights(dummy_result.type)
        return sum(details.get(k, 0.0) * w for k, w in weights.items())

    def _resolve_weights(self, result_type: str) -> dict:
        if self._weights:
            return self._weights
        if result_type == "lyrics":
            return dict(self.LYRICS_WEIGHTS)
        return dict(self.POEM_WEIGHTS)


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

    def _get(self, result, attr, default=None):
        """支持 dict 或 GenerationResult 对象"""
        if isinstance(result, dict):
            return result.get(attr, default)
        return getattr(result, attr, default)

    def score(self, result) -> tuple:
        """返回 (总分, 详情字典)。支持 dict 或 GenerationResult 对象。"""
        result_type = self._get(result, "type", "lyrics")
        if result_type == "lyrics":
            return self._score_lyrics(result)
        else:
            return self._score_poem(result)

    def _score_lyrics(self, result) -> tuple:
        text = self._get(result, "text", "")
        hook = self._get(result, "hook", "")
        emotion = self._get(result, "emotion", "")

        details = {}

        # Hook 强度
        hook_strength = self._score_hook_strength(text, hook)
        details["hook_strength"] = hook_strength

        # 歌词变化
        lyric_variation = self._score_lyric_variation(text)
        details["lyric_variation"] = lyric_variation

        # 情绪一致性
        emotion_consistency = self._score_emotion_consistency(text, emotion)
        details["emotion_consistency"] = emotion_consistency

        # 可唱性
        singability = self._score_singability(text)
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

    def _score_poem(self, result) -> tuple:
        text = self._get(result, "text", "")
        emotion = self._get(result, "emotion", "")

        details = {}

        # 意象密度
        imagery_density = self._score_imagery_density(text)
        details["imagery_density"] = imagery_density

        # 新颖度
        novelty = self._score_novelty(text)
        details["novelty"] = novelty

        # 连贯性
        coherence = self._score_coherence(text)
        details["coherence"] = coherence

        # 情绪深度
        emotional_depth = self._score_emotional_depth(text, emotion)
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


# ==================== 风格一致性约束 ====================

class StyleChecker:
    """
    检查文本是否符合 StyleTemplate 定义的风格约束。

    作用：refine 过程中，防止"越优化越不像原风格"。
    最终得分 = objective_score - style_penalty

    风格惩罚维度：
    - lyric_density: 句长是否匹配 short/medium/long
    - expression: 表达方式（direct 风格不能太文学，metaphor 不能太直白）
    - imagery_penalty: 某些风格（如 emo/direct）不需要太多意象
    """

    # 直接风格（抖音伤感/说唱）：不宜过多意象词
    DIRECT_EXPRESSION_KEYWORDS = ["忽然", "竟然", "原来", "却", "明明", "其实", "只是"]
    METAPHOR_EXPRESSION_KEYWORDS = ["像", "如", "似", "仿佛", "如同"]

    def penalty(self, text: str, style_template: StyleTemplate) -> float:
        """
        返回风格惩罚值（0.0 ~ 0.5）。

        分越低 = 越符合风格约束。
        目标：最终 score = objective_score - penalty
        """
        if style_template is None:
            return 0.0

        p = 0.0

        # 1. lyric_density 惩罚
        lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("【")]
        if lines:
            avg_len = sum(len(l) for l in lines) / len(lines)

            if style_template.lyric_density == "short":
                # short 风格：平均句长应 <= 8
                if avg_len > 10:
                    p += 0.15
                elif avg_len > 8:
                    p += 0.05
            elif style_template.lyric_density == "long":
                # long 风格：平均句长应 >= 8
                if avg_len < 6:
                    p += 0.15
                elif avg_len < 8:
                    p += 0.05

        # 2. expression 惩罚
        if style_template.expression == "direct":
            # direct 风格：意象词过多 = 不够直接
            metaphor_count = sum(1 for kw in self.METAPHOR_EXPRESSION_KEYWORDS if kw in text)
            if metaphor_count >= 3:
                p += 0.15
            elif metaphor_count >= 2:
                p += 0.08

        elif style_template.expression == "metaphor":
            # metaphor 风格：直白情绪词过多 = 意象不足
            direct_count = sum(1 for kw in self.DIRECT_EXPRESSION_KEYWORDS if kw in text)
            if direct_count >= 4:
                p += 0.15
            elif direct_count >= 2:
                p += 0.08

        # 3. Hook 相关惩罚（如果 template 指定了 hook_repeat）
        hook_count = text.count("【Hook】")
        if style_template.hook_repeat >= 2 and hook_count == 0:
            p += 0.1  # 需要 Hook 但没有

        # 4. Pre-Hook 惩罚
        if style_template.pre_hook_enabled:
            has_prehook = "【前Hook】" in text or "【Pre-Hook】" in text
            if not has_prehook:
                p += 0.05

        return min(0.5, p)


# ==================== 文本分析器 ====================

class TextAnalyzer:
    """
    规则快筛检测文本问题（0 LLM 调用）。

    检测维度：
    - hook_weak: Hook 长度/结构不达标
    - too_flat: 句式变化少（长度方差小、开头词单一）
    - no_imagery: 诗歌缺乏意象词
    - emotion_drift: 情绪关键词与预期不符
    """

    IMAGERY_WORDS = {
        "屏幕", "消息", "凌晨", "沉默", "放手",
        "枫叶", "稻香", "雨", "夜", "光", "影子",
        "咖啡", "烟", "酒", "日记", "照片",
        "空", "满", "远", "近", "冷", "暖",
        "车站", "街角", "雨天", "晴天", "心跳",
    }

    EMOTION_KEYWORDS = {
        "sadness": ["难过", "不回", "算了", "远了", "回不去", "忘", "痛", "伤"],
        "nostalgia": ["以前", "曾经", "那年", "记得", "时光", "怀念"],
        "anger": ["凭什么", "为什么", "太过分", "不公平", "气"],
        "joy": ["开心", "快乐", "幸福", "美好", "甜蜜"],
        "warmth": ["温暖", "谢谢", "想见", "拥抱", "感动"],
        "hope": ["会", "能", "相信", "希望", "期待"],
        "loneliness": ["一个人", "孤独", "没人", "寂寞", "空"],
    }

    START_WORDS = {"我", "你", "他", "她", "这", "那", "不是", "其实", "算了", "结果", "原来", "明明"}

    def analyze(self, text: str, mode: GenerationMode, expected_emotion: str = None) -> dict:
        """
        返回问题字典，每个 key 为 True 表示需要修复。
        """
        if mode == GenerationMode.LYRICS:
            return self._analyze_lyrics(text)
        else:
            return self._analyze_poem(text, expected_emotion)

    def _analyze_lyrics(self, text: str) -> dict:
        issues = {"hook_weak": False, "too_flat": False}

        # hook_weak: 检查 Hook 长度和情绪词
        hook_candidates = [l for l in text.split("\n") if "【Hook】" in l]
        if hook_candidates:
            hook = hook_candidates[0].replace("【Hook】", "").strip()
            if len(hook) < 4 or len(hook) > 10:
                issues["hook_weak"] = True
            if not any(kw in hook for kw in ["却", "才", "原来", "但", "算了", "没"]):
                issues["hook_weak"] = True
        else:
            # 没有 Hook 标记，整段结尾当作 hook
            non_tag = [l for l in text.split("\n") if l.strip() and not l.startswith("【")]
            if non_tag:
                last = non_tag[-1].strip()
                if len(last) < 4 or len(last) > 10:
                    issues["hook_weak"] = True

        # too_flat: 句子长度方差 + 开头词多样性
        lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("【")]
        if len(lines) >= 3:
            lengths = [len(l) for l in lines]
            avg = sum(lengths) / len(lengths)
            variance = sum((l - avg) ** 2 for l in lengths) / len(lengths)
            if variance < 2:
                issues["too_flat"] = True

            start_words = set()
            for line in lines:
                for sw in self.START_WORDS:
                    if line.startswith(sw):
                        start_words.add(sw)
                        break
            if len(start_words) <= 2:
                issues["too_flat"] = True

        return issues

    def _analyze_poem(self, text: str, expected_emotion: str = None) -> dict:
        issues = {"no_imagery": False, "too_flat": False, "emotion_drift": False}

        # no_imagery: 意象词密度
        if not any(w in text for w in self.IMAGERY_WORDS):
            issues["no_imagery"] = True

        # too_flat: 句式开头多样性
        lines = [l for l in text.split("\n") if l.strip()]
        if len(lines) >= 3:
            start_words = set()
            for line in lines:
                for sw in self.START_WORDS:
                    if line.strip().startswith(sw):
                        start_words.add(sw)
                        break
            if len(start_words) <= 2:
                issues["too_flat"] = True

        # emotion_drift: 情绪关键词不符
        if expected_emotion:
            expected_kws = self.EMOTION_KEYWORDS.get(expected_emotion, [])
            matched = sum(1 for kw in expected_kws if kw in text)
            if expected_kws and matched == 0:
                issues["emotion_drift"] = True

        return issues


# ==================== Refine Loop（操作空间搜索）====================

class RefineLoop:
    """
    基于操作空间搜索的 RefineLoop。

    核心变化：从"规则触发" → "搜索优化"

    每次 refine 步骤：
    1. 定义操作空间 OPS（每个 op 是生成候选项的 prompt 策略）
    2. 对当前 text 应用每个 op（或采样），生成候选
    3. 用 (objective_score - style_penalty) 对候选打分
    4. 选择最优候选（贪心）；若无提升则保持原文本

    这是一个贪心束搜索（Greedy Beam Search）：
    - beam_width = 1（只保留最优）
    - 若最优候选 < 当前，停止迭代
    """

    # 操作空间定义：op_name → (description, min_issue)
    # min_issue 表示该操作针对的问题
    OPS = {
        "rewrite_hook": {
            "desc": "重写 Hook：强化记忆点、可复述性、情绪冲击",
            "min_issue": "hook_weak",
        },
        "shorten_lines": {
            "desc": "缩短句长：所有句压缩到 4-8 字",
            "min_issue": "too_flat",
        },
        "lengthen_lines": {
            "desc": "拉长句长：补充细节使句子更饱满",
            "min_issue": None,
        },
        "add_imagery": {
            "desc": "注入意象：补充具象视觉/听觉/触觉意象",
            "min_issue": "no_imagery",
        },
        "increase_contrast": {
            "desc": "增强反转：加入转折/对比结构",
            "min_issue": None,
        },
        "simplify_language": {
            "desc": "简化语言：去掉形容词，直接呈现",
            "min_issue": None,
        },
        "fix_emotion_drift": {
            "desc": "修复情绪漂移：强化情绪关键词，统一基调",
            "min_issue": "emotion_drift",
        },
    }

    def __init__(self):
        self.analyzer = TextAnalyzer()

    def refine(self, text: str,
               style_template: StyleTemplate,
               emotion_vector: EmotionVector,
               mode: GenerationMode,
               objective_fn: "ObjectiveFunction" = None,
               style_checker: "StyleChecker" = None,
               issues: dict = None,
               beam_width: int = 2) -> tuple:
        """
        束搜索多步 refine（beam_width >= 2）。

        每次迭代：
        1. 对当前 beam 中每个候选，应用所有相关 op 生成扩展候选
        2. 用 (objective - penalty) 对所有候选打分
        3. 保留 top beam_width

        若 beam_width=1，退化为贪心搜索。

        Returns:
            (best_text, applied_op) - 最优候选和对其应用的操 作
        """
        if objective_fn is None:
            objective_fn = ObjectiveFunction(mode=mode)
        if style_checker is None:
            style_checker = StyleChecker()

        primary, intensity = emotion_vector.get_primary()
        emotion_context = emotion_vector.to_prompt_context()

        # 初始化 beam：[(text, score, applied_op)]
        initial_score = self._score_one(text, primary, mode, objective_fn, style_checker, style_template)
        beam = [(text, initial_score, None)]

        # 预分析 issues（全局，不变）
        if issues is None:
            issues = self.analyzer.analyze(text, mode, expected_emotion=primary)

        relevant_ops = self._filter_ops(issues)
        if not relevant_ops:
            return text, None

        # 束搜索迭代
        for step in range(5):  # 最多5步
            # 动态提议新操作（基于当前最优 beam 候选）
            dynamic_ops = self._propose_ops(
                beam[0][0], issues, emotion_context, style_template, mode
            )

            # 合并固定 ops + 动态 ops（动态 op 标记以便追踪）
            all_ops = relevant_ops + [f"dyn:{op}" for op in dynamic_ops]

            # 扩展所有 beam 候选
            all_candidates = []
            for beam_text, beam_score, _ in beam:
                for op in all_ops:
                    candidate = self._apply_op(op, beam_text, emotion_context, style_template, mode)
                    if candidate and candidate != beam_text:
                        cand_score = self._score_one(
                            candidate, primary, mode, objective_fn, style_checker, style_template
                        )
                        all_candidates.append((candidate, cand_score, op))

            if not all_candidates:
                break

            # 合并原 beam 一起排序
            combined = beam + all_candidates
            combined.sort(key=lambda x: x[1], reverse=True)
            beam = combined[:beam_width]

            # 若最优候选没有提升，停止
            if beam[0][1] <= initial_score and step >= 1:
                break

        best_text, best_score, best_op = beam[0]
        if best_text == text:
            return text, None
        return best_text, best_op

    def _score_one(self, text: str, emotion: str, mode: GenerationMode,
                    objective_fn, style_checker, style_template) -> float:
        """对单条文本计算 composite score"""
        hook = self._extract_hook_from_text(text)
        obj = objective_fn.score_text(text, hook, emotion, mode)
        penalty = style_checker.penalty(text, style_template)
        return obj - penalty

    def _filter_ops(self, issues: dict) -> list:
        """根据 issues 过滤相关操作"""
        relevant = []
        for op_name, op_info in self.OPS.items():
            min_issue = op_info["min_issue"]
            if min_issue is None:
                # 无特定问题要求的 op，每次都可以尝试
                relevant.append(op_name)
            elif issues.get(min_issue):
                relevant.append(op_name)
        return relevant

    def _propose_ops(self, text: str, issues: dict,
                      emotion_context: str,
                      style_template: StyleTemplate,
                      mode: GenerationMode) -> list:
        """
        用 LLM 动态提议新的操作（实验性）。

        根据当前文本和问题，让 LLM 建议针对性的修改策略。
        返回格式：[{"op": str, "description": str}, ...]
        """
        issue_summary = ", ".join([k for k, v in issues.items() if v]) or "无明显问题"
        is_lyrics = mode == GenerationMode.LYRICS
        type_hint = "歌词" if is_lyrics else "诗歌"

        prompt = f"""以下{type_hint}存在以下问题：{issue_summary}

原文本：
{text}

请建议 1-2 个针对性的修改操作（必须是具体、可执行的修改）：
- 每个操作用一句话描述修改方向
- 格式：操作名: 描述
- 不要超过2个

示例输出：
add_repetition: 在第二句加入重复词增强节奏感
insert_metaphor: 在第三行前加入一个意象比喻

直接输出，不要解释："""

        try:
            result = llm(prompt, temp=0.8).strip()
            ops = []
            for line in result.split("\n"):
                line = line.strip()
                if ":" in line:
                    op_name = line.split(":", 1)[0].strip()
                    # 验证 op 名字不包含危险字符
                    if op_name and len(op_name) < 30:
                        ops.append(op_name)
            return ops[:2]  # 最多2个动态操作
        except Exception:
            return []

    def _apply_op(self, op: str, text: str,
                  emotion_context: str,
                  style_template: StyleTemplate,
                  mode: GenerationMode) -> str:
        """对当前文本应用指定操作"""
        # 动态操作：dyn:op_name
        if op.startswith("dyn:"):
            dyn_op = op[4:]
            return self._apply_dynamic_op(dyn_op, text, emotion_context, style_template, mode)

        if mode == GenerationMode.LYRICS:
            return self._apply_op_lyrics(op, text, emotion_context, style_template)
        else:
            return self._apply_op_poem(op, text, emotion_context, style_template)

    def _apply_dynamic_op(self, op: str, text: str,
                          emotion_context: str,
                          style_template: StyleTemplate,
                          mode: GenerationMode) -> str:
        """
        应用 LLM 动态提议的操作。
        op 是操作名称（由 LLM 生成），我们将其作为修改指令。
        """
        is_lyrics = mode == GenerationMode.LYRICS
        type_hint = "歌词" if is_lyrics else "诗歌"

        prompt = f"""对以下{type_hint}执行修改操作：{op}

原{type_hint}：
{text}

要求：
- 情绪：{emotion_context}
- 只执行指定操作，不要大改
- 保持原结构和其他部分不变
- 直接输出修改后的完整{type_hint}，不要解释

直接输出："""

        try:
            return llm(prompt, temp=0.7).strip()
        except Exception:
            return text

    def _apply_op_lyrics(self, op: str, text: str,
                         emotion_context: str,
                         style_template: StyleTemplate) -> str:
        prompts = {
            "rewrite_hook": f"""以下歌词的 Hook 太弱，请改写为更有冲击力的核心记忆句。

原歌词：
{text}

要求：
- 情绪：{emotion_context}
- 新 Hook 必须：4-8字、有情绪反转或共鸣、可复述
- {'短平快口语化' if style_template and style_template.expression == 'direct' else '可以有文学性'}
- 保持其他部分不变，只改【Hook】部分
- 格式：输出完整歌词

直接输出完整歌词，不要解释：""",

            "shorten_lines": f"""以下歌词句子太长，请压缩到 4-8 字每句，保持情绪不变。

原歌词：
{text}

要求：
- 情绪：{emotion_context}
- 每句压缩到 4-8 字
- 保持原结构和情绪
- 保持韵律感

直接输出完整歌词，不要解释：""",

            "lengthen_lines": f"""以下歌词句子太短，请适当补充细节，使每句 8-14 字。

原歌词：
{text}

要求：
- 情绪：{emotion_context}
- 适度扩展句长
- 不要过度解释

直接输出完整歌词，不要解释：""",

            "increase_contrast": f"""以下歌词缺少反转和张力，请在适当位置加入转折句。

原歌词：
{text}

要求：
- 情绪：{emotion_context}
- 加入对比或反转（却/但/只是/然而）
- 保持整体结构

直接输出完整歌词，不要解释：""",

            "simplify_language": f"""以下歌词太文艺/啰嗦，请改为更直接、口语化的表达。

原歌词：
{text}

要求：
- 情绪：{emotion_context}
- 直接说，不要绕
- 保持情绪不变

直接输出完整歌词，不要解释：""",

            "fix_emotion_drift": f"""以下歌词情绪不统一，请改写强化情绪一致性。

原歌词：
{text}

目标情绪：{emotion_context}

要求：
- 统一情绪基调
- 增加目标情绪关键词

直接输出完整歌词，不要解释：""",
        }

        prompt = prompts.get(op)
        if not prompt:
            return text

        try:
            return llm(prompt, temp=0.6).strip()
        except Exception:
            return text

    def _apply_op_poem(self, op: str, text: str,
                      emotion_context: str,
                      style_template: StyleTemplate) -> str:
        prompts = {
            "rewrite_hook": f"""以下诗歌的结尾不够有力，请改写为更有冲击力的收束句。

原诗歌：
{text}

要求：
- 情绪：{emotion_context}
- 增强结尾的记忆点和情绪冲击
- 保持原风格

直接输出完整诗歌，不要解释：""",

            "add_imagery": f"""以下诗歌缺乏意象，请改写补充具象的视觉/听觉/触觉意象。

原诗歌：
{text}

要求：
- 情绪：{emotion_context}
- 补充意象（屏幕/雨/夜/光/影子/空/车站/街角等）
- 不要直接说情绪，用意象呈现

直接输出完整诗歌，不要解释：""",

            "increase_contrast": f"""以下诗歌缺少张力，请加入反转或对比结构。

原诗歌：
{text}

要求：
- 情绪：{emotion_context}
- 加入对比或反转

直接输出完整诗歌，不要解释：""",

            "simplify_language": f"""以下诗歌太复杂，请简化为更克制的表达。

原诗歌：
{text}

要求：
- 情绪：{emotion_context}
- 简洁、克制
- 不要过度修饰

直接输出完整诗歌，不要解释：""",

            "fix_emotion_drift": f"""以下诗歌情绪不统一，请改写强化情绪一致性。

原诗歌：
{text}

目标情绪：{emotion_context}

要求：
- 统一情绪基调

直接输出完整诗歌，不要解释：""",
        }

        prompt = prompts.get(op)
        if not prompt:
            return text

        try:
            return llm(prompt, temp=0.6).strip()
        except Exception:
            return text

    def _extract_hook_from_text(self, text: str) -> str:
        lines = text.split("\n")
        for line in lines:
            if "【Hook】" in line or "[Hook]" in line:
                return line.replace("【Hook】", "").replace("[Hook]", "").strip()
        non_empty = [l for l in lines if l.strip() and not l.startswith("【")]
        if non_empty:
            return non_empty[-1].strip()
        return ""


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
        self.humanizer = HumanRewriteLayer(intensity=0.3)
        self.dsl_gen = StructureDSLGenerator()
        self.hook_optimizer = HookOptimizer()
        self.text_gen = TextGenerator(hook_optimizer=self.hook_optimizer)
        self.scorer = CandidateScorer()
        self.objective_fn = ObjectiveFunction()
        self.style_checker = StyleChecker()
        self.analyzer = TextAnalyzer()
        self.refine_loop = RefineLoop()
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

        用户可控维度（通过 constraints）：
            mode: "lyrics" | "poem"
            style: "douyin_sad" | "rap" | "emo_pop" | "modern" | "classical" | "imagist" | "diary"
            constraints:
                - intensity: 情绪强度 0.0~1.0
                - structure: 用户自定义 DSL（list[dict]），最高优先
                - poem_form: "free" | "classical" | "imagist" | "diary"
                - hook_strength: "strong" | "weak" | "none"（Hook 强度偏好）
                - lyric_density: "short" | "medium" | "long"（句长风格）
                - expression: "direct" | "metaphor" | "self_mock"（表达方式）
                - weights: dict，自定义 ObjectiveFunction 权重
                - beam_width: 束搜索宽度（默认2），越大保留路径越多
                - max_refine_steps: 最大优化步数
                - humanize_intensity: 人类化强度

        Returns:
            GenerationResult: 包含主结果 + 候选列表 + 创作解释
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

        # 2.1 用 constraints 覆盖风格字段（用户可直接控制表达/句长）
        if "expression" in constraints:
            style_template.expression = constraints["expression"]
        if "lyric_density" in constraints:
            style_template.lyric_density = constraints["lyric_density"]
        if "poem_form" in constraints:
            style_template.poem_form = constraints["poem_form"]

        # 2.2 目标函数（支持用户自定义权重）
        custom_weights = constraints.get("weights")
        objective_fn = ObjectiveFunction(mode=gen_mode, weights=custom_weights)

        # 2.3 构建创作解释（初始部分）
        primary_emotion, intensity = emotion_vector.get_primary()
        creation_explanation = {
            "emotion_arc": f"{primary_emotion} ({intensity:.1f})",
            "style_decisions": {
                "expression": style_template.expression,
                "lyric_density": style_template.lyric_density,
                "poem_form": getattr(style_template, 'poem_form', None),
            },
            "structure_type": style_template.name if style_template else "default",
            "hook_strategy": self._describe_hook_strategy(style_template, constraints),
            "objective_weights": custom_weights,
            "optimization_steps": [],
            "num_candidates": num_candidates,
            "final_refine_steps": 0,
        }

        # 3. 多候选生成
        candidates = []
        for i in range(num_candidates):
            candidate = self._generate_one(
                content, emotion_vector, gen_mode, style_template, constraints, humanize
            )
            candidates.append(candidate)

        # 4. 排序
        ranked = self._rank(candidates)

        # 5. 两阶段精修：只对 top 2 做完整 refine loop
        max_refine_steps = constraints.get("max_refine_steps", 3)
        top_candidates = ranked[:2] if ranked else []

        # 提前初始化，避免 UnboundLocalError
        best_c = None
        best_c_score = float("-inf")

        for ranked_entry in top_candidates:
            c = ranked_entry["result"]
            refine_steps = 0
            step_records = []
            for step in range(max_refine_steps):
                issues = self.analyzer.analyze(c["text"], gen_mode, expected_emotion=c.get("emotion"))
                if not any(issues.values()):
                    break
                c["text"], applied_op = self.refine_loop.refine(
                    c["text"], style_template, emotion_vector, gen_mode,
                    objective_fn=objective_fn,
                    style_checker=self.style_checker,
                    issues=issues,
                    beam_width=constraints.get("beam_width", 2),
                )
                refine_steps += 1
                step_records.append({
                    "step": step,
                    "issues": [k for k, v in issues.items() if v],
                    "applied_op": applied_op,
                })
            c["refinement_steps"] = refine_steps
            c["step_records"] = step_records
            # Hook 可能已被改写，重新提取
            c["hook"] = self._extract_hook(c["text"], gen_mode)
            # 追踪当前最优候选（用于记录创作路径）
            primary_c, _ = emotion_vector.get_primary()
            c_score = objective_fn.score_text(
                c["text"], c.get("hook", ""), primary_c, gen_mode
            ) - self.style_checker.penalty(c["text"], style_template)
            if c_score > best_c_score:
                best_c = c
                best_c_score = c_score
                creation_explanation["optimization_steps"] = step_records
                creation_explanation["final_refine_steps"] = refine_steps

        # 兜底：top_candidates 为空时
        if best_c is None:
            creation_explanation["optimization_steps"] = []
            creation_explanation["final_refine_steps"] = 0

        # 6. 重新排序（refine 后）使用 composite score = objective - penalty
        all_refine_candidates = [e["result"] for e in top_candidates] + [e["result"] for e in (ranked[2:] if len(ranked) > 2 else [])]
        primary, _ = emotion_vector.get_primary()
        for c in all_refine_candidates:
            text = c.get("text", "")
            hook = c.get("hook", "")
            obj = objective_fn.score_text(text, hook, primary, gen_mode)
            penalty = self.style_checker.penalty(text, style_template)
            c["final_score"] = obj - penalty

        all_refine_candidates.sort(key=lambda x: x["final_score"], reverse=True)

        # 7. 提取最优结果
        best = all_refine_candidates[0]
        best_score = best.get("final_score", 0.0)
        best_details = best.get("score_details", {})

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
            refinement_steps=best.get("refinement_steps", 0),
            raw_text=best.get("raw_text", ""),
            creation_explanation=creation_explanation,
        )

    def _generate_one(
        self, content, emotion_vector: EmotionVector, mode: GenerationMode,
        style_template: StyleTemplate, constraints: dict, humanize: bool
    ) -> dict:
        """单次生成"""
        primary, intensity = emotion_vector.get_primary()

        # 1. 生成 DSL（支持用户自定义结构）
        dsl = self.dsl_gen.generate(
            emotion_vector, mode, style_template,
            user_structure=constraints.get("structure"),
            poem_form=constraints.get("poem_form"),
        )

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
            "type": "lyrics" if mode == GenerationMode.LYRICS else "poem",
            "refinement_steps": 0,
        }

    def _rank(self, candidates: list) -> list:
        """对候选打分并排序"""
        scored = []
        for c in candidates:
            mode_str = c.get("type", "lyrics")
            result = self._to_result(c, mode_str)
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

    def _composite_score(self, candidate: dict,
                         style_template: StyleTemplate,
                         mode: GenerationMode,
                         emotion: str) -> float:
        """
        最终得分 = objective_score - style_penalty。
        用于 refine 后排序。
        """
        text = candidate.get("text", "")
        hook = candidate.get("hook", "")
        obj_score = self.objective_fn.score_text(text, hook, emotion, mode)
        penalty = self.style_checker.penalty(text, style_template)
        return obj_score - penalty

    def _describe_hook_strategy(self, style_template: StyleTemplate,
                                 constraints: dict) -> str:
        """描述 Hook 策略（用于创作解释）"""
        hook_pref = constraints.get("hook_strength", "auto")
        if hook_pref == "none":
            return "无 Hook，纯叙述"
        elif hook_pref == "weak":
            return "弱 Hook，辅助叙事"
        elif hook_pref == "strong":
            return "强 Hook（反转+重复），强化记忆"
        # auto: 从 style_template 推断
        if style_template:
            if style_template.hook_repeat >= 3:
                return "洗脑 Hook（重复3次），高复述性"
            elif style_template.expression == "direct":
                return "反转 Hook，情绪冲击"
            else:
                return "意象 Hook，含蓄共鸣"
        return "默认 Hook 策略"

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
