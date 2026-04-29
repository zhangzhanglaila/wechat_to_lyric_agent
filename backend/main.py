"""
GenWriter Agent - FastAPI Backend
"""
import os
from dotenv import load_dotenv

# 显式加载 .env，确保子进程也能读到环境变量
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.api.generate import router as generate_router

app = FastAPI(
    title="GenWriter Agent API",
    description="可控歌词/诗歌生成系统 — LLM + 搜索优化",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate_router)

# 前端静态文件（打包后）
dist_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(dist_dir):
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")
else:
    @app.get("/")
    async def root():
        return {"msg": "frontend/dist not found. Run: cd frontend && npm run build"}


if __name__ == "__main__":
    import uvicorn
    print()
    print("🚀  GenWriter Agent")
    print("   Server:  http://localhost:8000")
    print("   API:     http://localhost:8000/docs")
    print()
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
