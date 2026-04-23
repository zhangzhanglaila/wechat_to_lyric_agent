"""
v7.9 Agent OS - Emotion-Aware Enhanced OS + Human Rewrite Layer
==============================================================
Integration layer: AgentOSKernel + ArtPipeline + HookGenerator + HumanRewriteLayer
"""

from agent_os import AgentOSKernel, ExecutionGate, StateSnapshotBuilder, StateSnapshot
from agent_os.art_layer import (
    ArtPipeline, EmotionVector, LyricRhythmSpec, ChatCompressionLayer,
    StylePreset, EmotionCurve, HookGenerator, StylePresetLibrary, HumanRewriteLayer
)


class EnhancedAgentOS:
    """
    EnhancedAgentOS - v7.9 Content Virality Engine

    核心变化：
    1. HookGenerator 生成"让人想发朋友圈"的记忆点
    2. HumanRewriteLayer 让AI歌词不像AI写的（v7.9核心）
    3. StylePreset 支持多种风格
    4. EmotionCurve 控制情绪起伏

    架构：
        ChatInput
            ↓
        ChatCompression
            ↓
        HookGenerator ← 传播性
            ↓
        LyricRenderer
            ↓
        HumanRewriteLayer ← 可信度（v7.9核心）
            ↓
        Virality-Ready Lyrics
    """

    def __init__(self, *args, **kwargs):
        self.kernel = AgentOSKernel(*args, **kwargs)
        self.art_pipeline = ArtPipeline(humanize=True)
        self.hook_generator = HookGenerator()
        self.humanizer = HumanRewriteLayer(intensity=0.3)
        self.compression = ChatCompressionLayer()
        self.gate = ExecutionGate()
        self.use_art_generation = True

    def submit_task(self, task):
        return self.kernel.submit_task(task)

    def generate_lyrics(
        self,
        chat_messages: list,
        style: StylePreset = None,
        emotion_curve: EmotionCurve = None,
        humanize_intensity: float = 0.3,
        user_feedback: str = ""
    ) -> dict:
        """
        v7.9 主接口：生成歌词

        Args:
            chat_messages: 聊天记录
            style: 风格预设（可选，自动检测）
            emotion_curve: 情绪曲线（可选，自动检测）
            humanize_intensity: 人类化强度 0.0-1.0，默认0.3
            user_feedback: 用户反馈

        Returns:
            {
                "lyrics": "歌词内容（含Hook，已人类化）",
                "raw_lyrics": "原始AI歌词",
                "hook": "记忆点句子",
                "style": "风格",
                "emotion_curve": "情绪曲线",
                "hook_variants": ["hook变体1", "hook变体2", ...]
            }
        """
        if not self.use_art_generation:
            return {"error": "Art generation disabled"}

        # 使用人类化强度控制
        result = self.art_pipeline.run_with_humanize(
            chat_messages,
            style=style,
            humanize_intensity=humanize_intensity,
            user_feedback=user_feedback
        )

        return {
            "lyrics": result["lyrics"],
            "raw_lyrics": result.get("raw_lyrics", result["lyrics"]),
            "theme": result["theme"],
            "emotion": result["emotion_vector"].to_prompt_context(),
            "hook": result["hook"],
            "style": result["style"],
            "emotion_curve": result["emotion_curve"],
            "hook_variants": result["hook_variants"],
            "humanized": result["humanized"],
            "humanize_intensity": humanize_intensity,
            "imagery": result["imagery"],
            "generation_count": result["generation_count"]
        }

    # 保留旧接口（向后兼容）
    def submit_chat_for_lyrics(self, chat_messages: list, user_feedback: str = "") -> dict:
        """标准歌词生成（向后兼容）"""
        return self.generate_lyrics(chat_messages, user_feedback=user_feedback)

    def submit_chat_with_bias(
        self,
        chat_messages: list,
        emotion_seed: float = None,
        user_feedback: str = ""
    ) -> dict:
        """
        EmotionBias 驱动的歌词生成
        """
        if not self.use_art_generation:
            return {"error": "Art generation disabled"}

        # 1. 压缩聊天，获取情绪向量
        compression_result = self.compression.compress(chat_messages)
        emotion_vector = compression_result["emotion_vector"]

        # 如果提供了 emotion_seed，覆盖情绪强度
        if emotion_seed is not None:
            primary, _ = emotion_vector.get_primary()
            setattr(emotion_vector, primary, emotion_seed)

        # 2. 构建系统状态快照
        state = self._build_state_snapshot()

        # 3. Gate 生成 EmotionBias
        emotion_bias = self.gate.generate_emotion_bias(
            state=state,
            emotion_vector=emotion_vector
        )

        # 4. 使用 bias 驱动 ArtPipeline
        result = self.art_pipeline.run_with_bias(
            chat_messages,
            emotion_bias,
            user_feedback
        )

        return {
            "lyrics": result["lyrics"],
            "theme": result["theme"],
            "emotion": result["emotion_vector"].to_prompt_context(),
            "emotion_primary": result["emotion_vector"].get_primary(),
            "emotion_bias": emotion_bias,
            "bias_constraints": emotion_bias.to_art_constraints(),
            "imagery": result["imagery"],
            "generation_count": result["generation_count"],
            "system_health": state.compute_health()
        }

    def generate_diverse_versions(
        self,
        chat_messages: list,
        num_versions: int = 3,
        user_feedback: str = ""
    ) -> list:
        """
        同一聊天 → 不同 humanize_intensity → 不同歌词
        """
        results = []
        intensities = [0.0, 0.3, 0.6][:num_versions]

        for intensity in intensities:
            result = self.generate_lyrics(
                chat_messages,
                humanize_intensity=intensity,
                user_feedback=user_feedback
            )
            results.append(result)

        return results

    def _build_state_snapshot(self) -> StateSnapshot:
        """构建系统状态快照（用于生成 EmotionBias）"""
        builder = StateSnapshotBuilder()
        state = builder.build(
            self.kernel.engine.scheduler,
            self.kernel.engine.worker_pool,
            self.kernel.engine.cost_tracker
        )
        return state

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
