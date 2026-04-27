"""
v7.9 Agent OS - Emotion-Aware Enhanced OS + Human Rewrite Layer
==============================================================
Integration layer: AgentOSKernel + ArtPipeline + HookGenerator + HumanRewriteLayer
"""

from agent_os import AgentOSKernel, ExecutionGate, StateSnapshotBuilder, StateSnapshot
from agent_os.art_layer import (
    ArtPipeline, EmotionVector, LyricRhythmSpec, ChatCompressionLayer,
    StylePreset, EmotionCurve, HookGenerator, StylePresetLibrary, HumanRewriteLayer,
    AudioLayer, MelodyPlanner, PerformancePlanner, MelodyPlan, PerformancePlan,
    SongSynthesizer, PhonemeAligner, DiffSingerAdapter, DiffSingerRunner
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
        self.audio_layer = AudioLayer()  # v9.8: 歌词 → 有声作品
        self.melody_planner = MelodyPlanner()  # v9.9: 歌词 → 旋律 IR
        self.performance_planner = PerformancePlanner()  # v10: 旋律 IR → 表演 IR
        self.song_synthesizer = SongSynthesizer()  # v10: 表演 IR → 歌曲音频
        self.phoneme_aligner = PhonemeAligner()  # v11: 歌词 → 音素序列
        self.diff_singer_adapter = DiffSingerAdapter()  # v11: 表演 IR → DiffSinger 格式
        self.diff_singer_runner = DiffSingerRunner()  # v11: DiffSinger 模型推理
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

    def synthesize_audio(
        self,
        chat_messages: list,
        output_path: str = "output/song.mp3",
        humanize_intensity: float = 0.3,
    ) -> dict:
        """
        v9.8 主接口：歌词 → 有声作品

        完整pipeline：
        微信聊天 → 语义帧 → 歌词 → TTS + BGM → 音频文件

        Args:
            chat_messages: 聊天记录
            output_path: 输出音频文件路径
            humanize_intensity: 人类化强度

        Returns:
            dict: {
                "lyrics": 歌词文本,
                "audio_output": 音频文件路径,
                "duration_sec": 时长,
                "emotion": 主情绪,
                "note": 说明,
            }
        """
        # 1. 生成歌词
        lyric_result = self.generate_lyrics(
            chat_messages,
            humanize_intensity=humanize_intensity
        )

        if "error" in lyric_result:
            return lyric_result

        # 2. 解析歌词行
        lyric_lines = []
        raw_lyrics = lyric_result.get("lyrics", "")
        lines = raw_lyrics.split("\n")

        # 简单解析：根据【】判断段落
        current_section = "verse1"
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "【主歌1】" in line:
                current_section = "verse1"
            elif "【主歌2】" in line:
                current_section = "verse2"
            elif "【副歌】" in line or "【Hook】" in line:
                current_section = "hook"
            elif "【转折】" in line:
                current_section = "turning"
            elif "【开场】" in line:
                current_section = "intro"
            elif "【结尾】" in line:
                current_section = "outro"
            elif line.startswith("【") and line.endswith("】"):
                current_section = line[1:-1]
            else:
                lyric_lines.append((current_section, line))

        if not lyric_lines:
            return {"error": "No lyric lines parsed"}

        # 3. 获取情绪向量
        compression_result = self.compression.compress(chat_messages)
        emotion_vector = compression_result["emotion_vector"]

        # 4. 合成音频
        audio_result = self.audio_layer.synthesize(
            lyric_lines,
            emotion_vector,
            output_path=output_path,
        )

        return {
            "lyrics": lyric_result["lyrics"],
            "audio_output": audio_result.get("final_output"),
            "tts_files": audio_result.get("tts_files", []),
            "duration_sec": audio_result.get("duration_sec", 0),
            "emotion": audio_result.get("primary_emotion", "unknown"),
            "voice": audio_result.get("voice", "unknown"),
            "bgm_file": audio_result.get("bgm_file"),
            "note": audio_result.get("note", ""),
        }

    def synthesize_song(
        self,
        chat_messages: list,
        output_path: str = "output/song.mp3",
        humanize_intensity: float = 0.3,
    ) -> dict:
        """
        v10 主接口：微信聊天 → 完整歌曲

        完整 pipeline：
        微信聊天 → 语义帧 → 歌词 → MelodyPlan → PerformancePlan → 歌曲音频

        Args:
            chat_messages: 聊天记录
            output_path: 输出音频文件路径
            humanize_intensity: 人类化强度

        Returns:
            dict: {
                "lyrics": 歌词文本,
                "melody_plan": MelodyPlan,
                "performance_plan": PerformancePlan,
                "song_output": 歌曲文件路径,
                "duration_sec": 时长,
                "emotion": 主情绪,
            }
        """
        import os

        # 1. 生成歌词
        lyric_result = self.generate_lyrics(
            chat_messages,
            humanize_intensity=humanize_intensity
        )

        if "error" in lyric_result:
            return lyric_result

        # 2. 解析歌词行
        lyric_lines = []
        raw_lyrics = lyric_result.get("lyrics", "")
        lines = raw_lyrics.split("\n")

        current_section = "verse1"
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "【主歌1】" in line:
                current_section = "verse1"
            elif "【主歌2】" in line:
                current_section = "verse2"
            elif "【副歌】" in line or "【Hook】" in line:
                current_section = "hook"
            elif "【转折】" in line:
                current_section = "turning"
            elif "【开场】" in line:
                current_section = "intro"
            elif "【结尾】" in line:
                current_section = "outro"
            elif line.startswith("【") and line.endswith("】"):
                current_section = line[1:-1]
            else:
                lyric_lines.append((current_section, line))

        if not lyric_lines:
            return {"error": "No lyric lines parsed"}

        # 3. 获取情绪向量
        compression_result = self.compression.compress(chat_messages)
        emotion_vector = compression_result["emotion_vector"]

        # 4. 生成 MelodyPlan
        melody_plan = self.melody_planner.plan(lyric_lines, emotion_vector)

        # 5. 生成 PerformancePlan
        performance_plan = self.performance_planner.plan(melody_plan, emotion_vector)

        # 6. 合成歌曲
        os.makedirs(os.path.dirname(output_path) or "output", exist_ok=True)
        song_output = self.song_synthesizer.synthesize(performance_plan, emotion_vector, output_path)

        return {
            "lyrics": lyric_result["lyrics"],
            "melody_plan": melody_plan,
            "performance_plan": performance_plan,
            "song_output": song_output,
            "duration_sec": len(performance_plan.notes) * 0.5,
            "emotion": performance_plan.emotion,
            "key": melody_plan.key,
            "bpm": melody_plan.bpm,
        }

    def generate_singing_input(
        self,
        chat_messages: list,
        humanize_intensity: float = 0.3,
    ) -> dict:
        """
        v11 主接口：生成 DiffSinger / SVC 可用的输入格式

        完整 pipeline：
        微信聊天 → 歌词 → MelodyPlan → PerformancePlan → DiffSinger格式

        Args:
            chat_messages: 聊天记录
            humanize_intensity: 人类化强度

        Returns:
            dict: {
                "lyrics": 歌词文本,
                "model_input": {
                    "phonemes": [...],
                    "f0": [...],
                    "durations": [...],
                    "breathiness": [...],
                    "vibrato": [...],
                    "stress": [...],
                    "attack": [...],
                    "key": "A_minor",
                    "bpm": 70,
                },
                "ready_for_singing_model": True,
            }
        """
        # 1. 生成歌词
        lyric_result = self.generate_lyrics(
            chat_messages,
            humanize_intensity=humanize_intensity
        )

        if "error" in lyric_result:
            return lyric_result

        # 2. 解析歌词行
        lyric_lines = []
        raw_lyrics = lyric_result.get("lyrics", "")
        lines = raw_lyrics.split("\n")

        current_section = "verse1"
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "【主歌1】" in line:
                current_section = "verse1"
            elif "【主歌2】" in line:
                current_section = "verse2"
            elif "【副歌】" in line or "【Hook】" in line:
                current_section = "hook"
            elif "【转折】" in line:
                current_section = "turning"
            elif "【开场】" in line:
                current_section = "intro"
            elif "【结尾】" in line:
                current_section = "outro"
            elif line.startswith("【") and line.endswith("】"):
                current_section = line[1:-1]
            else:
                lyric_lines.append((current_section, line))

        if not lyric_lines:
            return {"error": "No lyric lines parsed"}

        # 3. 获取情绪向量
        compression_result = self.compression.compress(chat_messages)
        emotion_vector = compression_result["emotion_vector"]

        # 4. 生成 MelodyPlan
        melody_plan = self.melody_planner.plan(lyric_lines, emotion_vector)

        # 5. 生成 PerformancePlan
        performance_plan = self.performance_planner.plan(melody_plan, emotion_vector)

        # 6. 转换为 DiffSinger 输入格式
        model_input = self.diff_singer_adapter.adapt(performance_plan)

        return {
            "lyrics": lyric_result["lyrics"],
            "model_input": model_input,
            "ready_for_singing_model": True,
            "emotion": performance_plan.emotion,
            "key": melody_plan.key,
            "bpm": melody_plan.bpm,
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

    def sing(
        self,
        chat_messages: list,
        output_path: str = "output/song.wav",
        humanize_intensity: float = 0.3,
        use_singing_model: bool = True,
    ) -> dict:
        """
        v11 终极接口：微信聊天 → 真实唱歌

        完整 pipeline：
        微信聊天 → 歌词 → MelodyPlan → PerformancePlan → DiffSinger格式 → 真唱

        Args:
            chat_messages: 聊天记录
            output_path: 输出音频文件路径
            humanize_intensity: 人类化强度
            use_singing_model: 是否优先使用 DiffSinger（False 则降级到 TTS）

        Returns:
            dict: {
                "lyrics": 歌词文本,
                "melody_plan": MelodyPlan,
                "performance_plan": PerformancePlan,
                "model_input": DiffSinger 输入格式,
                "audio_output": 音频文件路径,
                "duration_sec": 时长,
                "emotion": 主情绪,
                "singing_model_used": 是否用了真唱模型,
            }
        """
        import os

        # 1. 生成歌词
        lyric_result = self.generate_lyrics(
            chat_messages,
            humanize_intensity=humanize_intensity
        )

        if "error" in lyric_result:
            return lyric_result

        # 2. 解析歌词行
        lyric_lines = self._parse_lyric_lines(lyric_result.get("lyrics", ""))

        if not lyric_lines:
            return {"error": "No lyric lines parsed"}

        # 3. 获取情绪向量
        compression_result = self.compression.compress(chat_messages)
        emotion_vector = compression_result["emotion_vector"]

        # 4. 生成 MelodyPlan
        melody_plan = self.melody_planner.plan(lyric_lines, emotion_vector)

        # 5. 生成 PerformancePlan
        performance_plan = self.performance_planner.plan(melody_plan, emotion_vector)

        # 6. 生成 DiffSinger 输入格式
        model_input = self.diff_singer_adapter.adapt(performance_plan)

        os.makedirs(os.path.dirname(output_path) or "output", exist_ok=True)

        audio_output = None
        singing_model_used = False

        if use_singing_model:
            # 7. 尝试 DiffSinger 真唱
            audio_output = self.diff_singer_runner.run_with_sing_model(
                model_input,
                os.path.dirname(output_path) or "output"
            )
            if audio_output and os.path.exists(audio_output):
                singing_model_used = True

        if not singing_model_used:
            # 8. 降级：使用 SongSynthesizer (pitch-shifted TTS)
            audio_output = self.song_synthesizer.synthesize(
                performance_plan,
                emotion_vector,
                output_path
            )

        return {
            "lyrics": lyric_result["lyrics"],
            "melody_plan": melody_plan,
            "performance_plan": performance_plan,
            "model_input": model_input,
            "audio_output": audio_output,
            "duration_sec": len(performance_plan.notes) * 0.5,
            "emotion": performance_plan.emotion,
            "key": melody_plan.key,
            "bpm": melody_plan.bpm,
            "singing_model_used": singing_model_used,
        }

    def _parse_lyric_lines(self, lyrics_text: str) -> list:
        """解析歌词文本为 (section, line) 列表"""
        lyric_lines = []
        lines = lyrics_text.split("\n")
        current_section = "verse1"

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "【主歌1】" in line:
                current_section = "verse1"
            elif "【主歌2】" in line:
                current_section = "verse2"
            elif "【副歌】" in line or "【Hook】" in line:
                current_section = "hook"
            elif "【转折】" in line:
                current_section = "turning"
            elif "【开场】" in line:
                current_section = "intro"
            elif "【结尾】" in line:
                current_section = "outro"
            elif line.startswith("【") and line.endswith("】"):
                current_section = line[1:-1]
            else:
                lyric_lines.append((current_section, line))

        return lyric_lines
