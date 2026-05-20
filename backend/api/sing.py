"""
Sing API - 唱歌功能路由

提供歌词→歌曲的生成接口，SSE流式推送进度。
"""
import os
import json
import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse

from backend.schemas.sing import SingRequest
from backend.services.singer import stream_sing_async, SING_OUTPUT_DIR

router = APIRouter(prefix="/api", tags=["唱歌"])


@router.post("/sing")
async def sing(req: SingRequest):
    """
    同步唱歌接口（兼容模式）。
    内部消费SSE流，返回最终结果。
    """
    result = None
    try:
        async for evt in stream_sing_async(req):
            if evt.get("step") == "final":
                result = evt.get("data")
            elif evt.get("step") == "error":
                raise HTTPException(status_code=500, detail=evt.get("msg", "未知错误"))

        if result is None:
            raise HTTPException(status_code=500, detail="未生成结果")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sing/stream")
async def sing_stream(req: SingRequest):
    """
    SSE流式唱歌接口（主接口）。
    实时推送生成进度：parse → melody → midi → synth → tts → mix → final
    """
    async def event_stream():
        try:
            async for evt in stream_sing_async(req):
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        except Exception as e:
            error_payload = json.dumps(
                {"step": "error", "msg": str(e)},
                ensure_ascii=False
            )
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sing/audio/{filename}")
async def get_sing_audio(filename: str):
    """获取生成的音频文件"""
    # 安全检查：防止路径遍历
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="无效文件名")

    file_path = os.path.join(SING_OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")

    # 根据扩展名设置媒体类型
    if filename.endswith(".mp3"):
        media_type = "audio/mpeg"
    elif filename.endswith(".wav"):
        media_type = "audio/wav"
    else:
        media_type = "application/octet-stream"

    return FileResponse(file_path, media_type=media_type, filename=filename)
