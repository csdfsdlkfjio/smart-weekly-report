"""FastAPI 入口。

启动方式：
    uvicorn app.main:app --port 8000
启动时自动建表；演示数据由后续阶段的 seed 脚本灌入。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.db import init_db
from app.exceptions import AppError
from app.routers import audit, auth, director, leader, member, meta


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="智能周报系统",
    description="科室周报自动汇总与上报（MVP）",
    version="0.1.0",
    lifespan=lifespan,
)


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
def root() -> dict[str, str]:
    return {"name": "智能周报系统", "docs": "/docs", "health": "/api/health"}


app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(member.router)
app.include_router(director.router)
app.include_router(leader.router)
app.include_router(audit.router)
