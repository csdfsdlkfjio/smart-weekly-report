"""数据库连接与会话管理。"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app import config


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def _connect_args(url: str) -> dict:
    # SQLite 默认不允许跨线程复用连接；FastAPI 的线程池需要关闭该限制。
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


engine = create_engine(config.DATABASE_URL, connect_args=_connect_args(config.DATABASE_URL))

if config.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


def init_db() -> None:
    """建表；幂等，可重复调用。"""
    from app import models  # noqa: F401  确保模型已注册到 Base.metadata

    if config.DATABASE_URL.startswith("sqlite"):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个会话，异常时回滚。"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
