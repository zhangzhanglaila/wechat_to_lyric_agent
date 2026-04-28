"""
v12.x GenWriter Agent - 歌词/诗歌生成引擎
==============================================================
统一入口：generate(content, mode, style, constraints)

用法：
    # 基础生成
    python chat2lyric_agent.py --input chat.txt --mode lyrics --style douyin_sad

    # 带创作说明输出
    python chat2lyric_agent.py --input keywords.txt --mode poem --style modern --explain

    # Baseline 对比（不加优化链的原始生成）
    python chat2lyric_agent.py --input chat.txt --mode lyrics --baseline

    # 完整可配置
    python chat2lyric_agent.py --input chat.txt --mode lyrics \\
        --style douyin_sad --intensity 0.8 \\
        --candidates 3 --beam-width 2 \\
        --explain --show-candidates
"""

import os
import argparse
import json
from dotenv import load_dotenv

load_dotenv()

# 禁用代理
for k in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
    os.environ.pop(k, None)


def format_score_table(score_details: dict, total: float) -> str:
    """格式化分数详情为 ASCII 表格"""
    lines = []
    lines.append(f"  Total   : {total:.2f}")
    lines.append("  ─────   : ──────")
    for key, val in score_details.items():
        if key == "total":
            continue
        bar = "█" * int(val * 10) + "░" * (10 - int(val * 10))
        lines.append(f"  {key:<12} : {bar} {val:.2f}")
    return "\n".join(lines)


def format_explanation(explanation: dict) -> str:
    """格式化创作说明"""
    lines = []
    arc = explanation.get("emotion_arc", "unknown")
    style_dec = explanation.get("style_decisions", {})
    hook_st = explanation.get("hook_strategy", "default")
    opt_steps = explanation.get("optimization_steps", [])
    weights = explanation.get("objective_weights")

    lines.append(f"  情绪演化  : {arc}")
    lines.append(f"  表达方式  : {style_dec.get('expression', 'N/A')}")
    lines.append(f"  句长风格  : {style_dec.get('lyric_density', 'N/A')}")
    if style_dec.get("poem_form"):
        lines.append(f"  诗歌体裁  : {style_dec.get('poem_form')}")
    lines.append(f"  Hook策略  : {hook_st}")
    if weights:
        lines.append(f"  权重配置  : {weights}")
    lines.append(f"  优化步数  : {explanation.get('final_refine_steps', 0)}")

    if opt_steps:
        lines.append("  ──────────────────")
        for step in opt_steps:
            issues = ", ".join(step.get("issues", [])) or "—"
            op = step.get("applied_op") or "—"
            lines.append(f"    Step {step.get('step', 0)+1}: [{issues}] → {op}")

    return "\n".join(lines)


def run_baseline(content, mode, style, constraints: dict) -> tuple:
    """
    Baseline 生成：跳过 refine loop，只保留 DSL + 人类化。
    用于对比优化效果。
    """
    from agent_os.integration import (
        EnhancedAgentOS, StructureDSLGenerator, TextGenerator,
        HookOptimizer, CandidateScorer, GenerationMode,
    )
    from agent_os.art_layer import get_style_template, StylePreset, EmotionVector

    eos = EnhancedAgentOS()
    gen_mode = GenerationMode.LYRICS if mode == "lyrics" else GenerationMode.POEM
    style_template = eos._resolve_style(style, gen_mode)

    # 覆盖 constraints 中的字段
    for k in ["expression", "lyric_density", "poem_form"]:
        if k in constraints:
            setattr(style_template, k, constraints[k])

    if isinstance(content, list):
        compression_result = eos.compression.compress(content)
        emotion_vector = compression_result["emotion_vector"]
    else:
        emotion_vector = eos._emotion_from_keywords(content)

    # DSL
    dsl = eos.dsl_gen.generate(
        emotion_vector, gen_mode, style_template,
        user_structure=constraints.get("structure"),
        poem_form=constraints.get("poem_form"),
    )

    # 文本生成
    text = eos.text_gen.generate_from_dsl(dsl, style_template, emotion_vector, gen_mode)
    raw_text = text

    # 人类化
    intensity = constraints.get("humanize_intensity", 0.3)
    text = eos.humanizer.humanize(text, intensity=intensity)

    # Hook
    hook = eos._extract_hook(text, gen_mode)

    # 评分
    scorer = CandidateScorer()
    dummy_result = type('obj', (object,), {
        "type": mode, "text": text, "hook": hook,
        "structure_dsl": dsl, "emotion": emotion_vector.get_primary()[0],
        "emotion_intensity": 0.5, "score": 0.0, "score_details": {},
    })()
    score, details = scorer.score(dummy_result)

    return text, hook, score, details


def main():
    parser = argparse.ArgumentParser(
        description="GenWriter Agent - 歌词/诗歌生成引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python chat2lyric_agent.py --input chat.txt --mode lyrics --style douyin_sad
  python chat2lyric_agent.py --input keywords.txt --mode poem --style modern --explain
  python chat2lyric_agent.py --input chat.txt --mode lyrics --baseline --explain
  python chat2lyric_agent.py --input chat.txt --mode lyrics --intensity 0.9 --beam-width 3 --explain
        """
    )
    parser.add_argument("--input", type=str, required=True,
                        help="输入文件路径（支持 JSON 聊天记录或纯文本关键词）")
    parser.add_argument("--mode", type=str, default="lyrics",
                        choices=["lyrics", "poem"],
                        help="生成模式：歌词(lyrics) 或 诗歌(poem)")
    parser.add_argument("--style", type=str, default=None,
                        help="风格: douyin_sad / rap / pop / emo_pop / modern / classical / imagist / diary")
    parser.add_argument("--candidates", type=int, default=3,
                        help="候选数量（默认3）")
    parser.add_argument("--intensity", type=float, default=None,
                        help="情绪强度 0.0~1.0")
    parser.add_argument("--expression", type=str, default=None,
                        choices=["direct", "metaphor", "self_mock"],
                        help="表达方式")
    parser.add_argument("--lyric-density", type=str, default=None,
                        choices=["short", "medium", "long"],
                        help="句长风格")
    parser.add_argument("--beam-width", type=int, default=2,
                        help="束搜索宽度（默认2）")
    parser.add_argument("--max-refine", type=int, default=3,
                        help="最大优化步数（默认3）")
    parser.add_argument("--explain", action="store_true",
                        help="显示创作说明")
    parser.add_argument("--show-candidates", action="store_true",
                        help="显示所有候选及其分数")
    parser.add_argument("--baseline", action="store_true",
                        help="同时输出 Baseline 对比（无优化链的原始生成）")
    parser.add_argument("--save", type=str, default=None,
                        help="保存路径")

    args = parser.parse_args()

    # 读取输入
    with open(args.input, encoding="utf-8") as f:
        content_text = f.read()

    # 解析：聊天记录(list) 或 关键词(str)
    try:
        parsed = json.loads(content_text)
        content = parsed if isinstance(parsed, list) else content_text.strip()
    except json.JSONDecodeError:
        content = content_text.strip()

    # 构建约束
    constraints = {}
    if args.intensity is not None:
        constraints["intensity"] = args.intensity
    if args.expression:
        constraints["expression"] = args.expression
    if args.lyric_density:
        constraints["lyric_density"] = args.lyric_density
    constraints["beam_width"] = args.beam_width
    constraints["max_refine_steps"] = args.max_refine

    mode = args.mode
    style = args.style

    from agent_os.integration import EnhancedAgentOS

    # ── Baseline ──────────────────────────────────────────────
    if args.baseline:
        bl_text, bl_hook, bl_score, bl_details = run_baseline(
            content, mode, style, constraints
        )
        print(f"\n{'='*56}")
        print(f"  Baseline（无优化链的原始 LLM 生成）")
        print(f"{'='*56}")
        print()
        print("【歌词】")
        print("-" * 56)
        print(bl_text)
        print("-" * 56)
        print()
        print(f"【Hook】{bl_hook}")
        print()
        print("【分数】")
        print(format_score_table(bl_details, bl_score))
        print()
        print(f"{'='*56}")
        print(f"  优化后（完整管线）")
        print(f"{'='*56}")
        print()

    # ── 主生成 ────────────────────────────────────────────────
    eos = EnhancedAgentOS()
    result = eos.generate(
        content=content,
        mode=mode,
        style=style,
        constraints=constraints,
        num_candidates=args.candidates,
    )

    mode_label = "LYRICS" if mode == "lyrics" else "POEM"
    print(f"\n{'='*56}")
    print(f"  GenWriter Agent  |  {mode_label}  |  {result.style}")
    print(f"{'='*56}")

    # 创作说明
    if args.explain:
        print()
        print("【创作说明】")
        print("-" * 56)
        print(format_explanation(result.creation_explanation))
        print("-" * 56)

    # 主结果
    print()
    print("【歌词】")
    print("-" * 56)
    print(result.text)
    print("-" * 56)
    print()
    print(f"【Hook】{result.hook}")
    print()

    # 分数
    print("【分数】")
    print(format_score_table(result.score_details, result.score))

    # 候选
    if args.show_candidates:
        print()
        print(f"【{args.candidates} 个候选】")
        print("-" * 56)
        for i, c in enumerate(result.candidates):
            c_score = eos.scorer.score(c)[0]
            print(f"\n  [Candidate {i+1}]  score={c_score:.2f}")
            print(f"  {c.text[:200]}...")

    # Baseline 对比
    if args.baseline:
        improvement = result.score - bl_score
        arrow = "↑" if improvement > 0 else "↓"
        print()
        print(f"【对比】Baseline {bl_score:.2f}  {arrow}  System {result.score:.2f}  "
              f"(Δ {improvement:+.2f})")

    # 保存
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(f"# {result.style} | {result.emotion}\n\n")
            f.write(result.text)
            if result.hook:
                f.write(f"\n\n# Hook: {result.hook}\n")
            if args.explain:
                f.write(f"\n# Score: {result.score:.2f}\n")
                f.write(f"\n# Explanation:\n")
                for line in format_explanation(result.creation_explanation).split("\n"):
                    f.write(f"# {line}\n")
        print(f"\n✅ 已保存: {args.save}")


if __name__ == "__main__":
    main()
