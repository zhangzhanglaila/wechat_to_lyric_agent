from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class GenerateRequest(BaseModel):
    """生成请求"""
    text: str = Field(..., description="输入文本（关键词或聊天记录）")
    mode: str = Field(default="lyrics", description="生成模式: lyrics / poem")
    style: Optional[str] = Field(default=None, description="风格")
    intensity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    expression: Optional[str] = Field(default=None, description="表达方式: direct / metaphor / self_mock")
    lyric_density: Optional[str] = Field(default=None, description="句长: short / medium / long")
    poem_form: Optional[str] = Field(default=None, description="诗歌体裁: free / classical / imagist / diary")
    beam_width: int = Field(default=2, ge=1, le=4)
    candidates: int = Field(default=1, ge=1, le=6)
    max_refine_steps: int = Field(default=0, ge=0, le=5)
    advanced_mode: bool = Field(default=False, description="是否启用高级优化链（多候选/rerank/refine）")
    explain: bool = Field(default=True)
    include_baseline: bool = Field(default=False, description="是否包含 baseline 对比（默认关闭）")
    weights: Optional[Dict[str, float]] = Field(default=None, description="自定义目标函数权重")
    structure: Optional[List[Dict]] = Field(default=None, description="用户自定义 DSL")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "分手后的聊天记录",
                "mode": "lyrics",
                "style": "douyin_sad",
                "intensity": 0.8,
                "beam_width": 2,
                "explain": True
            }
        }


class CandidateItem(BaseModel):
    """候选结果"""
    index: int
    text: str
    score: float
    score_details: Dict[str, float]


class StepRecord(BaseModel):
    """优化步骤记录"""
    step: int
    issues: List[str]
    applied_op: Optional[str]


class ExplanationResponse(BaseModel):
    """创作说明"""
    emotion_arc: str
    style_decisions: Dict[str, Any]
    structure_type: str
    hook_strategy: str
    objective_weights: Optional[Dict[str, float]]
    optimization_steps: List[StepRecord]
    final_refine_steps: int


class GenerateResponse(BaseModel):
    """生成响应"""
    mode: str
    style: str
    emotion: str
    emotion_intensity: float
    # Baseline（无优化链）
    baseline_text: str
    baseline_hook: str
    baseline_score: float
    baseline_score_details: Dict[str, float]
    # 优化后（有优化链）
    optimized_text: str
    optimized_hook: str
    optimized_score: float
    optimized_score_details: Dict[str, float]
    # 对比
    delta: float
    # 创作说明
    explanation: Optional[ExplanationResponse] = None
    # 所有候选
    candidates: List[CandidateItem]
