from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from backend.schemas.generate import GenerateRequest, GenerateResponse
from backend.services.generator import stream_generate_async

router = APIRouter(prefix="/api", tags=["生成"])


@router.get("/test_llm")
async def test_llm():
    """LLM 连通性测试"""
    import time
    t0 = time.time()
    try:
        from agent_os.art_layer import llm
        result = llm("Say 'LLM OK' in Chinese", temp=0.0)
        elapsed = time.time() - t0
        return {
            "status": "success",
            "elapsed": round(elapsed, 2),
            "response": result.strip(),
        }
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "status": "error",
            "elapsed": round(elapsed, 2),
            "error": str(e),
        }


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """同步生成接口（保留兼容）"""
    from backend.services.generator import stream_generate_async
    import json

    async def sync_wrapper():
        def sse_format(step, msg, data, elapsed):
            payload = {"step": step, "msg": msg, "elapsed": round(elapsed, 2)}
            if data is not None:
                payload["data"] = data
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        result_data = None
        async for item in stream_generate_async(req, sse_format):
            if item:
                result_data = item
        return result_data

    return {"status": "ok"}


@router.post("/generate/stream")
async def generate_stream(req: GenerateRequest):
    """流式生成接口 — SSE。LLM 调用期间事件循环保持活跃，可实时推送每一步。"""
    import json

    def sse_format(step, msg, data, elapsed):
        payload = {"step": step, "msg": msg, "elapsed": round(elapsed, 2)}
        if data is not None:
            payload["data"] = data
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def event_stream():
        try:
            async for item in stream_generate_async(req, sse_format):
                if item:
                    yield item
        except Exception as e:
            import traceback
            traceback.print_exc()
            error_payload = json.dumps({"step": "error", "msg": str(e)}, ensure_ascii=False)
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
