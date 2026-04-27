"""
v7.9 Agent OS - Emotion-Aware Enhanced OS + Human Rewrite Layer
==============================================================
Integration layer: AgentOSKernel + ArtPipeline + HookGenerator + HumanRewriteLayer
"""

from agent_os import AgentOSKernel, ExecutionGate, StateSnapshotBuilder, StateSnapshot
from agent_os.art_layer import (
    ArtPipeline, EmotionVector, LyricRhythmSpec, ChatCompressionLayer,
    StylePreset, StylePresetLibrary, EmotionCurve, HookGenerator, HumanRewriteLayer,
    AudioLayer, MelodyPlanner, PerformancePlanner, MelodyPlan, PerformancePlan,
    SongSynthesizer, PhonemeAligner, DiffSingerAdapter, DiffSingerRunner,
    StyleTemplate, get_style_template, STYLE_TEMPLATES
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

    # ==================== v12.0 多候选生成 + 排序 ====================

    def sing(
        self,
        chat_messages: list,
        output_path: str = "output/song.wav",
        humanize_intensity: float = 0.3,
        use_singing_model: bool = True,
        num_candidates: int = 3,
        style: str = None,
    ) -> dict:
        """
        v12.0 多候选生成接口

        一条输入 → 3~5首候选歌 → 排序/选择

        Args:
            chat_messages: 聊天记录
            output_path: 输出音频文件路径
            humanize_intensity: 人类化强度
            use_singing_model: 是否优先使用 DiffSinger
            num_candidates: 候选数量，默认3
            style: 风格预设（"douyin_sad" / "rap" / "emo_pop" / None=自动检测）

        Returns:
            dict: {
                "candidates": [result1, result2, ...],
                "best": result (最高分),
                "rank_scores": [score1, score2, ...],
            }
        """
        if num_candidates <= 1:
            # 单候选模式
            result = self._sing_once(
                chat_messages, output_path, humanize_intensity, use_singing_model
            )
            return {"candidates": [result], "best": result, "rank_scores": [self._score_result(result)]}

        # 多候选生成
        candidates = []
        for i in range(num_candidates):
            candidate_output = self._candidate_output_path(output_path, i)
            result = self._sing_once(
                chat_messages, candidate_output, humanize_intensity, use_singing_model, style
            )
            candidates.append(result)

        # 排序
        ranked = self._rank(candidates)

        return {
            "candidates": candidates,
            "best": ranked[0]["result"],
            "rank_scores": [r["score"] for r in ranked],
            "rank_details": ranked,
        }

    def _sing_once(
        self,
        chat_messages: list,
        output_path: str,
        humanize_intensity: float,
        use_singing_model: bool,
        style: str = None,
    ) -> dict:
        """
        单次生成（完整 pipeline）
        微信聊天 → 歌词 → MelodyPlan → PerformancePlan → 音频
        """
        import os

        # v12.2: 解析风格参数
        style_preset = None
        style_template = None
        if style:
            try:
                style_preset = StylePreset(style)
                style_template = get_style_template(style_preset)
            except ValueError:
                style_preset = None
                style_template = None

        # v12.2: 风格影响人类化强度和 BPM
        # 短视频风格需要更强人类化（更短更爆）
        if style_template:
            if style_template.expression == "direct":
                humanize_intensity = min(0.6, humanize_intensity + 0.2)
            elif style_template.expression == "self_mock":
                humanize_intensity = min(0.7, humanize_intensity + 0.3)

        # 1. 生成歌词（传入风格参数）
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

        # v12.2: 风格覆盖 BPM
        if style_template:
            melody_plan.bpm = style_template.bpm

        # 5. 生成 PerformancePlan
        performance_plan = self.performance_planner.plan(melody_plan, emotion_vector)

        # 6. 生成 DiffSinger 输入格式
        model_input = self.diff_singer_adapter.adapt(performance_plan)

        os.makedirs(os.path.dirname(output_path) or "output", exist_ok=True)

        audio_output = None
        singing_model_used = False

        if use_singing_model:
            audio_output = self.diff_singer_runner.run_with_sing_model(
                model_input,
                os.path.dirname(output_path) or "output"
            )
            if audio_output and os.path.exists(audio_output):
                singing_model_used = True

        if not singing_model_used:
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
            "style": style_preset.value if style_preset else None,
            "style_name": style_template.name if style_template else None,
            "raw_lyrics": lyric_result.get("raw_lyrics", ""),
            "hook": lyric_result.get("hook", ""),
            "hook_variants": lyric_result.get("hook_variants", []),
        }

    def _candidate_output_path(self, base_path: str, index: int) -> str:
        """生成候选输出路径"""
        import os
        folder = os.path.dirname(base_path) or "output"
        name = os.path.basename(base_path)
        stem, ext = os.path.splitext(name)
        return os.path.join(folder, f"{stem}_cand{index+1}{ext}")

    def _rank(self, candidates: list) -> list:
        """
        v12.0 排序：对候选结果打分并排序

        评分维度：
        - hook_strength (0.3): Hook行是否够"爆"
        - lyric_variation (0.2): 歌词是否有变化（不重复）
        - melody_jumpiness (0.2): 旋律是否有跳跃（避免平淡）
        - emotion_consistency (0.3): 情绪是否连贯

        Returns:
            list: [{result, score, details}, ...] 按分数降序
        """
        scored = []
        for result in candidates:
            score, details = self._score_result(result)
            scored.append({
                "result": result,
                "score": score,
                "details": details,
            })

        # 降序排列
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def _score_result(self, result: dict) -> tuple:
        """
        对单个结果打分

        Returns:
            (total_score, details_dict)
        """
        hook_strength = self._score_hook_strength(result)
        lyric_variation = self._score_lyric_variation(result)
        melody_jumpiness = self._score_melody_jumpiness(result)
        emotion_consistency = self._score_emotion_consistency(result)

        total = (
            hook_strength * 0.3 +
            lyric_variation * 0.2 +
            melody_jumpiness * 0.2 +
            emotion_consistency * 0.3
        )

        details = {
            "hook_strength": hook_strength,
            "lyric_variation": lyric_variation,
            "melody_jumpiness": melody_jumpiness,
            "emotion_consistency": emotion_consistency,
        }

        return total, details

    def _score_hook_strength(self, result: dict) -> float:
        """
        Hook 强度：Hook行是否够"爆"
        - 有 Hook 句子（0.3）
        - Hook 不在首尾位置（0.2）
        - Hook 长度 4-8 字（0.2）
        - Hook 包含感叹/疑问（0.3）
        """
        score = 0.0
        lyrics = result.get("lyrics", "")
        hook = result.get("hook", "")

        # 有 Hook
        if hook and len(hook) >= 2:
            score += 0.3

            # Hook 长度合适
            if 4 <= len(hook) <= 8:
                score += 0.2

            # Hook 包含感叹/疑问（情感强）
            if any(c in hook for c in "！？"):
                score += 0.3
            elif any(kw in hook for kw in ["懂了", "明白了", "算了", "知道了"]):
                score += 0.2

        # 检查 Hook 在歌词中的位置（应该在中间而非首尾）
        hook_lines = [l for l in lyrics.split("\n") if "hook" in l.lower() or "【Hook】" in l]
        if hook_lines:
            all_lines = lyrics.split("\n")
            non_empty = [l for l in all_lines if l.strip() and not l.startswith("【")]
            if non_empty:
                hook_idx = next((i for i, l in enumerate(non_empty)
                                if any(kw in l for kw in ["hook", "Hook", "【Hook】"])), -1)
                if 0 < hook_idx < len(non_empty) - 1:
                    score += 0.2  # Hook 不在首尾

        return min(1.0, score)

    def _score_lyric_variation(self, result: dict) -> float:
        """
        歌词变化：句子长度方差、句式多样性
        - 句子长度有变化（0.4）
        - 句式不重复（0.3）
        - 有情绪转折（0.3）
        """
        lyrics = result.get("lyrics", "")
        lines = [l.strip() for l in lyrics.split("\n")
                 if l.strip() and not l.startswith("【")]

        if len(lines) < 2:
            return 0.0

        score = 0.0

        # 句子长度有变化
        lengths = [len(l) for l in lines]
        if len(set(lengths)) > 1:
            variance = sum((l - sum(lengths)/len(lengths))**2 for l in lengths) / len(lengths)
            if variance > 4:  # 有一定方差
                score += 0.4

        # 句式不重复（检查开头词）
        start_words = set()
        for line in lines:
            for w in ["我", "你", "他", "她", "它", "这", "那", "不是", "其实", "算了"]:
                if line.startswith(w):
                    start_words.add(w)
                    break

        if len(start_words) >= 3:
            score += 0.3
        elif len(start_words) >= 2:
            score += 0.15

        # 有情绪转折
        turning_keywords = ["但", "只是", "其实", "不过", "然而"]
        has_turning = any(any(kw in l for kw in turning_keywords) for l in lines)
        if has_turning:
            score += 0.3

        return min(1.0, score)

    def _score_melody_jumpiness(self, result: dict) -> float:
        """
        旋律跳跃：音程变化、节奏变化
        - 音程变化大（0.4）
        - 节奏有变化（0.3）
        - 有 REST 呼吸点（0.3）
        """
        melody_plan = result.get("melody_plan")
        if not melody_plan or not hasattr(melody_plan, "notes"):
            return 0.5  # 默认中间值

        notes = melody_plan.notes
        if len(notes) < 3:
            return 0.5

        score = 0.0

        # 音程变化
        pitch_freq = {
            "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23,
            "G4": 392.00, "A4": 440.00, "B4": 493.88,
            "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46,
            "G5": 783.99, "A5": 880.00, "B5": 987.77,
        }
        intervals = []
        prev_freq = None
        for n in notes:
            if n.pitch == "REST" or n.pitch not in pitch_freq:
                continue
            freq = pitch_freq[n.pitch]
            if prev_freq is not None:
                intervals.append(abs(freq - prev_freq))
            prev_freq = freq

        if intervals:
            avg_interval = sum(intervals) / len(intervals)
            if avg_interval > 80:  # 平均音程超过半音
                score += 0.4
            elif avg_interval > 40:
                score += 0.2

        # 节奏有变化（非均匀）
        durations = [n.duration for n in notes if n.pitch != "REST"]
        if durations and len(set(durations)) > 1:
            score += 0.3

        # 有 REST 呼吸点
        rest_count = sum(1 for n in notes if n.pitch == "REST")
        if rest_count > 0:
            score += 0.3

        return min(1.0, score)

    def _score_emotion_consistency(self, result: dict) -> float:
        """
        情绪连贯：emotion 在 lyrics 中有呼应
        - 关键词和 emotion 一致（0.5）
        - 歌词覆盖情绪词（0.5）
        """
        emotion = result.get("emotion", "")
        lyrics = result.get("lyrics", "").lower()

        score = 0.0

        # 情绪关键词映射
        emotion_keywords = {
            "sadness": ["难过", "不回", "算了", "远了", "回不去", "忘"],
            "nostalgia": ["以前", "曾经", "那年", "记得", "小时候"],
            "anger": ["凭什么", "为什么", "太过分", "不公平"],
            "joy": ["开心", "快乐", "幸福", "美好"],
            "warmth": ["温暖", "谢谢", "想见", "抱抱"],
            "hope": ["会", "能", "相信", "希望"],
            "loneliness": ["一个人", "孤独", "没人", "寂寞"],
        }

        keywords = emotion_keywords.get(emotion, [])
        if keywords:
            matched = sum(1 for kw in keywords if kw in lyrics)
            score = min(0.5, matched * 0.15)

        # 检查 raw_lyrics 也有情绪词
        raw_lyrics = result.get("raw_lyrics", "").lower()
        if raw_lyrics and keywords:
            matched_raw = sum(1 for kw in keywords if kw in raw_lyrics)
            score += min(0.5, matched_raw * 0.15)

        return min(1.0, max(0.0, score))
