"""
Singer Service - 歌曲生成服务

SSE异步生成器模式，复用 generator.py 的 _emit / request_id 模式。
流程：parse → melody → midi → synth → tts → mix → final
"""
import os
import sys
import json
import time
import uuid
import asyncio
import logging
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent_os.melody_generator import generate_melody, MelodySpec
from agent_os.audio_engine import (
    MidiSynthesizer, VocalGenerator, AudioMixer,
    ensure_soundfont, cleanup_temp_files, SING_OUTPUT_DIR,
)
from agent_os.art_layer import (
    StyleTemplate, STYLE_TEMPLATES, StylePreset, EmotionVector,
    get_style_template,
)

logger = logging.getLogger(__name__)

SING_TIMEOUT_SECONDS = float(os.getenv("SING_TIMEOUT_SECONDS", "180"))


def _emit(step: str, msg: str, data, elapsed: float) -> dict:
    """创建SSE事件"""
    payload = {"step": step, "msg": msg, "elapsed": round(elapsed, 2)}
    if data is not None:
        payload["data"] = data
    return payload


def _resolve_style(style_name: str) -> StyleTemplate:
    """解析风格名称为StyleTemplate"""
    style_map = {
        "jay_chou": StylePreset.JAY_CHOU,
        "folk": StylePreset.FOLK,
        "heartbreak": StylePreset.HEARTBREAK,
        "nostalgic": StylePreset.NOSTALGIC,
        "darkness": StylePreset.DARKNESS,
        "douyin_sad": StylePreset.DOUYIN_SAD,
        "rap": StylePreset.RAP,
        "emo_pop": StylePreset.EMO_POP,
    }
    preset = style_map.get(style_name, StylePreset.HEARTBREAK)
    return get_style_template(preset)


def _detect_emotion(lyrics: str) -> str:
    """简单情绪检测"""
    sad_words = ["伤", "痛", "哭", "泪", "忘", "离", "散", "碎", "冷", "寒"]
    joy_words = ["笑", "乐", "甜", "美", "爱", "暖", "光", "晴", "星"]
    anger_words = ["恨", "怒", "烦", "燥", "骂", "打", "撕", "裂"]

    text = lyrics.lower()
    scores = {
        "sad": sum(1 for w in sad_words if w in text),
        "joy": sum(1 for w in joy_words if w in text),
        "anger": sum(1 for w in anger_words if w in text),
    }
    if max(scores.values()) == 0:
        return "nostalgic"
    return max(scores, key=scores.get)


async def stream_sing_async(req):
    """
    唱歌SSE异步生成器。

    Yields:
        dict: SSE事件 {"step", "msg", "elapsed", "data"}
    """
    request_id = uuid.uuid4().hex[:12]
    t0 = time.time()
    temp_files = []

    def emit(step, msg, data=None):
        if isinstance(data, dict):
            data["request_id"] = request_id
        return _emit(step, msg, data, time.time() - t0)

    try:
        # ===== Step 1: 解析 =====
        yield emit("parse", "解析歌词和风格...")
        await asyncio.sleep(0)

        template = _resolve_style(req.style)
        if req.tempo > 0:
            template.bpm = req.tempo
        emotion = _detect_emotion(req.lyrics)

        yield emit("parse", f"风格: {template.name}, 情绪: {emotion}, BPM: {template.bpm}", {
            "style": template.name,
            "emotion": emotion,
            "bpm": template.bpm,
            "melody_pattern": template.melody_pattern,
        })
        await asyncio.sleep(0)

        # ===== Step 2: LLM生成旋律 =====
        yield emit("melody", "LLM正在创作旋律...")

        melody = await asyncio.to_thread(
            generate_melody, req.lyrics, template, emotion
        )

        yield emit("melody", f"旋律生成完成: {len(melody.notes)}个音符, 调性{melody.key}", {
            "key": melody.key,
            "bpm": melody.bpm,
            "note_count": len(melody.notes),
        })
        await asyncio.sleep(0)

        # ===== Step 3: 生成MIDI =====
        yield emit("midi", "生成MIDI文件...")
        os.makedirs(SING_OUTPUT_DIR, exist_ok=True)
        midi_path = os.path.join(SING_OUTPUT_DIR, f"{request_id}.mid")
        temp_files.append(midi_path)

        await asyncio.to_thread(
            MidiSynthesizer.melody_to_midi, melody, midi_path
        )

        yield emit("midi", "MIDI文件生成完成", {"path": midi_path})
        await asyncio.sleep(0)

        # ===== Step 4: 合成伴奏音频 =====
        instrumental_path = None
        if req.mode != "vocal_only":
            yield emit("synth", "合成伴奏音频...")

            # 确保soundfont可用
            sf = await asyncio.to_thread(ensure_soundfont)
            if sf:
                yield emit("synth", f"Soundfont: {os.path.basename(sf)}")

            audio_path = os.path.join(SING_OUTPUT_DIR, f"{request_id}_inst.wav")
            temp_files.append(audio_path)

            instrumental_path = await asyncio.to_thread(
                MidiSynthesizer.midi_to_audio, midi_path, audio_path, sf
            )

            yield emit("synth", "伴奏合成完成", {"path": instrumental_path})
            await asyncio.sleep(0)

        # ===== Step 5: 人声生成（TTS或合成歌声） =====
        vocal_paths = []
        vocal_combined_path = None
        if req.mode != "instrumental":
            vocal_dir = tempfile.mkdtemp(prefix=f"sing_{request_id}_")
            temp_files.append(vocal_dir)

            if req.mode == "synth":
                # 合成歌声模式（波表+共振峰+颤音）
                yield emit("tts", "合成歌声生成中（波表合成+共振峰滤波）...")

                vocal_combined_path = await VocalGenerator.generate_synth_singing(
                    melody, req.lyrics, emotion, req.style,
                    output_dir=vocal_dir,
                )

                if vocal_combined_path and os.path.exists(vocal_combined_path):
                    vocal_paths = [vocal_combined_path]
                    yield emit("tts", "合成歌声生成完成", {
                        "vocal_path": vocal_combined_path,
                        "mode": "synth",
                    })
                else:
                    yield emit("tts", "合成歌声生成失败")
            else:
                # TTS人声模式（edge-tts）
                yield emit("tts", "逐行TTS合成中（native pitch + 逐音符切片）...")

                vocal_combined_path = await VocalGenerator.generate_singing_vocals(
                    melody, req.lyrics, emotion, req.style,
                    voice_override=req.voice,
                    output_dir=vocal_dir,
                )

                if vocal_combined_path and os.path.exists(vocal_combined_path):
                    vocal_paths = [vocal_combined_path]
                    logger.info(f"Vocal generated: {vocal_combined_path}")
                    yield emit("tts", f"人声生成完成（native pitch + 微调）", {
                        "vocal_path": vocal_combined_path,
                    })
                else:
                    logger.warning(f"Vocal generation failed: path={vocal_combined_path}")
                    yield emit("tts", "人声生成失败")
            await asyncio.sleep(0)

        # ===== Step 6: 混音 =====
        yield emit("mix", "混音中...")

        output_ext = ".wav"  # WAV总是可用
        output_filename = f"{request_id}{output_ext}"
        output_path = os.path.join(SING_OUTPUT_DIR, output_filename)

        logger.info(f"Mix: mode={req.mode}, instrumental_path={instrumental_path}, vocal_paths={vocal_paths}")
        logger.info(f"Mix: instrumental_path exists={os.path.exists(instrumental_path) if instrumental_path else False}")
        logger.info(f"Mix: vocal_paths count={len(vocal_paths)}")

        if req.mode == "vocal_only" and vocal_paths:
            result_path = await asyncio.to_thread(
                AudioMixer.vocal_only, vocal_paths, output_path, req.vocal_volume
            )
        elif req.mode == "instrumental" and instrumental_path:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(instrumental_path)
            audio.export(output_path, format="wav")
            result_path = output_path
        elif instrumental_path and vocal_paths:
            result_path = await asyncio.to_thread(
                AudioMixer.mix, instrumental_path, vocal_paths, output_path,
                req.instrumental_volume, req.vocal_volume,
            )
        elif instrumental_path:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(instrumental_path)
            audio.export(output_path, format="wav")
            result_path = output_path
        else:
            raise ValueError("无法生成音频：无伴奏且无人声")

        yield emit("mix", "混音完成", {"path": result_path})
        await asyncio.sleep(0)

        # ===== Step 7: 清理临时文件 =====
        # 保留最终输出，清理中间文件
        for p in temp_files:
            if p != result_path and p != SING_OUTPUT_DIR:
                cleanup_temp_files([p])

        # ===== Final =====
        yield emit("final", "歌曲生成完成", {
            "audio_url": f"/api/sing/audio/{os.path.basename(result_path)}",
            "audio_path": result_path,
            "filename": os.path.basename(result_path),
            "melody_key": melody.key,
            "bpm": melody.bpm,
            "note_count": len(melody.notes),
            "vocal_segments": len(vocal_paths),
            "mode": req.mode,
            "style": template.name,
            "emotion": emotion,
            "request_id": request_id,
        })

    except asyncio.TimeoutError:
        yield emit("error", f"生成超时（{SING_TIMEOUT_SECONDS}秒）", {
            "request_id": request_id,
        })
    except Exception as e:
        logger.exception(f"Sing error: {e}")
        yield emit("error", f"生成失败: {str(e)}", {
            "request_id": request_id,
        })
