"""
Generator Service - 企业级高性能歌词/诗歌生成

架构原则：
- 单次 LLM 生成（不是几十次）
- SSE 每步实时推送，携带丰富内容
- Token 实时流式输出（async generator 直连 HTTP）

目标：< 15s 出结果，用户实时可见每一步
"""
import sys
import os
import json
import time
import asyncio
import queue
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent_os.integration import (
    EnhancedAgentOS, GenerationMode,
    CandidateScorer,
)
from agent_os.art_layer import EmotionVector


# ==================== 工具函数 ====================

def _safe_score(eos, candidate) -> float:
    """本地打分（不调 LLM），失败返回 0.0"""
    try:
        result = eos.scorer.score(candidate)
        if result is None:
            return 0.0
        score = result[0] if isinstance(result, tuple) else result
        return float(score) if score is not None else 0.0
    except Exception:
        return 0.0


def _build_constraints(req) -> dict:
    constraints = {
        "beam_width": req.beam_width,
        "max_refine_steps": min(req.max_refine_steps, 1),
    }
    if req.intensity is not None:
        constraints["intensity"] = req.intensity
    if req.expression is not None:
        constraints["expression"] = req.expression
    if req.lyric_density is not None:
        constraints["lyric_density"] = req.lyric_density
    if req.poem_form is not None:
        constraints["poem_form"] = req.poem_form
    if req.weights is not None:
        constraints["weights"] = req.weights
    if req.structure is not None:
        constraints["structure"] = req.structure
    return constraints


def _emit(step: str, msg: str, data, elapsed: float) -> dict:
    """创建事件 dict（直接 yield，无需回调）"""
    payload = {"step": step, "msg": msg, "elapsed": round(elapsed, 2)}
    if data is not None:
        payload["data"] = data
    return payload


# ==================== 核心生成逻辑 ====================

async def _gen_single_candidate(
    idx: int,
    eos, emotion_vector, gen_mode, style_template, constraints, dsl,
):
    """
    生成单个候选。是一个 async generator，yield 第一个 token 时通知主循环开始监听。

    每个候选独立，不依赖其他候选。
    """
    primary, intensity = emotion_vector.get_primary()

    # 用于 token 队列（跨线程安全）
    token_q: asyncio.Queue = asyncio.Queue()
    text_chunks = []
    done_event = asyncio.Event()

    def _on_token(token):
        """同步回调：把 token 放入队列（在 LLM 线程中调用）"""
        text_chunks.append(token)
        try:
            token_q.put_nowait(token)
        except queue.Full:
            pass

    # 启动后台生成协程
    async def _generate():
        try:
            if gen_mode == GenerationMode.LYRICS:
                async for _ in eos.text_gen.generate_from_dsl_streaming(
                    dsl, style_template, emotion_vector, gen_mode, _on_token,
                ):
                    pass
            else:
                async for _ in eos.text_gen.generate_poem_streaming(
                    dsl, style_template, emotion_vector, _on_token,
                ):
                    pass
        finally:
            done_event.set()

    gen_task = asyncio.create_task(_generate())

    # 立即 yield 第一个哨兵事件，通知主循环"这个候选开始了"
    yield {"type": "start", "idx": idx, "primary": primary, "intensity": intensity}

    # 主循环：持续从队列读 token，直到生成完毕
    while not done_event.is_set() or not token_q.empty():
        try:
            token = await asyncio.wait_for(token_q.get(), timeout=0.05)
            # yield token 事件（主循环负责格式化为 SSE）
            yield {"type": "token", "idx": idx, "token": token, "partial": "".join(text_chunks)}
        except asyncio.TimeoutError:
            continue

    await gen_task

    text = "".join(text_chunks)

    # 本地人类化处理（不调 LLM）
    text = await asyncio.to_thread(
        eos.humanizer.humanize,
        text, intensity=constraints.get("humanize_intensity", 0.3),
    )

    # 本地提取 Hook（规则匹配，不调 LLM）
    hook = eos._extract_hook(text, gen_mode)

    yield {
        "type": "candidate",
        "idx": idx,
        "text": text,
        "hook": hook,
        "dsl": dsl,
        "emotion": primary,
        "emotion_intensity": intensity,
        "result_type": "lyrics" if gen_mode == GenerationMode.LYRICS else "poem",
        "score": 0.0,
    }


async def _rank_and_refine(
    eos, candidates, emotion_vector, gen_mode, style_template,
    constraints, objective_fn, style_checker,
):
    """
    排序 + 可选一次 refine。
    返回 (best_candidate, refine_steps_list, list_of_events_to_yield)
    """
    t0 = time.time()
    events = []

    def emit(step, msg, data=None):
        events.append(_emit(step, msg, data, time.time() - t0))

    # 1. 打分
    for c in candidates:
        c["score"] = _safe_score(eos, c)

    # 2. 排序
    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    emit("rank", "候选排序完成", {
        "top_score": best["score"],
        "total": len(candidates),
        "candidates": [
            {"index": i + 1, "score": c["score"], "hook": c.get("hook", "")[:30]}
            for i, c in enumerate(candidates)
        ],
    })

    # 3. 可选一次 refine
    if constraints.get("max_refine_steps", 0) <= 0:
        emit("done", f"生成完成 (score: {best['score']:.3f})", {
            "final_score": best["score"],
            "refine_steps": 0,
        })
        return best, [], events

    REFINE_THRESHOLD = 0.5
    if best["score"] >= REFINE_THRESHOLD:
        emit("done", f"生成完成，无需精修 (score: {best['score']:.3f})", {
            "final_score": best["score"],
            "refine_steps": 0,
        })
        return best, [], events

    emit("refine_start", "开始一次精修...")

    issues = await asyncio.to_thread(
        eos.analyzer.analyze, best["text"], gen_mode, best.get("emotion"),
    )

    if not any(issues.values()):
        emit("done", f"生成完成 (score: {best['score']:.3f})", {
            "final_score": best["score"],
            "refine_steps": 0,
        })
        return best, [], events

    best["text"], applied_op = await asyncio.to_thread(
        eos.refine_loop.refine,
        best["text"], style_template, emotion_vector, gen_mode,
        objective_fn=objective_fn,
        style_checker=style_checker,
        issues=issues,
        beam_width=constraints.get("beam_width", 1),
    )
    best["hook"] = eos._extract_hook(best["text"], gen_mode)
    best["score"] = _safe_score(eos, best)

    op_label = applied_op if applied_op else "无需修改"
    emit("refine_done", f"精修完成: {op_label}", {
        "op": applied_op,
        "score": best["score"],
        "before_score": candidates[0].get("score", 0),
        "issues": [k for k, v in issues.items() if v],
    })

    refine_steps = [{"step": 0, "issues": [k for k, v in issues.items() if v], "applied_op": applied_op}]
    return best, refine_steps, events


# ==================== 主入口 ====================

async def stream_generate_async(req):
    """
    企业级流式生成（async generator 版本）。

    直接 yield 事件 dict：
    - 主循环实时消费 token 事件并立即 yield 到 HTTP 层
    - 每个候选是独立 async generator，token 到达时立即推送

    流程：
    1. parse + emotion（本地，ms）
    2. dsl 生成（LLM 1次，~1-3s）
    3. 并发候选生成，每个 token 实时 yield（~3-5s/候选）
    4. 排序（~ms）
    5. final
    """
    t0 = time.time()

    def emit(step, msg, data=None):
        return _emit(step, msg, data, time.time() - t0)

    try:
        eos = EnhancedAgentOS()
        gen_mode = GenerationMode.LYRICS if req.mode == "lyrics" else GenerationMode.POEM
        constraints = _build_constraints(req)

        # ===== Step 1: parse =====
        yield emit("parse", "解析输入...", {"input": req.text[:50]})

        if isinstance(req.text, list):
            compression_result = await asyncio.to_thread(
                eos.compression.compress, req.text
            )
            emotion_vector = compression_result["emotion_vector"]
        else:
            emotion_vector = await asyncio.to_thread(
                eos._emotion_from_keywords, req.text
            )

        primary_emotion, intensity = emotion_vector.get_primary()
        style_template = eos._resolve_style(req.style, gen_mode)

        for k in ["expression", "lyric_density", "poem_form"]:
            if k in constraints:
                setattr(style_template, k, constraints[k])

        yield emit("emotion", f"情绪建模: {primary_emotion} ({intensity:.1f})", {
            "emotion": primary_emotion,
            "intensity": intensity,
            "style": style_template.name if style_template else "default",
        })

        # ===== Step 2: DSL 生成 =====
        yield emit("dsl", "生成结构...")
        dsl = await asyncio.to_thread(
            eos.dsl_gen.generate,
            emotion_vector, gen_mode, style_template,
            user_structure=constraints.get("structure"),
            poem_form=constraints.get("poem_form"),
        )
        yield emit("dsl_done", f"结构生成完成 ({len(dsl)} 节)", {
            "sections": len(dsl),
            "preview": [s.get("section", "") + ":" + s.get("intent", "")[:10] for s in dsl],
        })

        # ===== Step 3: 并发候选生成 + token 实时流式推送 =====
        num_candidates = min(req.candidates, 3)
        yield emit("generate", f"正在生成 {num_candidates} 个候选歌词...", {
            "count": num_candidates,
        })

        # 启动所有候选生成器
        candidate_gens = [
            _gen_single_candidate(
                i, eos, emotion_vector, gen_mode,
                style_template, constraints, dsl,
            )
            for i in range(num_candidates)
        ]

        # 启动所有候选任务
        pending = {asyncio.create_task(cg.__anext__()) for cg in candidate_gens}
        candidate_results = [None] * num_candidates
        started_candidates = set()
        accumulated = [""] * num_candidates  # 每个候选的累积文本

        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for finished_task in done:
                try:
                    event = finished_task.result()
                    idx = event["idx"]

                    if event["type"] == "start":
                        # 候选开始，立即创建后续任务继续消费这个候选的 token
                        started_candidates.add(idx)
                        pending.add(asyncio.create_task(candidate_gens[idx].__anext__()))

                    elif event["type"] == "token":
                        accumulated[idx] = event["partial"]
                        # ★ 核心：立即 yield token 事件 → HTTP 层实时推送
                        yield _emit("token", "", {
                            "candidate_index": idx + 1,
                            "total": num_candidates,
                            "partial_text": event["partial"],
                        }, time.time() - t0)

                        # 继续消费这个候选
                        pending.add(asyncio.create_task(candidate_gens[idx].__anext__()))

                    elif event["type"] == "candidate":
                        candidate_results[idx] = event
                        # 候选完成，打分并 yield candidate 事件
                        c = event
                        c["score"] = _safe_score(eos, c)
                        yield _emit("candidate", f"候选 {idx+1}/{num_candidates} 生成完成", {
                            "index": idx + 1,
                            "score": c["score"],
                            "hook": c.get("hook", "")[:40],
                            "preview": c.get("text", "")[:80],
                            "text": c.get("text", ""),
                        }, time.time() - t0)
                        # 不再为这个候选创建任务

                except StopAsyncIteration:
                    pass

        # ===== Step 4: 打分排序 =====
        best, refine_steps, rank_events = await _rank_and_refine(
            eos, candidate_results, emotion_vector, gen_mode,
            style_template, constraints, eos.objective_fn,
            eos.style_checker,
        )
        for evt in rank_events:
            yield evt

        # ===== Step 5: Baseline 对比（默认关闭）=====
        bl_text = bl_hook = ""
        bl_score = 0.0
        bl_details = {}
        scorer = CandidateScorer()

        if getattr(req, 'include_baseline', False):
            yield emit("baseline", "正在生成 baseline 对比...", None)
            bl_text, bl_hook, bl_score, bl_details = await asyncio.to_thread(
                _run_baseline_sync,
                eos, req.text, req.mode, req.style, constraints,
                gen_mode, style_template, emotion_vector, dsl,
            )

        _, opt_details = scorer.score(best) if best else (0.0, {})

        # ===== Step 6: 最终结果 =====
        yield emit("final", "创作完成", {
            "mode": req.mode,
            "style": style_template.name if style_template else "default",
            "emotion": best.get("emotion", primary_emotion) if best else primary_emotion,
            "emotion_intensity": best.get("emotion_intensity", intensity) if best else intensity,
            "baseline_text": bl_text,
            "baseline_hook": bl_hook,
            "baseline_score": bl_score,
            "baseline_score_details": bl_details,
            "optimized_text": best.get("text", "") if best else "",
            "optimized_hook": best.get("hook", "") if best else "",
            "optimized_score": best.get("score", 0) if best else 0,
            "optimized_score_details": opt_details,
            "delta": (best.get("score", 0) - bl_score) if best else 0.0,
            "explanation": {
                "emotion_arc": f"{primary_emotion} ({intensity:.1f})",
                "style_decisions": {
                    "expression": getattr(style_template, 'expression', None),
                    "lyric_density": getattr(style_template, 'lyric_density', None),
                    "poem_form": getattr(style_template, 'poem_form', None),
                },
                "structure_type": style_template.name if style_template else "default",
                "hook_strategy": "single-pass generation",
                "objective_weights": constraints.get("weights"),
                "optimization_steps": refine_steps,
                "final_refine_steps": len(refine_steps),
            },
            "candidates": [
                {
                    "index": i + 1,
                    "text": c.get("text", ""),
                    "score": c.get("score", 0),
                    "hook": c.get("hook", ""),
                }
                for i, c in enumerate(candidate_results)
            ],
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        yield _emit("error", f"生成失败: {e}", None, time.time() - t0)


def _run_baseline_sync(eos, text, mode, style, constraints, gen_mode, style_template, emotion_vector, dsl):
    """在子线程运行 baseline 生成"""
    text_out = eos.text_gen.generate_from_dsl(dsl, style_template, emotion_vector, gen_mode)
    text_out = eos.humanizer.humanize(
        text_out, intensity=constraints.get("humanize_intensity", 0.3)
    )
    hook = eos._extract_hook(text_out, gen_mode)
    scorer = CandidateScorer()
    dummy = type("obj", (object,), {
        "type": mode, "text": text_out, "hook": hook,
        "structure_dsl": dsl, "emotion": emotion_vector.get_primary()[0],
        "emotion_intensity": 0.5, "score": 0.0, "score_details": {},
    })()
    score, details = scorer.score(dummy)
    return text_out, hook, score, details
