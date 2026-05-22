from pydantic import BaseModel, Field
from typing import Optional


class SingRequest(BaseModel):
    """唱歌请求"""
    lyrics: str = Field(..., description="歌词文本")
    style: str = Field(default="heartbreak", description="风格预设名称")
    voice: str = Field(default="", description="TTS声音（空=自动选择）")
    tempo: int = Field(default=0, ge=0, le=200, description="BPM（0=使用风格默认值）")
    mode: str = Field(default="full", description="模式: full(人声+伴奏) / instrumental(纯伴奏) / vocal_only(纯人声)")
    instrumental_volume: float = Field(default=0.8, ge=0.0, le=1.0, description="伴奏音量")
    vocal_volume: float = Field(default=0.7, ge=0.0, le=1.0, description="人声音量")

    class Config:
        json_schema_extra = {
            "example": {
                "lyrics": "窗外的麻雀 在电线杆上多嘴\n你说这一句 很有夏天的感觉",
                "style": "jay_chou",
                "mode": "full",
                "instrumental_volume": 0.3,
                "vocal_volume": 0.9,
            }
        }
