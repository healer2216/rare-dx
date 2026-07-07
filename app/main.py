"""rare-dx · 罕见病诊断辅助系统 — FastAPI 入口。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router as api_router
from .api.agent_routes import router as agent_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="rare-dx",
        description="罕见病诊断辅助系统 — 五层临床推理引擎",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(agent_router)
    return app


app = create_app()
