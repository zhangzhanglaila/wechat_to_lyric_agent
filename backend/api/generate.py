from fastapi import APIRouter, HTTPException
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
    final_event = None
    async for evt in stream_generate_async(req):
        if evt.get("step") == "final":
            final_event = evt
        elif evt.get("step") == "error":
            raise HTTPException(status_code=500, detail=evt.get("msg", "生成失败"))
    return final_event["data"] if final_event else {}


@router.post("/generate/stream")
async def generate_stream(req: GenerateRequest):
    """流式生成接口 — SSE。每个 token 实时推送，用户可见打字机效果。"""
    import json

    async def event_stream():
        try:
            async for evt in stream_generate_async(req):
                # evt 是 dict，直接 json 序列化后 yield
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
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
