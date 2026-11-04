"""FastAPI 入口。

启动方式：
    uvicorn app.main:app --port 8000
启动时自动建表并幂等灌入演示数据（AUTO_SEED=0 可关闭）。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.db import init_db
from app.exceptions import AppError
from app.routers import audit, auth, director, leader, member, meta
from app.seed import seed_demo_data
from app.services.week_service import ensure_current_week

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if config.AUTO_SEED:
        seed_demo_data()

    # 启动时确保周次覆盖今天：空库建当前周，旧库按周一至周日自动顺延
    created_weeks = ensure_current_week()
    if created_weeks:
        logger.info(
            "自动生成周次：%s",
            [
                f"第{week.week_no}周 {week.start_date}~{week.end_date}"
                for week in created_weeks
            ],
        )
    yield


app = FastAPI(
    title="智能周报系统",
    description="科室周报自动汇总与上报（MVP）",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def disable_static_cache(request: Request, call_next):
    """本地演示时避免浏览器缓存旧版 HTML/JS/CSS。"""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
    )


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(member.router)
app.include_router(director.router)
app.include_router(leader.router)
app.include_router(audit.router)

# 前端静态资源：/static/style.css、/static/app.js 等
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
