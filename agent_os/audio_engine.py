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

SOUNDFONT_URL = "https://github.com/urish/cinto/raw/master/media/TimGM6mb.sf2"
DEFAULT_SOUNDFONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "soundfonts", "TimGM6mb.sf2"
)
SING_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "output", "sing"
)

# TTS声音映射
TTS_VOICE_MAP = {
    "sad": "zh-CN-XiaoyiNeural",
    "nostalgic": "zh-CN-XiaoyiNeural",
    "joy": "zh-CN-YunxiNeural",
    "anger": "zh-CN-YunyangNeural",
    "warmth": "zh-CN-XiaoyiNeural",
    "loneliness": "zh-CN-XiaoxiaoNeural",
    "hope": "zh-CN-YunxiNeural",
    "regret": "zh-CN-XiaoyiNeural",
    "default": "zh-CN-XiaoyiNeural",
}

# 风格→TTS参数
STYLE_TTS_PARAMS = {
    "douyin_sad": {"rate": "-15%", "pitch": "+5Hz"},
    "rap": {"rate": "+10%", "pitch": "+0Hz"},
    "emo_pop": {"rate": "-10%", "pitch": "+8Hz"},
    "heartbreak": {"rate": "-20%", "pitch": "+3Hz"},
    "folk": {"rate": "-15%", "pitch": "+0Hz"},
    "jay_chou": {"rate": "-10%", "pitch": "+5Hz"},
    "pop": {"rate": "-10%", "pitch": "+3Hz"},
    "default": {"rate": "-10%", "pitch": "+3Hz"},
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


# ==================== TTS人声生成器 ====================

class VocalGenerator:
    """歌词→edge-tts人声"""

    @staticmethod
    def _get_voice(emotion: str, voice_override: str = "") -> str:
        """选择TTS声音"""
        if voice_override:
            return voice_override
        for key, voice in TTS_VOICE_MAP.items():
            if key in emotion.lower():
                return voice
        return TTS_VOICE_MAP["default"]

    @staticmethod
    def _get_tts_params(style: str) -> dict:
        """获取风格对应的TTS参数"""
        for key, params in STYLE_TTS_PARAMS.items():
            if key in style.lower():
                return params
        return STYLE_TTS_PARAMS["default"]

    @staticmethod
    async def generate_vocal_line(text: str, voice: str, rate: str, pitch: str, output_path: str) -> str:
        """为一行歌词生成TTS音频"""
        import edge_tts

        if not text.strip():
            return ""

        # edge-tts 使用原生 rate/pitch 参数（非SSML）
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(output_path)
        return output_path

    @staticmethod
    async def generate_vocals(lyrics: str, emotion: str, style: str,
                               voice_override: str = "", output_dir: str = "") -> List[str]:
        """
        为整首歌词生成人声音频片段。

        Returns:
            List[str]: 每行歌词对应的音频文件路径
        """
        if not output_dir:
            output_dir = tempfile.mkdtemp(prefix="sing_vocal_")

        voice = VocalGenerator._get_voice(emotion, voice_override)
        params = VocalGenerator._get_tts_params(style)
        rate = params["rate"]
        pitch = params["pitch"]

        lines = [line.strip() for line in lyrics.split("\n") if line.strip()]
        paths = []

        for i, line in enumerate(lines):
            # 去掉结构标记如【主歌】【Hook】等
            clean_line = re.sub(r"[【\[][^】\]]*[】\]]", "", line).strip()
            if not clean_line:
                continue

            out_path = os.path.join(output_dir, f"vocal_{i:03d}.mp3")
            try:
                result = await VocalGenerator.generate_vocal_line(
                    clean_line, voice, rate, pitch, out_path
                )
                if result and os.path.exists(result):
                    paths.append(result)
            except Exception as e:
                logger.warning(f"TTS生成失败 (line {i}): {e}")
                continue

        return paths


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
        return sf_path

    os.makedirs(os.path.dirname(sf_path), exist_ok=True)
    logger.info(f"下载Soundfont: {SOUNDFONT_URL}")
    try:
        urllib.request.urlretrieve(SOUNDFONT_URL, sf_path)
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
