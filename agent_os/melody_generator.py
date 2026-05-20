"""
Melody Generator - LLM旋律生成模块

使用现有 LLM 接口生成旋律音符序列，支持风格约束和规则回退。
输出结构化的 MelodySpec，供 MidiSynthesizer 消费。
"""
import re
import random
from dataclasses import dataclass, field
from typing import List, Optional

from agent_os.art_layer import llm, StyleTemplate


# ==================== 数据结构 ====================

@dataclass
class NoteSpec:
    """单个音符规格"""
    pitch: str       # "C4", "D#4", "REST"
    duration: float  # 以拍为单位 (0.25, 0.5, 1.0, 2.0)
    lyric: str = ""  # 对应的歌词字/词

    @property
    def is_rest(self) -> bool:
        return self.pitch.upper() == "REST"


@dataclass
class MelodySpec:
    """完整旋律规格"""
    key: str = "C_major"
    bpm: int = 80
    time_sig: str = "4/4"
    notes: List[NoteSpec] = field(default_factory=list)


# ==================== 音阶定义 ====================

SCALES = {
    "C_major":  ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5", "D5", "E5"],
    "A_minor":  ["A3", "B3", "C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"],
    "G_major":  ["G3", "A3", "B3", "C4", "D4", "E4", "F#4", "G4", "A4", "B4"],
    "E_minor":  ["E3", "F#3", "G3", "A3", "B3", "C4", "D4", "E4", "F#4", "G4"],
    "F_major":  ["F3", "G3", "A3", "Bb3", "C4", "D4", "E4", "F4", "G4", "A4"],
    "D_minor":  ["D3", "E3", "F3", "G3", "A3", "Bb3", "C4", "D4", "E4", "F4"],
}

# 情绪→调性映射
EMOTION_KEY_MAP = {
    "sad": "A_minor",
    "nostalgic": "G_major",
    "joy": "C_major",
    "anger": "E_minor",
    "warmth": "C_major",
    "loneliness": "D_minor",
    "hope": "G_major",
    "regret": "A_minor",
}

# 和弦进行（根音 MIDI 编号）
CHORD_PROGRESSIONS = {
    "C_major":  [60, 67, 65, 62],  # C G Am F
    "A_minor":  [57, 60, 65, 62],  # Am C F G
    "G_major":  [55, 62, 60, 59],  # G D C B
    "E_minor":  [52, 55, 60, 59],  # Em G C B
    "F_major":  [53, 60, 57, 55],  # F C Am G
    "D_minor":  [50, 57, 53, 55],  # Dm Am F G
}

# MIDI音符编号映射
NOTE_TO_MIDI = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def pitch_to_midi(pitch: str) -> int:
    """音名转MIDI编号，如 C4 -> 60"""
    if pitch.upper() == "REST":
        return 0
    match = re.match(r"^([A-G][#b]?)(\d)$", pitch)
    if not match:
        return 60  # 默认C4
    note_name, octave = match.groups()
    return (int(octave) + 1) * 12 + NOTE_TO_MIDI[note_name]


def get_scale_for_emotion(emotion: str) -> str:
    """根据情绪选择调性"""
    for key, scale in EMOTION_KEY_MAP.items():
        if key in emotion.lower():
            return scale
    return "C_major"


# ==================== LLM旋律生成 ====================

def _build_melody_prompt(lyrics: str, template: StyleTemplate, key: str) -> str:
    """构建旋律生成提示词"""
    scale = SCALES.get(key, SCALES["C_major"])
    scale_str = ", ".join(scale)

    pattern_desc = {
        "jump": "音程跳跃较大，节奏切分，适合说唱和伤感风格",
        "smooth": "级进为主，连贯流畅，适合抒情和民谣风格",
        "flat": "音高变化小，节奏平稳，适合emo和低吟风格",
    }.get(template.melody_pattern, "级进为主")

    return f"""你是一位专业的华语流行歌曲旋律创作者。请为以下歌词创作一段旋律。

【歌词】
{lyrics}

【调性】{key}（可用音阶：{scale_str}）
【速度】{template.bpm} BPM
【旋律特征】{pattern_desc}
【密度】歌词密度为 {template.lyric_density}（short=每字一音，medium=部分连音，long=多字一音）

【输出格式要求】
每行一个音符，格式为：音名:时值:歌词字
- 音名：必须在上述音阶内，REST表示休止
- 时值：以拍为单位（0.25=十六分音符, 0.5=八分音符, 1.0=四分音符, 2.0=二分音符）
- 歌词字：对应的歌词字符

示例输出：
C4:0.5:你
E4:0.5:好
G4:1.0:吗
REST:0.5:
A4:0.5:世
G4:0.5:界

【要求】
1. 每个歌词字对应一个音符，标点符号用REST
2. 旋律要朗朗上口，符合{template.name}风格
3. 重复的歌词（Hook）旋律要一致
4. 音域控制在一个八度内

旋律："""


def _parse_melody_output(raw: str, scale: List[str]) -> List[NoteSpec]:
    """解析LLM输出的旋律文本"""
    notes = []
    valid_pitches = set(scale)

    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # 格式: NOTE:DURATION:LYRIC 或 NOTE:DURATION
        parts = re.split(r"[:\s]+", line)
        if len(parts) < 2:
            continue

        pitch = parts[0].strip()
        try:
            duration = float(parts[1].strip())
        except ValueError:
            continue

        lyric = parts[2].strip() if len(parts) > 2 else ""

        # 校验音高
        if pitch.upper() != "REST" and pitch not in valid_pitches:
            # 尝试最近的音
            pitch = _nearest_pitch(pitch, scale)

        # 校验时值
        duration = max(0.25, min(4.0, duration))

        notes.append(NoteSpec(pitch=pitch, duration=duration, lyric=lyric))

    return notes


def _nearest_pitch(pitch: str, scale: List[str]) -> str:
    """找到音阶中最接近的音"""
    try:
        midi = pitch_to_midi(pitch)
        best = min(scale, key=lambda s: abs(pitch_to_midi(s) - midi))
        return best
    except Exception:
        return scale[0]


# ==================== 规则回退生成 ====================

def _generate_rule_based_melody(lyrics: str, template: StyleTemplate, key: str) -> List[NoteSpec]:
    """规则回退：当LLM失败时生成简单旋律"""
    scale = SCALES.get(key, SCALES["C_major"])
    chords = CHORD_PROGRESSIONS.get(key, CHORD_PROGRESSIONS["C_major"])
    notes = []
    beat_in_bar = 0
    bar_idx = 0
    chord_idx = 0

    # 按字分割歌词
    chars = list(lyrics.replace("\n", "").replace(" ", ""))

    # 根据风格确定基本时值
    base_duration = {
        "short": 0.5,
        "medium": 0.75,
        "long": 1.0,
    }.get(template.lyric_density, 0.5)

    # 根据旋律模式确定音程范围
    max_interval = {
        "jump": 5,
        "smooth": 2,
        "flat": 1,
    }.get(template.melody_pattern, 2)

    prev_idx = len(scale) // 2  # 从中间开始

    for ch in chars:
        if ch in "，。！？、；：""''《》（）\n\r":
            notes.append(NoteSpec(pitch="REST", duration=base_duration * 0.5, lyric=ch))
            beat_in_bar += base_duration * 0.5
        else:
            # 选择音高：在前一个音附近随机游走
            delta = random.randint(-max_interval, max_interval)
            new_idx = max(0, min(len(scale) - 1, prev_idx + delta))

            # 强拍倾向于和弦音
            if beat_in_bar % 1.0 < 0.01 and random.random() < 0.6:
                chord_root = chords[chord_idx % len(chords)]
                nearest = min(range(len(scale)),
                              key=lambda i: abs(pitch_to_midi(scale[i]) - chord_root))
                new_idx = nearest

            pitch = scale[new_idx]
            prev_idx = new_idx
            notes.append(NoteSpec(pitch=pitch, duration=base_duration, lyric=ch))

        beat_in_bar += base_duration
        if beat_in_bar >= 4.0:
            beat_in_bar = 0
            bar_idx += 1
            chord_idx += 1

    return notes


# ==================== 主接口 ====================

def generate_melody(lyrics: str, template: StyleTemplate, emotion: str = "") -> MelodySpec:
    """
    生成旋律。

    Args:
        lyrics: 歌词文本
        template: 风格模板（包含bpm, melody_pattern等）
        emotion: 情绪描述（用于选择调性）

    Returns:
        MelodySpec 完整旋律规格
    """
    key = get_scale_for_emotion(emotion)
    scale = SCALES.get(key, SCALES["C_major"])

    # 尝试LLM生成
    try:
        prompt = _build_melody_prompt(lyrics, template, key)
        raw = llm(prompt, temp=0.7)
        if raw and not raw.startswith("LLM Error"):
            notes = _parse_melody_output(raw, scale)
            if len(notes) >= 4:  # 至少4个音符才算有效
                return MelodySpec(
                    key=key,
                    bpm=template.bpm,
                    time_sig="4/4",
                    notes=notes,
                )
    except Exception:
        pass

    # 回退到规则生成
    notes = _generate_rule_based_melody(lyrics, template, key)
    return MelodySpec(
        key=key,
        bpm=template.bpm,
        time_sig="4/4",
        notes=notes,
    )
