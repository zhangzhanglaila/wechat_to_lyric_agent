"""
WeChatChat2Lyric-Agent v5.0
Self-Optimizing Agent System

核心架构：
- Global Constraint Controller（冻结高分维度，避免震荡）
- Diff-based Editing（精确修改局部）
- Unified Objective Function（全局优化目标）
- Meta-Agent（学习修复历史，经验驱动优化）

解决 v4.0 的核心问题：non-converging multi-objective optimization
"""

import os
import re
import sys
import json
from typing import List, Dict, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv
from datetime import datetime
from collections import defaultdict

from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage

# ==================== 配置 ====================
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY", "sk-44b7a257f56d4d80b85ed5ac4d1d182d")
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")

GENRE_OPTIONS = ["流行", "民谣", "说唱", "抒情", "摇滚"]

llm = ChatOpenAI(
    openai_api_key=API_KEY,
    openai_api_base=API_BASE,
    model_name=MODEL_NAME,
    temperature=0.8,
    streaming=False
)


# ==================== 全局约束控制器 ====================

class ConstraintLock:
    """
    全局约束锁
    冻结高分维度，避免修复时破坏已达标的部分
    """

    def __init__(self):
        self.locked_dims: Set[str] = set()
        self.lock_threshold = 8.0  # 超过此分数锁定
        self.lock_history: List[Dict] = []

    def evaluate_and_lock(self, scores: Dict[str, float]) -> Set[str]:
        """
        评估分数，锁定高分维度
        返回当前被锁定的维度
        """
        newly_locked = set()

        for dim, score in scores.items():
            if score >= self.lock_threshold and dim not in self.locked_dims:
                self.locked_dims.add(dim)
                newly_locked.add(dim)
                self.lock_history.append({
                    "dimension": dim,
                    "score": score,
                    "action": "LOCK",
                    "timestamp": datetime.now().isoformat()
                })

        return self.locked_dims

    def is_locked(self, dimension: str) -> bool:
        return dimension in self.locked_dims

    def get_locked_dims(self) -> Set[str]:
        return self.locked_dims.copy()

    def unlock_all(self):
        """重置锁定"""
        self.locked_dims.clear()

    def get_lock_report(self) -> str:
        if not self.locked_dims:
            return "无锁定维度"
        return f"已锁定: {', '.join(self.locked_dims)}"


# ==================== 差分编辑器 ====================

@dataclass
class EditAction:
    """编辑操作"""
    line_index: int
    action_type: str  # "fix_rhyme", "boost_emotion", "modify"
    target_content: str = ""
    original_content: str = ""
    reason: str = ""


class DiffEditor:
    """
    差分编辑器
    只修改局部，不整段重写
    """

    def __init__(self):
        self.edit_history: List[EditAction] = []
        self.line_cache: List[str] = []

    def parse_lyrics_to_lines(self, lyrics: str) -> List[str]:
        """解析歌词为行列表"""
        lines = []
        sections = []

        for line in lyrics.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('[') and line.endswith(']'):
                sections.append(line)
                lines.append(line)  # 保留段落标记
            else:
                lines.append(line)

        return lines

    def apply_line_edit(self, lyrics: str, edit: EditAction) -> str:
        """应用单行编辑"""
        lines = self.parse_lyrics_to_lines(lyrics)

        if 0 <= edit.line_index < len(lines):
            # 跳过段落标记行
            target_idx = edit.line_index
            if lines[target_idx].startswith('['):
                target_idx += 1

            if target_idx < len(lines):
                original = lines[target_idx]
                lines[target_idx] = edit.target_content

                edit.original_content = original
                self.edit_history.append(edit)

        return '\n'.join(lines)

    def apply_batch_edits(self, lyrics: str, edits: List[EditAction]) -> str:
        """批量应用编辑"""
        result = lyrics

        # 按行索引排序（从低到高，避免索引偏移）
        sorted_edits = sorted(edits, key=lambda e: e.line_index)

        for edit in sorted_edits:
            result = self.apply_line_edit(result, edit)

        return result

    def generate_targeted_edit_plan(
        self,
        lyrics: str,
        issues: List[str],
        locked_dims: Set[str]
    ) -> List[EditAction]:
        """
        生成精确的编辑计划
        基于问题定位，生成最小编辑集
        """
        lines = self.parse_lyrics_to_lines(lyrics)
        edit_plan = []

        # 分析问题类型
        rhyme_issues = [i for i in issues if '押韵' in i or 'rhyme' in i.lower()]
        emotion_issues = [i for i in issues if '情感' in i or 'emotion' in i.lower()]
        structure_issues = [i for i in issues if '结构' in i or '句数' in i]

        # 为押韵问题定位目标行
        if rhyme_issues and 'rhyme' not in locked_dims:
            # 找最后一行（最可能是问题行）
            last_meaningful_idx = len(lines) - 1
            while last_meaningful_idx >= 0 and lines[last_meaningful_idx].startswith('['):
                last_meaningful_idx -= 1

            if last_meaningful_idx >= 0:
                edit_plan.append(EditAction(
                    line_index=last_meaningful_idx,
                    action_type="fix_rhyme",
                    reason=f"修复押韵: {rhyme_issues[0]}"
                ))

        # 为情感问题定位
        if emotion_issues and 'emotion' not in locked_dims:
            # 副歌部分通常是情感核心
            for i, line in enumerate(lines):
                if line.startswith('[副歌]') or (i > 0 and 'chorus' in line.lower()):
                    edit_plan.append(EditAction(
                        line_index=i + 1,
                        action_type="boost_emotion",
                        reason=f"增强情感: {emotion_issues[0]}"
                    ))
                    break

        return edit_plan


# ==================== 统一目标优化器 ====================

@dataclass
class OptimizationWeights:
    """优化权重配置"""
    rhythm: float = 0.25
    emotion: float = 0.30
    structure: float = 0.20
    rhyme: float = 0.15
    keyword: float = 0.10


class GlobalOptimizer:
    """
    全局目标优化器
    将多维分数统一为单一目标
    """

    def __init__(self, weights: OptimizationWeights = None):
        self.weights = weights or OptimizationWeights()
        self.history: List[Dict] = []

    def compute_global_score(self, scores: Dict[str, float]) -> float:
        """
        计算全局分数
        weighted sum = w1*s1 + w2*s2 + ...
        """
        w = self.weights

        total = (
            w.rhythm * scores.get("rhythm_quality", 0) +
            w.emotion * scores.get("emotion_match", 0) +
            w.structure * scores.get("structure_compliance", 0) +
            w.rhyme * scores.get("rhyme_quality", 0) +
            w.keyword * scores.get("keyword_coverage", 0)
        )

        return round(total, 2)

    def get_improvement_direction(
        self,
        current_scores: Dict[str, float],
        target_scores: Dict[str, float]
    ) -> List[Tuple[str, float]]:
        """
        获取改进方向
        返回：(维度, 改进优先级) 按优先级排序
        """
        improvements = []

        for dim in ["rhythm", "emotion", "structure", "rhyme", "keyword"]:
            score_key = f"{dim}_quality" if dim != "emotion" else "emotion_match"
            current = current_scores.get(score_key, 0)
            target = target_scores.get(score_key, 8.0)
            gap = target - current

            if gap > 0.5:  # 只考虑显著差距
                # 考虑权重加权
                weight = getattr(self.weights, dim, 0.2)
                priority = gap * weight
                improvements.append((dim, priority))

        # 按优先级排序
        improvements.sort(key=lambda x: x[1], reverse=True)
        return improvements

    def should_continue_optimizing(
        self,
        current_scores: Dict[str, float],
        iteration: int,
        max_iterations: int = 5
    ) -> Tuple[bool, str]:
        """
        判断是否继续优化
        返回：(是否继续, 原因)
        """
        global_score = self.compute_global_score(current_scores)

        # 检查是否达标
        if global_score >= 8.0:
            return False, f"全局分数达标 ({global_score})"

        # 检查迭代次数
        if iteration >= max_iterations:
            return False, f"达到最大迭代次数 ({max_iterations})"

        # 检查是否收敛（分数变化小于阈值）
        if len(self.history) >= 2:
            prev_score = self.compute_global_score(self.history[-1])
            delta = global_score - prev_score
            if abs(delta) < 0.1:
                return False, f"收敛 (delta={delta})"

        return True, f"继续优化 (global={global_score})"

    def record_iteration(self, scores: Dict, action: str):
        """记录迭代历史"""
        self.history.append({
            "iteration": len(self.history),
            "scores": scores.copy(),
            "global_score": self.compute_global_score(scores),
            "action": action,
            "timestamp": datetime.now().isoformat()
        })


# ==================== Meta-Agent（核心创新）====================

class MetaAgent:
    """
    元优化 Agent
    学习修复历史，决定最优修复策略
    从"规则驱动" → "经验驱动"
    """

    def __init__(self):
        self.repair_success_log: List[Dict] = []
        self.repair_failure_log: List[Dict] = []
        self.strategy_preference: Dict[str, float] = defaultdict(float)

    def analyze_repair_outcome(
        self,
        repair_action: str,
        scores_before: Dict,
        scores_after: Dict,
        issue_dim: str
    ):
        """
        分析修复结果
        记录成功/失败经验
        """
        before_global = sum(scores_before.values()) / len(scores_before)
        after_global = sum(scores_after.values()) / len(scores_after)
        delta = after_global - before_global

        record = {
            "action": repair_action,
            "issue_dim": issue_dim,
            "delta": delta,
            "scores_before": scores_before,
            "scores_after": scores_after,
            "timestamp": datetime.now().isoformat()
        }

        if delta > 0.3:
            self.repair_success_log.append(record)
            self.strategy_preference[repair_action] += delta
        elif delta < -0.2:
            self.repair_failure_log.append(record)
            self.strategy_preference[repair_action] += delta

    def get_optimal_action_sequence(self, issue_dim: str) -> List[str]:
        """
        获取最优操作序列
        基于历史学习
        """
        # 分析相关维度的成功操作
        relevant_successes = [
            r for r in self.repair_success_log
            if r["issue_dim"] == issue_dim
        ]

        if not relevant_successes:
            # 默认顺序
            return ["fix_structure", "fix_rhyme", "boost_emotion"]

        # 按 delta 排序
        relevant_successes.sort(key=lambda x: x["delta"], reverse=True)

        return [r["action"] for r in relevant_successes[:3]]

    def get_avoid_actions(self, issue_dim: str) -> List[str]:
        """获取应避免的操作"""
        relevant_failures = [
            r for r in self.repair_failure_log
            if r["issue_dim"] == issue_dim
        ]
        return [r["action"] for r in relevant_failures]

    def should_skip_repair(
        self,
        repair_action: str,
        current_scores: Dict,
        locked_dims: Set[str]
    ) -> Tuple[bool, str]:
        """
        判断是否跳过某修复
        基于历史经验
        """
        # 检查是否锁定
        for dim in ["rhyme", "emotion", "structure"]:
            if dim in repair_action and dim in locked_dims:
                return True, f"{dim} 已锁定，跳过 {repair_action}"

        # 检查历史失败率
        action_failures = [
            r for r in self.repair_failure_log
            if r["action"] == repair_action
        ]
        action_successes = [
            r for r in self.repair_success_log
            if r["action"] == repair_action
        ]

        total = len(action_failures) + len(action_successes)
        if total >= 3:
            failure_rate = len(action_failures) / total
            if failure_rate > 0.6:
                return True, f"{repair_action} 失败率 {failure_rate:.0%}，跳过"

        return False, "继续执行"


# ==================== 核心数据结构 ====================

@dataclass
class SectionPlan:
    """段落计划"""
    section_type: str
    lines: int
    emotion: str
    theme: str
    keywords: List[str]
    rhyme_end: str = ""
    hook_line: str = ""
    tone: str = ""
    melody_hint: str = ""


@dataclass
class BeatStructuredSkeleton:
    """骨架"""
    sections: List[SectionPlan] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "sections": [
                {
                    "section_type": s.section_type,
                    "lines": s.lines,
                    "emotion": s.emotion,
                    "theme": s.theme,
                    "keywords": s.keywords,
                    "rhyme_end": s.rhyme_end,
                    "hook_line": s.hook_line,
                    "tone": s.tone,
                    "melody_hint": s.melody_hint,
                }
                for s in self.sections
            ]
        }

    @staticmethod
    def from_dict(data: Dict) -> "BeatStructuredSkeleton":
        sections = []
        for s in data.get("sections", []):
            sections.append(SectionPlan(
                section_type=s.get("section_type", "verse"),
                lines=s.get("lines", 4),
                emotion=s.get("emotion", "low"),
                theme=s.get("theme", ""),
                keywords=s.get("keywords", []),
                rhyme_end=s.get("rhyme_end", ""),
                hook_line=s.get("hook_line", ""),
                tone=s.get("tone", ""),
                melody_hint=s.get("melody_hint", ""),
            ))
        return BeatStructuredSkeleton(sections=sections)


# ==================== Agent 实现 ====================

class BaseAgent:
    name = "base"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> Any:
        raise NotImplementedError


class CleanerAgent(BaseAgent):
    name = "clean"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> str:
        raw_text = context.get("raw_text", "")
        lines = raw_text.split('\n')
        cleaned_lines = []

        timestamp_pattern = r'\d{4}[/\-]\d{1,2}[/\-]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?'
        system_patterns = [
            r'^以上是打招呼内容', r'^以上是正文内容', r'^点击添加备注',
            r'^---\s*$', r'^\s*$', r'^【.*】$'
        ]

        for line in lines:
            line = line.strip()
            if not line or re.match(timestamp_pattern, line):
                continue
            if any(re.match(p, line) for p in system_patterns):
                continue
            line = re.sub(r'^["\"]?[\u4e00-\u9fa5a-zA-Z0-9_]+["\"]?\s*[:：]\s*', '', line)
            if line and len(line) > 1:
                cleaned_lines.append(line)

        cleaned = '\n'.join(cleaned_lines)

        prompt = f"""清洗微信聊天记录，每行一条消息：

{cleaned}

直接输出："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return cleaned


class EmotionAnalystAgent(BaseAgent):
    name = "analyze"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> Dict:
        cleaned_text = context.get("cleaned_text", "")

        prompt = f"""分析聊天记录，输出JSON：

{{
    "emotion": "情感",
    "emotion_detail": "情感细化",
    "keywords": ["词1", "词2", "词3", "词4", "词5"],
    "story": "故事线",
    "relationship": "人物关系",
    "emotion_curve": ["low", "rising", "peak", "fall", "peak"]
}}

聊天记录：
{cleaned_text}

直接输出JSON："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            return json.loads(result)
        except:
            return {
                "emotion": "未知", "emotion_detail": "", "keywords": [],
                "story": "", "relationship": "", "emotion_curve": []
            }


class SkeletonPlannerAgent(BaseAgent):
    name = "plan"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> Dict:
        emotion = context.get("emotion", "")
        emotion_detail = context.get("emotion_detail", "")
        keywords = context.get("keywords", [])
        story = context.get("story", "")
        genre = context.get("genre", "流行")

        genre_rhyme = {
            "流行": ["ang", "ian", "ou"],
            "民谣": ["an", "en", "ing"],
            "说唱": ["a", "e", "i", "ou"],
            "抒情": ["ang", "ian", "ao"],
            "摇滚": ["ang", "ong", "ai"]
        }
        rhyme_options = genre_rhyme.get(genre, ["ang", "ian"])

        prompt = f"""生成 Beat-Structured Skeleton（严格JSON）：

{{
    "sections": [
        {{
            "section_type": "verse1",
            "lines": 4,
            "emotion": "low",
            "theme": "引入故事",
            "keywords": ["{keywords[0] if keywords else '情感'}"],
            "rhyme_end": "{rhyme_options[0]}",
            "hook_line": "",
            "tone": "叙事",
            "melody_hint": "下行"
        }},
        {{
            "section_type": "chorus",
            "lines": 4,
            "emotion": "peak",
            "theme": "情感高潮",
            "keywords": ["{keywords[1] if len(keywords) > 1 else keywords[0]}"],
            "rhyme_end": "{rhyme_options[1] if len(rhyme_options) > 1 else rhyme_options[0]}",
            "hook_line": "核心金句（10字内押韵）",
            "tone": "强烈",
            "melody_hint": "上行"
        }},
        {{
            "section_type": "verse2",
            "lines": 4,
            "emotion": "rising",
            "theme": "延续递进",
            "keywords": ["{keywords[2] if len(keywords) > 2 else keywords[0]}"],
            "rhyme_end": "{rhyme_options[0]}",
            "hook_line": "",
            "tone": "叙事",
            "melody_hint": "平稳"
        }},
        {{
            "section_type": "bridge",
            "lines": 4,
            "emotion": "fall",
            "theme": "情感转折",
            "keywords": ["{keywords[3] if len(keywords) > 3 else keywords[0]}"],
            "rhyme_end": "{rhyme_options[1] if len(rhyme_options) > 1 else rhyme_options[0]}",
            "hook_line": "",
            "tone": "低沉",
            "melody_hint": "下行"
        }}
    ]
}}

情感：{emotion} - {emotion_detail}
曲风：{genre}

直接输出JSON："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            return json.loads(result)
        except:
            return {
                "sections": [
                    {"section_type": "verse1", "lines": 4, "emotion": "low",
                     "theme": "引入", "keywords": keywords[:2], "rhyme_end": "ang",
                     "hook_line": "", "tone": "叙事", "melody_hint": "下行"},
                    {"section_type": "chorus", "lines": 4, "emotion": "peak",
                     "theme": "高潮", "keywords": keywords[:2], "rhyme_end": "ian",
                     "hook_line": "我们的故事", "tone": "强烈", "melody_hint": "上行"},
                    {"section_type": "verse2", "lines": 4, "emotion": "rising",
                     "theme": "延续", "keywords": keywords[:2], "rhyme_end": "ou",
                     "hook_line": "", "tone": "叙事", "melody_hint": "平稳"},
                    {"section_type": "bridge", "lines": 4, "emotion": "fall",
                     "theme": "转折", "keywords": keywords[:1], "rhyme_end": "en",
                     "hook_line": "", "tone": "低沉", "melody_hint": "下行"},
                ]
            }


class GeneratorAgent(BaseAgent):
    name = "generate"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> str:
        emotion = context.get("emotion", "")
        emotion_detail = context.get("emotion_detail", "")
        keywords = context.get("keywords", [])
        story = context.get("story", "")
        genre = context.get("genre", "流行")
        skeleton_data = context.get("skeleton_plan", {})

        skeleton = BeatStructuredSkeleton.from_dict(skeleton_data)

        genre_notes = {
            "流行": "旋律优美，情感细腻",
            "民谣": "叙事性强，画面感足",
            "说唱": "节奏强劲，押韵密集",
            "抒情": "情感浓烈，旋律优美",
            "摇滚": "力量感足，节奏强劲"
        }

        # 构建约束
        constraints = []
        for s in skeleton.sections:
            constraints.append(f"[{s.section_type.upper()}] {s.lines}句 情感:{s.emotion} 韵脚:{s.rhyme_end} 主题:{s.theme}")

        prompt = f"""基于结构创作歌词：

曲风：{genre} - {genre_notes.get(genre, '')}
情感：{emotion} - {emotion_detail}
关键词：{', '.join(keywords)}
故事：{story}

结构：
{chr(10).join(constraints)}

要求：
1. 严格按句数创作
2. 按韵脚押韵
3. 禁止真实人名地名

直接输出歌词："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return "生成失败"


class DiffEditAgent(BaseAgent):
    """
    差分编辑 Agent
    v5.0 核心：精确修改局部，不整段重写
    """
    name = "diff_edit"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> str:
        lyrics = context.get("lyrics", "")
        edit_plan = context.get("edit_plan", [])

        if not edit_plan:
            return lyrics

        # 应用编辑
        diff_editor = DiffEditor()
        result = diff_editor.apply_batch_edits(lyrics, edit_plan)

        return result


class VerifierAgent(BaseAgent):
    """验证 Agent"""

    name = "verify"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> Dict:
        lyrics = context.get("lyrics", "")
        emotion = context.get("emotion", "")
        emotion_detail = context.get("emotion_detail", "")
        keywords = context.get("keywords", [])
        skeleton_data = context.get("skeleton_plan", {})

        skeleton = BeatStructuredSkeleton.from_dict(skeleton_data)

        prompt = f"""审查歌词（严格JSON）：

{{
    "overall": 8.5,
    "rhythm_quality": 8.0,
    "emotion_match": 9.0,
    "structure_compliance": 8.5,
    "rhyme_quality": 8.0,
    "keyword_coverage": 7.5,
    "issues": ["问题1", "问题2"],
    "targeted_repairs": {{
        "fix_rhyme": true,
        "boost_emotion": false,
        "fix_structure": true
    }}
}}

歌词：
{lyrics}

情感：{emotion}
关键词：{', '.join(keywords)}
句数要求：主歌{skeleton.sections[0].lines if skeleton.sections else 4}句 副歌{skeleton.sections[1].lines if len(skeleton.sections) > 1 else 4}句

直接输出JSON："""

        try:
            response = llm([HumanMessage(content=prompt)])
            result = response.content.strip()
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]

            data = json.loads(result)

            # 存储分数
            context["score"] = data.get("overall", 0)
            context["rhythm_score"] = data.get("rhythm_quality", 0)
            context["emotion_match"] = data.get("emotion_match", 0)
            context["structure_score"] = data.get("structure_compliance", 0)
            context["rhyme_score"] = data.get("rhyme_quality", 0)
            context["keyword_score"] = data.get("keyword_coverage", 0)

            return data

        except:
            return {
                "overall": 5.0, "issues": ["审查失败"],
                "targeted_repairs": {"fix_rhyme": True, "boost_emotion": True, "fix_structure": True}
            }


class TitleAgent(BaseAgent):
    """标题生成"""

    name = "title"

    @classmethod
    def execute(cls, context: Dict, **kwargs) -> str:
        lyrics = context.get("lyrics", "")
        emotion = context.get("emotion", "")

        prompt = f"""生成歌词标题（2-6字）：

歌词片段：{lyrics[:300]}
情感：{emotion}

直接输出标题："""

        try:
            response = llm([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return "无题"


# ==================== Self-Optimizing Pipeline ====================

class SelfOptimizingPipeline:
    """
    v5.0 核心：自优化 Pipeline
    解决收敛性问题
    """

    def __init__(self, api_key: str, api_base: str, model_name: str):
        self.llm = ChatOpenAI(
            openai_api_key=api_key,
            openai_api_base=api_base,
            model_name=model_name,
            temperature=0.8
        )

        # 核心组件
        self.constraint_lock = ConstraintLock()
        self.global_optimizer = GlobalOptimizer()
        self.meta_agent = MetaAgent()
        self.diff_editor = DiffEditor()

        self.genre = "流行"
        self.max_iterations = 5

    def run(self, chat_text: str, genre: str = "流行") -> Dict:
        """执行自优化流程"""
        self.genre = genre

        context = {
            "raw_text": chat_text,
            "genre": genre,
            "iteration": 0,
            "scores_history": []
        }

        print("\n" + "="*60)
        print("🎵 WeChatChat2Lyric-Agent v5.0 (Self-Optimizing)")
        print("="*60)
        print(f"📂 聊天记录: {len(chat_text)} 字符")
        print(f"🎸 曲风: {genre}")
        print("\n🔄 开始自优化流程...\n")

        # Phase 1: 生成
        print("[Phase 1] 生成初始歌词...")
        context = self._generation_phase(context)

        # Phase 2: 自优化
        print("\n[Phase 2] 自优化循环...")
        context = self._optimization_phase(context)

        # Phase 3: 输出
        print("\n[Phase 3] 生成标题...")
        context["title"] = TitleAgent.execute(context)

        return self._build_result(context)

    def _generation_phase(self, context: Dict) -> Dict:
        """生成阶段"""
        print("  [1.1] 清洗...")
        context["cleaned_text"] = CleanerAgent.execute(context)

        print("  [1.2] 分析情感...")
        analysis = EmotionAnalystAgent.execute(context)
        context.update(analysis)
        print(f"       情感: {context.get('emotion', '未知')}")

        print("  [1.3] 规划骨架...")
        context["skeleton_plan"] = SkeletonPlannerAgent.execute(context)

        print("  [1.4] 生成歌词...")
        context["lyrics"] = GeneratorAgent.execute(context)
        print(f"       生成: {len(context['lyrics'])} 字符")

        return context

    def _optimization_phase(self, context: Dict) -> Dict:
        """优化阶段 - 核心创新"""
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            context["iteration"] = iteration

            print(f"\n  --- 优化循环 {iteration}/{self.max_iterations} ---")

            # 验证
            print("  [验证] 质量审查...")
            verification = VerifierAgent.execute(context)
            scores = {
                "rhythm_quality": verification.get("rhythm_quality", 0),
                "emotion_match": verification.get("emotion_match", 0),
                "structure_compliance": verification.get("structure_compliance", 0),
                "rhyme_quality": verification.get("rhyme_quality", 0),
                "keyword_coverage": verification.get("keyword_coverage", 0)
            }
            context["verification"] = verification

            global_score = self.global_optimizer.compute_global_score(scores)
            print(f"       全局分数: {global_score:.2f}/10")

            # 约束锁定
            locked = self.constraint_lock.evaluate_and_lock(scores)
            print(f"       {self.constraint_lock.get_lock_report()}")

            # 记录历史
            self.global_optimizer.record_iteration(scores, "verify")

            # 检查收敛
            should_continue, reason = self.global_optimizer.should_continue_optimizing(
                scores, iteration, self.max_iterations
            )

            if not should_continue:
                print(f"       ✅ {reason}")
                break

            # Targeted Repair
            targeted = verification.get("targeted_repairs", {})
            issues = verification.get("issues", [])

            if not any(targeted.values()):
                print("       ✅ 无需修复")
                break

            print(f"       🔧 执行精准修复...")
            print(f"       📋 问题: {', '.join(issues[:2])}")

            # Meta-Agent 决策
            for dim, needs_fix in targeted.items():
                if not needs_fix:
                    continue

                # 检查是否跳过
                skip, skip_reason = self.meta_agent.should_skip_repair(
                    f"fix_{dim}" if dim != "emotion" else "boost_emotion",
                    scores,
                    locked
                )

                if skip:
                    print(f"       ⏭️  跳过 {dim}: {skip_reason}")
                    continue

                # 执行修复
                print(f"       → 修复 {dim}...")
                scores_before = scores.copy()

                # 差分编辑
                edit_plan = self.diff_editor.generate_targeted_edit_plan(
                    context["lyrics"], issues, locked
                )

                if edit_plan:
                    context["edit_plan"] = edit_plan
                    context["lyrics"] = DiffEditAgent.execute(context)
                else:
                    # 回退到整段重生成（不得已）
                    context["lyrics"] = GeneratorAgent.execute(context)

                # 重新验证
                verification_new = VerifierAgent.execute(context)
                scores_new = {
                    "rhythm_quality": verification_new.get("rhythm_quality", 0),
                    "emotion_match": verification_new.get("emotion_match", 0),
                    "structure_compliance": verification_new.get("structure_compliance", 0),
                    "rhyme_quality": verification_new.get("rhyme_quality", 0),
                    "keyword_coverage": verification_new.get("keyword_coverage", 0)
                }

                # Meta-Agent 学习
                self.meta_agent.analyze_repair_outcome(
                    f"fix_{dim}",
                    scores_before,
                    scores_new,
                    dim
                )

                self.global_optimizer.record_iteration(scores_new, f"fix_{dim}")

                # 更新分数
                context["verification"] = verification_new
                scores = scores_new

            # 约束重评估
            locked = self.constraint_lock.evaluate_and_lock(scores)

        return context

    def _build_result(self, context: Dict) -> Dict:
        """构建结果"""
        return {
            "title": context.get("title", "无题"),
            "genre": self.genre,
            "emotion": context.get("emotion", ""),
            "emotion_detail": context.get("emotion_detail", ""),
            "keywords": context.get("keywords", []),
            "story": context.get("story", ""),
            "lyric_plan": context.get("skeleton_plan", {}),
            "lyrics": context.get("lyrics", ""),
            "quality_score": context.get("verification", {}),
        }

    def print_result(self, result: Dict):
        """打印结果"""
        print("\n" + "="*60)
        print("🎵 歌曲标题:", result["title"])
        print("🎸 曲风:", result["genre"])
        print("🎧 情感:", result["emotion"])
        print("🔑 关键词:", ", ".join(result["keywords"][:6]))

        qs = result.get("quality_score", {})
        if qs:
            print(f"⭐ 质量评分: {qs.get('overall', 0):.1f}/10")

        print("="*60)
        print("\n📝 歌词:")
        print("-"*40)
        print(result["lyrics"])
        print("-"*40)


# ==================== 演示 ====================

def run_demo():
    """演示"""
    print("\n" + "="*60)
    print("🎵 WeChatChat2Lyric-Agent v5.0 演示")
    print("="*60)

    demo_chat = """2024/1/1 12:00:00
小明：亲爱的，新年快乐！
小红：新年快乐呀～今年是我们在一起的第三年了
小明：是啊，时间过得好快
小红：记得我们第一次见面是在咖啡店
小明：你当时穿了一条白裙子
小红：你还记得呀，你当时紧张得话都说不清楚
小明：那是太喜欢你了嘛
小红：哼，就会说好听的
小明：我说的是真的，每次看到你都很开心
小红：我也是呀，和你在一起的时候
小明：今年有什么想做的事吗？
小红：想和你一起去旅行，看更多的风景
小明：好，我带你去你看日出
小红：说定了哦，不许反悔
小明：绝不反悔，我们拉钩
小红：拉钩上吊一百年不许变"""

    print("\n📝 示例聊天记录（情侣甜蜜对话）:\n")
    print(demo_chat[:200] + "...\n")

    pipeline = SelfOptimizingPipeline(API_KEY, API_BASE, MODEL_NAME)
    result = pipeline.run(demo_chat, "流行")
    pipeline.print_result(result)

    return result


# ==================== 命令行 ====================

def interactive_mode():
    """交互界面"""
    print("""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║        🎵 WeChatChat2Lyric-Agent v5.0 🎵                ║
║                                                          ║
║     Self-Optimizing Agent System                         ║
║     Global Constraint + Diff Edit + Meta-Agent           ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
    """)

    print("\n🎯 选项：")
    print("  1. 从文件加载")
    print("  2. 直接输入")
    print("  3. 演示")
    print("  0. 退出")

    choice = input("\n请输入: ").strip()

    if choice == "1":
        file_path = input("文件路径: ").strip()
        genre = input("曲风 (1流行/2民谣/3说唱/4抒情/5摇滚): ").strip()
        genre_map = {"1": "流行", "2": "民谣", "3": "说唱", "4": "抒情", "5": "摇滚"}
        genre = genre_map.get(genre, "流行")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                chat_text = f.read()

            pipeline = SelfOptimizingPipeline(API_KEY, API_BASE, MODEL_NAME)
            result = pipeline.run(chat_text, genre)
            pipeline.print_result(result)

            if input("\n保存？(y/n): ").strip().lower() == 'y':
                save_path = input("路径: ").strip()
                if save_path:
                    with open(save_path, 'w', encoding='utf-8') as f:
                        f.write(f"🎵 {result['title']}\n\n{result['lyrics']}")
                    print(f"✅ 已保存")
        except Exception as e:
            print(f"❌ 错误: {e}")

    elif choice == "2":
        print("\n粘贴聊天记录（EOF结束）：")
        lines = []
        while True:
            try:
                line = input()
                if line.strip().upper() == "EOF":
                    break
                lines.append(line)
            except:
                break

        pipeline = SelfOptimizingPipeline(API_KEY, API_BASE, MODEL_NAME)
        result = pipeline.run('\n'.join(lines), "流行")
        pipeline.print_result(result)

    elif choice == "3":
        run_demo()

    else:
        print("👋 再见！")


# ==================== 主入口 ====================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--demo":
            run_demo()
        elif sys.argv[1] == "--help":
            print("""
使用：python chat2lyric_agent.py
     python chat2lyric_agent.py --demo
     python chat2lyric_agent.py <file> [genre]
            """)
        else:
            file_path = sys.argv[1]
            genre = sys.argv[2] if len(sys.argv) > 2 else "流行"

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    chat_text = f.read()

                pipeline = SelfOptimizingPipeline(API_KEY, API_BASE, MODEL_NAME)
                result = pipeline.run(chat_text, genre)
                pipeline.print_result(result)
            except Exception as e:
                print(f"❌ 错误: {e}")
    else:
        interactive_mode()
