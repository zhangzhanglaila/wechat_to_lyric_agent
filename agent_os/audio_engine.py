"""
Audio Engine - MIDI合成 + TTS人声 + 混音引擎

三层回退策略确保Windows兼容：
1. FluidSynth + Soundfont（最佳音质）
2. pretty_midi 内置合成（中等音质）
3. numpy 波形合成（保底，总能用）
"""
import os
import re
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import List, Optional

import numpy as np

from agent_os.melody_generator import MelodySpec, NoteSpec, pitch_to_midi

logger = logging.getLogger(__name__)

# ==================== 配置 ====================

SOUNDFONT_URL = "https://www.synthfont.com/TimGM6mb.sf2"
DEFAULT_SOUNDFONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "soundfonts", "TimGM6mb.sf2"
)
SING_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "output", "sing"
)

# TTS声音映射 — XiaoxiaoNeural（清晰明亮，音量最大）
TTS_VOICE_MAP = {
    "sad": "zh-CN-XiaoxiaoNeural",
    "nostalgic": "zh-CN-XiaoxiaoNeural",
    "joy": "zh-CN-XiaoxiaoNeural",
    "anger": "zh-CN-YunyangNeural",
    "warmth": "zh-CN-XiaoxiaoNeural",
    "loneliness": "zh-CN-XiaoxiaoNeural",
    "hope": "zh-CN-XiaoxiaoNeural",
    "regret": "zh-CN-XiaoxiaoNeural",
    "default": "zh-CN-XiaoxiaoNeural",
}

# 风格→TTS参数（rate必须>=+10%，不能用负数会太慢）
STYLE_TTS_PARAMS = {
    "douyin_sad": {"rate": "+15%"},
    "rap": {"rate": "+30%"},
    "emo_pop": {"rate": "+20%"},
    "heartbreak": {"rate": "+10%"},
    "folk": {"rate": "+10%"},
    "jay_chou": {"rate": "+15%"},
    "pop": {"rate": "+20%"},
    "default": {"rate": "+15%"},
}


def _ensure_output_dir():
    os.makedirs(SING_OUTPUT_DIR, exist_ok=True)


# ==================== MIDI合成器 ====================

class MidiSynthesizer:
    """旋律→MIDI文件→音频"""

    @staticmethod
    def melody_to_midi(melody: MelodySpec, output_path: str) -> str:
        """将旋律转为MIDI文件"""
        import mido

        mid = mido.MidiFile()
        track = mido.MidiTrack()
        mid.tracks.append(track)

        # 设置 tempo
        tempo = mido.bpm2tempo(melody.bpm)
        track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

        # 设置乐器 (Acoustic Grand Piano)
        track.append(mido.Message("program_change", program=0, channel=0, time=0))

        # 计算 ticks per beat
        ticks_per_beat = mid.ticks_per_beat

        for note in melody.notes:
            if note.is_rest:
                # 休止符：用 ticks 表示时值
                ticks = int(note.duration * ticks_per_beat)
                # 添加一个极低音量的静音事件来占时间
                track.append(mido.Message("note_on", note=0, velocity=0, channel=0, time=ticks))
                track.append(mido.Message("note_off", note=0, velocity=0, channel=0, time=0))
            else:
                midi_num = pitch_to_midi(note.pitch)
                ticks = int(note.duration * ticks_per_beat)
                track.append(mido.Message("note_on", note=midi_num, velocity=80, channel=0, time=0))
                track.append(mido.Message("note_off", note=midi_num, velocity=0, channel=0, time=ticks))

        # 添加伴奏声部（简单的和弦根音低音）
        bass_track = mido.MidiTrack()
        mid.tracks.append(bass_track)
        bass_track.append(mido.Message("program_change", program=32, channel=1, time=0))  # Acoustic Bass

        from agent_os.melody_generator import CHORD_PROGRESSIONS, SCALES
        chords = CHORD_PROGRESSIONS.get(melody.key, CHORD_PROGRESSIONS["C_major"])

        total_beats = sum(n.duration for n in melody.notes)
        beat = 0
        chord_idx = 0
        bar_duration = 4.0  # 4/4 拍

        while beat < total_beats:
            root = chords[chord_idx % len(chords)]
            bass_note = root - 12  # 低八度
            if bass_note < 28:
                bass_note = root

            duration = min(bar_duration, total_beats - beat)
            ticks = int(duration * ticks_per_beat)

            bass_track.append(mido.Message("note_on", note=bass_note, velocity=50, channel=1, time=0))
            bass_track.append(mido.Message("note_off", note=bass_note, velocity=0, channel=1, time=ticks))

            beat += bar_duration
            chord_idx += 1

        mid.save(output_path)
        return output_path

    @staticmethod
    def midi_to_audio(midi_path: str, output_path: str, soundfont: str = "") -> str:
        """
        MIDI转音频，三级回退策略。
        """
        sf_path = soundfont or os.getenv("SOUNDFONT_PATH", DEFAULT_SOUNDFONT_PATH)

        # 策略1: FluidSynth + Soundfont
        try:
            return MidiSynthesizer._synth_with_fluidsynth(midi_path, output_path, sf_path)
        except Exception as e:
            logger.warning(f"FluidSynth合成失败: {e}, 尝试pretty_midi...")

        # 策略2: pretty_midi 内置合成
        try:
            return MidiSynthesizer._synth_with_pretty_midi(midi_path, output_path)
        except Exception as e:
            logger.warning(f"pretty_midi合成失败: {e}, 回退到numpy波形...")

        # 策略3: numpy波形合成（保底）
        return MidiSynthesizer._synth_with_numpy(midi_path, output_path)

    @staticmethod
    def _synth_with_fluidsynth(midi_path: str, output_path: str, soundfont: str) -> str:
        """策略1: FluidSynth"""
        import pretty_midi
        if not os.path.exists(soundfont):
            raise FileNotFoundError(f"Soundfont not found: {soundfont}")

        midi = pretty_midi.PrettyMIDI(midi_path)
        audio = midi.fluidsynth(fs=22050, sf2_path=soundfont)

        # 保存为WAV
        wav_path = output_path.replace(".mp3", ".wav")
        MidiSynthesizer._save_wav(audio, wav_path, 22050)
        return wav_path

    @staticmethod
    def _synth_with_pretty_midi(midi_path: str, output_path: str) -> str:
        """策略2: pretty_midi 内置合成（无soundfont，用内置波形）"""
        import pretty_midi

        midi = pretty_midi.PrettyMIDI(midi_path)
        # pretty_midi.synthesize() 使用内置的简单合成器
        audio = midi.synthesize(fs=22050)

        wav_path = output_path.replace(".mp3", ".wav")
        MidiSynthesizer._save_wav(audio, wav_path, 22050)
        return wav_path

    @staticmethod
    def _synth_with_numpy(midi_path: str, output_path: str) -> str:
        """策略3: 纯numpy波形合成（三角波+简单包络）"""
        import mido

        mid = mido.MidiFile(midi_path)
        sample_rate = 22050

        # 收集所有音符事件
        events = []
        current_time = 0.0
        tempo = 500000  # 默认120BPM

        for track in mid.tracks:
            current_time = 0.0
            for msg in track:
                ticks = msg.time
                current_time += mido.tick2second(ticks, mid.ticks_per_beat, tempo)

                if msg.type == "set_tempo":
                    tempo = msg.tempo
                elif msg.type == "note_on" and msg.velocity > 0:
                    events.append(("on", current_time, msg.note, msg.velocity))
                elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                    events.append(("off", current_time, msg.note, 0))

        # 计算总时长
        if not events:
            total_time = 1.0
        else:
            total_time = max(e[1] for e in events) + 0.5

        total_samples = int(total_time * sample_rate)
        audio = np.zeros(total_samples, dtype=np.float64)

        # 合成每个音符
        active_notes = {}
        for event_type, time, note, vel in sorted(events, key=lambda x: x[1]):
            sample_idx = int(time * sample_rate)

            if event_type == "on":
                active_notes[note] = (sample_idx, vel)
            elif event_type == "off" and note in active_notes:
                start_idx, velocity = active_notes.pop(note)
                end_idx = sample_idx

                if end_idx > start_idx:
                    duration = end_idx - start_idx
                    t = np.arange(duration) / sample_rate
                    freq = 440.0 * (2.0 ** ((note - 69) / 12.0))

                    # 三角波（比正弦波更温暖）
                    wave = np.abs(2.0 * (t * freq - np.floor(t * freq + 0.5))) * 2.0 - 1.0

                    # ADSR 包络
                    attack = min(int(0.01 * sample_rate), duration // 4)
                    release = min(int(0.05 * sample_rate), duration // 4)
                    envelope = np.ones(duration)
                    if attack > 0:
                        envelope[:attack] = np.linspace(0, 1, attack)
                    if release > 0:
                        envelope[-release:] = np.linspace(1, 0, release)

                    vol = velocity / 127.0 * 0.3
                    audio[start_idx:end_idx] += wave * envelope * vol

        # 归一化
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val * 0.8

        wav_path = output_path.replace(".mp3", ".wav")
        MidiSynthesizer._save_wav(audio, wav_path, sample_rate)
        return wav_path

    @staticmethod
    def _save_wav(audio: np.ndarray, path: str, sample_rate: int):
        """保存为WAV文件"""
        import wave
        import struct

        audio_16bit = (audio * 32767).astype(np.int16)

        with wave.open(path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_16bit.tobytes())


# ==================== TTS人声生成器（逐字+音高匹配） ====================

class VocalGenerator:
    """歌词→edge-tts人声，逐字生成+音高匹配旋律"""

    @staticmethod
    def _get_voice(emotion: str, voice_override: str = "") -> str:
        if voice_override:
            return voice_override
        for key, voice in TTS_VOICE_MAP.items():
            if key in emotion.lower():
                return voice
        return TTS_VOICE_MAP["default"]

    @staticmethod
    def _get_tts_params(style: str) -> dict:
        for key, params in STYLE_TTS_PARAMS.items():
            if key in style.lower():
                return params
        return STYLE_TTS_PARAMS["default"]

    @staticmethod
    async def generate_vocal_line(text: str, voice: str, rate: str, pitch: str, output_path: str) -> str:
        """为一行歌词生成TTS音频（非SSML模式）"""
        import edge_tts
        if not text.strip():
            return ""
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(output_path)
        return output_path

    @staticmethod
    def _midi_to_pitch_str(midi_note: int, tts_natural_hz: float = 250.0) -> str:
        """MIDI音高转edge-tts pitch参数（Hz偏移）"""
        if midi_note <= 0:
            return "+0Hz"
        # MIDI → Hz: A4(69)=440Hz
        target_hz = 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
        offset = target_hz - tts_natural_hz
        # 限制范围，避免极端失真
        offset = max(-100, min(150, offset))
        return f"{offset:+.0f}Hz"

    @staticmethod
    def _generate_synth_note(frequency: float, duration: float, sr: int = 24000,
                              formant_freq: float = 800.0, vibrato_depth: float = 0.02) -> np.ndarray:
        """
        生成单个合成音符（波表+共振峰+颤音）

        Args:
            frequency: 基频频率 (Hz)
            duration: 时长 (秒)
            sr: 采样率
            formant_freq: 共振峰频率 (Hz)
            vibrato_depth: 颤音深度 (0-0.1)
        """
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        # 基频 + 泛音（模拟人声的谐波结构）
        signal = np.sin(2 * np.pi * frequency * t)  # 基频
        signal += 0.5 * np.sin(2 * np.pi * 2 * frequency * t)  # 2次谐波
        signal += 0.25 * np.sin(2 * np.pi * 3 * frequency * t)  # 3次谐波
        signal += 0.125 * np.sin(2 * np.pi * 4 * frequency * t)  # 4次谐波

        # 颤音（vibrato）
        vibrato = 1 + vibrato_depth * np.sin(2 * np.pi * 5 * t)  # 5Hz颤音
        signal = signal * vibrato

        # 共振峰滤波（简化版 - 用带通滤波模拟）
        # 人声共振峰：F1≈500Hz, F2≈1500Hz, F2≈2500Hz
        formant1 = np.sin(2 * np.pi * formant_freq * t)
        formant2 = np.sin(2 * np.pi * (formant_freq * 2) * t)
        signal = signal * 0.7 + formant1 * 0.2 + formant2 * 0.1

        # 包络（ADSR）
        attack = int(0.05 * sr)  # 50ms attack
        decay = int(0.1 * sr)  # 100ms decay
        release = int(0.1 * sr)  # 100ms release

        envelope = np.ones(len(signal))
        # Attack
        if attack > 0:
            envelope[:attack] = np.linspace(0, 1, attack)
        # Decay
        if decay > 0:
            envelope[attack:attack+decay] = np.linspace(1, 0.8, decay)
        # Release
        if release > 0 and release < len(envelope):
            envelope[-release:] = np.linspace(0.8, 0, release)

        signal = signal * envelope

        # 归一化
        max_val = np.max(np.abs(signal))
        if max_val > 0:
            signal = signal / max_val * 0.8

        return signal

    @staticmethod
    async def generate_synth_singing(melody, lyrics: str, emotion: str, style: str,
                                      voice_override: str = "", output_dir: str = "") -> str:
        """
        合成歌声（v13 - 波表合成+共振峰+颤音）。

        核心策略：
        1. 每个音符生成对应频率的合成波形
        2. 应用共振峰滤波模拟人声
        3. 添加颤音（vibrato）增加自然感
        4. 按歌词顺序拼接音符

        效果：类似电子合成器的"歌唱"，有明确的音高变化
        """
        import wave

        if not output_dir:
            output_dir = tempfile.mkdtemp(prefix="sing_synth_")

        sr = 24000

        # 去掉结构标记，提取歌词
        raw_lines = [line.strip() for line in lyrics.split("\n") if line.strip()]
        clean_text = ""
        for line in raw_lines:
            clean = re.sub(r"[【\[][^】\]]*[】\]]", "", line).strip()
            if clean:
                clean_text += clean

        if not clean_text:
            raise ValueError("没有有效歌词")

        # 提取所有字符
        chars = [c for c in clean_text if c.strip() and c not in '，。！？、；：""''…— ']

        # 为每个字符分配音符
        all_segments = []
        note_idx = 0

        for char in chars:
            if note_idx >= len(melody.notes):
                break

            note = melody.notes[note_idx]
            note_idx += 1

            # 跳过休止符
            while note_idx < len(melody.notes) and note.is_rest:
                note = melody.notes[note_idx]
                note_idx += 1

            if note.is_rest:
                continue

            # 计算频率
            if isinstance(note.pitch, str):
                midi_num = pitch_to_midi(note.pitch)
            else:
                midi_num = note.pitch

            if midi_num <= 0:
                continue

            frequency = 440.0 * (2.0 ** ((midi_num - 69) / 12.0))

            # 计算时长
            beat_duration = 60.0 / melody.bpm
            note_duration = note.duration * beat_duration

            # 生成合成音符
            synth_note = VocalGenerator._generate_synth_note(
                frequency, note_duration, sr,
                formant_freq=800 + (midi_num - 60) * 10,  # 共振峰随音高变化
                vibrato_depth=0.03
            )

            all_segments.append(synth_note)

            # 添加小间隔
            gap = np.zeros(int(0.02 * sr))
            all_segments.append(gap)

        if not all_segments:
            raise ValueError("没有生成有效的合成音符")

        # 拼接所有音符
        combined = np.concatenate(all_segments)

        # 添加整体包络
        fade_in = int(0.1 * sr)
        fade_out = int(0.2 * sr)
        if fade_in > 0:
            combined[:fade_in] *= np.linspace(0, 1, fade_in)
        if fade_out > 0:
            combined[-fade_out:] *= np.linspace(1, 0, fade_out)

        # 归一化
        max_val = np.max(np.abs(combined))
        if max_val > 0:
            combined = combined / max_val * 0.85

        # 保存WAV
        output_path = os.path.join(output_dir, "synth_singing.wav")
        audio_16bit = (combined * 32767).astype(np.int16)
        with wave.open(output_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(audio_16bit.tobytes())

        return output_path

    @staticmethod
    async def generate_singing_vocals(melody, lyrics: str, emotion: str, style: str,
                                       voice_override: str = "", output_dir: str = "") -> str:
        """
        逐行TTS + 行平均pitch + 按音符比例切片（v12 - 快速+有调子+BGM）。

        核心策略：
        1. 每行一次TTS，用该行音符的平均MIDI音高设置native pitch
        2. 按音符时长比例切片（不拉伸）
        3. XiaoxiaoNeural（最清晰明亮的中文女声）
        """
        import wave

        if not output_dir:
            output_dir = tempfile.mkdtemp(prefix="sing_vocal_")

        voice = VocalGenerator._get_voice(emotion, voice_override)
        params = VocalGenerator._get_tts_params(style)
        rate = params.get("rate", "+0%")
        sr = 24000

        # 去掉结构标记，提取歌词行
        raw_lines = [line.strip() for line in lyrics.split("\n") if line.strip()]
        clean_lines = []
        for line in raw_lines:
            clean = re.sub(r"[【\[][^】\]]*[】\]]", "", line).strip()
            if clean:
                clean_lines.append(clean)

        if not clean_lines:
            raise ValueError("没有有效歌词行")

        # 分配音符到行
        note_idx = 0
        line_note_map = {}
        for line_i, line in enumerate(clean_lines):
            line_chars = list(line)
            line_notes = []
            char_i = 0
            while note_idx < len(melody.notes) and char_i < len(line_chars):
                note = melody.notes[note_idx]
                note_idx += 1
                if note.is_rest:
                    continue
                if note.lyric:
                    line_notes.append(note)
                    if note.lyric in line_chars[char_i:]:
                        char_i = line_chars.index(note.lyric, char_i) + 1
                else:
                    line_notes.append(note)
                    char_i += 1
            line_note_map[line_i] = line_notes

        all_line_segments = []

        for line_i, line in enumerate(clean_lines):
            line_notes = line_note_map.get(line_i, [])
            active_notes = [n for n in line_notes if not n.is_rest]
            if not active_notes:
                continue

            active_beats = sum(n.duration for n in active_notes)

            # 计算该行的平均MIDI音高
            midi_values = []
            for note in active_notes:
                midi_num = pitch_to_midi(note.pitch) if isinstance(note.pitch, str) else note.pitch
                if midi_num > 0:
                    midi_values.append(midi_num)

            if midi_values:
                avg_midi = sum(midi_values) / len(midi_values)
                pitch_str = VocalGenerator._midi_to_pitch_str(int(avg_midi))
            else:
                pitch_str = "+0Hz"

            # 用native pitch生成TTS
            tts_path = os.path.join(output_dir, f"line_{line_i:02d}.mp3")
            try:
                from pydub import AudioSegment
                await VocalGenerator.generate_vocal_line(line, voice, rate, pitch_str, tts_path)
                seg = AudioSegment.from_file(tts_path)
                line_audio = np.array(seg.get_array_of_samples(), dtype=np.float64) / 32768.0
                if seg.frame_rate != sr:
                    indices = np.linspace(0, len(line_audio) - 1, int(len(line_audio) * sr / seg.frame_rate))
                    line_audio = np.interp(indices, np.arange(len(line_audio)), line_audio)

                # 裁剪首尾静音
                line_audio = VocalGenerator._trim_silence(line_audio, sr, threshold=0.01, keep_ms=10)
            except Exception as e:
                logger.warning(f"TTS行生成失败 ({line}): {e}")
                continue

            if len(line_audio) < sr * 0.1:
                logger.warning(f"TTS太短 ({len(line_audio)/sr:.2f}s), 跳过")
                continue

            logger.info(f"Line {line_i}: tts={len(line_audio)/sr:.2f}s, pitch={pitch_str}, notes={len(active_notes)}")

            # 按音符时长比例切片
            total_tts = len(line_audio)
            note_segments = []
            cursor = 0

            for note in active_notes:
                note_ratio = note.duration / active_beats
                note_len = max(1, int(note_ratio * total_tts))
                end = min(cursor + note_len, total_tts)

                seg_chunk = line_audio[cursor:end]
                if len(seg_chunk) > 0:
                    note_segments.append(seg_chunk)

                cursor = end

            if cursor < total_tts and note_segments:
                note_segments[-1] = np.concatenate([note_segments[-1], line_audio[cursor:]])

            if note_segments:
                line_output = VocalGenerator._crossfade_segments(note_segments, sr, crossfade_ms=15)

                max_val = np.max(np.abs(line_output))
                if max_val > 0:
                    line_output = line_output / max_val * 0.85

                all_line_segments.append(line_output)
                all_line_segments.append(np.zeros(int(0.1 * sr)))

        if not all_line_segments:
            raise ValueError("没有生成有效的人声音频")

        combined = np.concatenate(all_line_segments)

        max_val = np.max(np.abs(combined))
        if max_val > 0:
            combined = combined / max_val * 0.85

        # 保存WAV
        output_path = os.path.join(output_dir, "vocal_combined.wav")
        audio_16bit = (combined * 32767).astype(np.int16)
        with wave.open(output_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(audio_16bit.tobytes())

        return output_path

    @staticmethod
    def _crossfade_segments(segments: list, sr: int, crossfade_ms: int = 15) -> np.ndarray:
        """交叉淡化拼接音频片段"""
        if not segments:
            return np.array([], dtype=np.float64)
        if len(segments) == 1:
            return segments[0].copy()

        crossfade_samples = int(crossfade_ms / 1000.0 * sr)
        crossfade_samples = max(1, crossfade_samples)

        # 先拼接所有片段，然后在边界处做交叉淡化
        output = segments[0].copy()

        for i in range(1, len(segments)):
            seg = segments[i]
            if len(seg) == 0:
                continue

            # 交叉淡化区域
            cf = min(crossfade_samples, len(output) // 2, len(seg) // 2)
            if cf < 1:
                output = np.concatenate([output, seg])
                continue

            # 提取重叠区域
            overlap_out = output[-cf:].copy()
            overlap_seg = seg[:cf].copy()

            # 淡出 + 淡入
            fade_out = np.linspace(1, 0, cf)
            fade_in = np.linspace(0, 1, cf)

            blended = overlap_out * fade_out + overlap_seg * fade_in

            # 拼接：output去掉尾部cf个样本 + blended + seg剩余部分
            output = np.concatenate([output[:-cf], blended, seg[cf:]])

        return output

    @staticmethod
    def _trim_silence(audio: np.ndarray, sr: int, threshold: float = 0.005, keep_ms: int = 50) -> np.ndarray:
        """裁剪首尾静音，保留少量淡入淡出"""
        if len(audio) < sr // 10:
            return audio

        # 找到第一个有声帧
        frame_size = int(0.02 * sr)  # 20ms帧
        start = 0
        for i in range(0, len(audio) - frame_size, frame_size):
            rms = np.sqrt(np.mean(audio[i:i + frame_size] ** 2))
            if rms > threshold:
                start = max(0, i - frame_size)
                break

        # 找到最后一个有声帧
        end = len(audio)
        for i in range(len(audio) - frame_size, 0, -frame_size):
            rms = np.sqrt(np.mean(audio[i:i + frame_size] ** 2))
            if rms > threshold:
                end = min(len(audio), i + frame_size * 2)
                break

        if end <= start:
            return audio

        # 保留少量边距
        keep_samples = int(keep_ms / 1000.0 * sr)
        start = max(0, start - keep_samples)
        end = min(len(audio), end + keep_samples)

        return audio[start:end]

    @staticmethod
    def _detect_frame_pitch(frame: np.ndarray, sr: int) -> float:
        """单帧基频检测（用于PSOLA回退）"""
        if len(frame) < sr // 40:
            return 0.0
        emphasized = np.append(frame[0], frame[1:] - 0.97 * frame[:-1])
        windowed = emphasized * np.hanning(len(emphasized))
        corr = np.correlate(windowed, windowed, mode='full')
        corr = corr[len(corr) // 2:]
        min_lag = int(sr / 500)
        max_lag = min(int(sr / 80), len(corr) - 1)
        if max_lag <= min_lag:
            return 0.0
        search = corr[min_lag:max_lag]
        if len(search) == 0:
            return 0.0
        peak_idx = np.argmax(search) + min_lag
        if peak_idx == 0 or corr[peak_idx] < 0.2 * corr[0]:
            return 0.0
        return sr / peak_idx


# ==================== 音频混音器 ====================

class AudioMixer:
    """伴奏+人声混音"""

    @staticmethod
    def mix(instrumental_path: str, vocal_paths: List[str], output_path: str,
            instrumental_volume: float = 0.4, vocal_volume: float = 0.8,
            gap_between_lines: int = 300) -> str:
        """
        混合伴奏和人声。

        Args:
            instrumental_path: 伴奏音频路径
            vocal_paths: 人声音频路径列表
            output_path: 输出路径
            instrumental_volume: 伴奏音量 (0.0-1.0)
            vocal_volume: 人声音量 (0.0-1.0)
            gap_between_lines: 行间静音（毫秒）
        """
        from pydub import AudioSegment

        # 加载伴奏
        if instrumental_path.endswith(".wav"):
            instrumental = AudioSegment.from_wav(instrumental_path)
        else:
            instrumental = AudioSegment.from_file(instrumental_path)

        # 调整伴奏音量
        instrumental = instrumental + (20 * np.log10(instrumental_volume + 0.001))

        # 拼接人声
        vocal_combined = AudioSegment.empty()
        for i, vp in enumerate(vocal_paths):
            if not vp or not os.path.exists(vp):
                continue
            try:
                segment = AudioSegment.from_file(vp)
                segment = segment + (20 * np.log10(vocal_volume + 0.001))
                vocal_combined += segment
                if i < len(vocal_paths) - 1:
                    vocal_combined += AudioSegment.silent(duration=gap_between_lines)
            except Exception as e:
                logger.warning(f"加载人声片段失败 {vp}: {e}")

        if len(vocal_combined) == 0:
            # 没有人声，直接输出伴奏
            instrumental.export(output_path, format="wav")
            return output_path

        # 确保伴奏不短于人声
        if len(instrumental) < len(vocal_combined):
            # 循环伴奏
            repeats = len(vocal_combined) // len(instrumental) + 1
            instrumental = instrumental * repeats

        # 截取到人声长度
        instrumental = instrumental[:len(vocal_combined)]

        # 混音
        mixed = instrumental.overlay(vocal_combined)

        # 导出
        if output_path.endswith(".mp3"):
            try:
                mixed.export(output_path, format="mp3", bitrate="192k")
            except Exception:
                # ffmpeg不可用，回退到WAV
                output_path = output_path.replace(".mp3", ".wav")
                mixed.export(output_path, format="wav")
        else:
            mixed.export(output_path, format="wav")

        return output_path

    @staticmethod
    def vocal_only(vocal_paths: List[str], output_path: str,
                   vocal_volume: float = 0.8, gap_between_lines: int = 300) -> str:
        """纯人声拼接"""
        from pydub import AudioSegment

        combined = AudioSegment.empty()
        for i, vp in enumerate(vocal_paths):
            if not vp or not os.path.exists(vp):
                continue
            try:
                segment = AudioSegment.from_file(vp)
                segment = segment + (20 * np.log10(vocal_volume + 0.001))
                combined += segment
                if i < len(vocal_paths) - 1:
                    combined += AudioSegment.silent(duration=gap_between_lines)
            except Exception as e:
                logger.warning(f"加载人声片段失败 {vp}: {e}")

        if len(combined) == 0:
            raise ValueError("没有有效的人声音频")

        if output_path.endswith(".mp3"):
            try:
                combined.export(output_path, format="mp3", bitrate="192k")
            except Exception:
                output_path = output_path.replace(".mp3", ".wav")
                combined.export(output_path, format="wav")
        else:
            combined.export(output_path, format="wav")

        return output_path


# ==================== Soundfont管理 ====================

def ensure_soundfont() -> str:
    """确保soundfont文件存在，不存在则下载"""
    import urllib.request

    sf_path = os.getenv("SOUNDFONT_PATH", DEFAULT_SOUNDFONT_PATH)
    if os.path.exists(sf_path):
        # 验证文件是否是有效的SF2（以RIFF开头）
        try:
            with open(sf_path, 'rb') as f:
                header = f.read(4)
            if header == b'RIFF':
                return sf_path
            else:
                logger.warning(f"Soundfont文件无效（不是SF2格式），重新下载")
                os.remove(sf_path)
        except Exception:
            pass

    os.makedirs(os.path.dirname(sf_path), exist_ok=True)
    logger.info(f"下载Soundfont: {SOUNDFONT_URL}")
    try:
        urllib.request.urlretrieve(SOUNDFONT_URL, sf_path)
        # 验证下载的文件
        with open(sf_path, 'rb') as f:
            header = f.read(4)
        if header != b'RIFF':
            logger.warning(f"下载的文件不是有效的SF2格式")
            os.remove(sf_path)
            return ""
        logger.info(f"Soundfont已保存: {sf_path}")
        return sf_path
    except Exception as e:
        logger.warning(f"Soundfont下载失败: {e}")
        return ""


# ==================== 清理工具 ====================

def cleanup_temp_files(paths: List[str]):
    """清理临时文件"""
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
