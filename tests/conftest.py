from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import auth, models
from app.db import Base, get_db
from app.main import app as fastapi_app


@pytest.fixture()
def session_factory(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture()
def seed(session_factory):
    db = session_factory()
    dept1 = models.Department(name="心内科")
    dept2 = models.Department(name="骨科")
    db.add_all([dept1, dept2])
    db.flush()

    password_hash = auth.hash_password("demo123")
    users = {
        "member_a": models.User(
            username="member_a", name="张医生", role="member", dept_id=dept1.id, password_hash=password_hash
        ),
        "member_b": models.User(
            username="member_b", name="李医生", role="member", dept_id=dept1.id, password_hash=password_hash
        ),
        "member_c": models.User(
            username="member_c", name="王医生", role="member", dept_id=dept1.id, password_hash=password_hash
        ),
        "member_d": models.User(
            username="member_d", name="赵医生", role="member", dept_id=dept1.id, password_hash=password_hash
        ),
        "member_e": models.User(
            username="member_e", name="陈医生", role="member", dept_id=dept1.id, password_hash=password_hash
        ),
        "member_x": models.User(
            username="member_x", name="刘医生", role="member", dept_id=dept2.id, password_hash=password_hash
        ),
        "director": models.User(
            username="director", name="王主任", role="director", dept_id=dept1.id, password_hash=password_hash
        ),
        "director2": models.User(
            username="director2", name="李主任", role="director", dept_id=dept2.id, password_hash=password_hash
        ),
        "leader": models.User(
            username="leader", name="院领导", role="leader", dept_id=None, password_hash=password_hash
        ),
        "admin": models.User(
            username="admin", name="管理员", role="admin", dept_id=None, password_hash=password_hash
        ),
    }
    db.add_all(users.values())
    db.flush()

    week1 = models.Week(
        week_no=1,
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 26),
        deadline=datetime(2026, 10, 27, 23, 59),
    )
    week2 = models.Week(
        week_no=2,
        start_date=date(2026, 10, 27),
        end_date=date(2026, 11, 2),
        deadline=datetime(2026, 11, 3, 23, 59),
    )
    db.add_all([week1, week2])
    db.commit()

    result = {
        "dept1_id": dept1.id,
        "dept2_id": dept2.id,
        "week1_id": week1.id,
        "week2_id": week2.id,
        "user_ids": {key: user.id for key, user in users.items()},
    }
    db.close()
    return result


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(fastapi_app)
    try:
        yield test_client
    finally:
        fastapi_app.dependency_overrides.clear()
        test_client.close()


@pytest.fixture()
def login(client):
    def _login(username: str, password: str = "demo123") -> dict[str, str]:
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _login


@pytest.fixture()
def submit_report(client, login):
    """快捷提交：一次草稿 + 一次提交，返回响应 JSON 与 headers。"""

    def _submit(
        username: str,
        week_id: int,
        *,
        done: list[str] | None = None,
        plan: list[str] | None = None,
        issue: list[str] | None = None,
        coord: list[str] | None = None,
    ) -> tuple[dict, dict[str, str]]:
        headers = login(username)
        payload = {
            "week_id": week_id,
            "done": done if done is not None else ["完成日常诊疗工作"],
            "plan": plan if plan is not None else ["按计划推进下周工作"],
            "issue": issue or [],
            "coord": coord or [],
        }
        draft = client.post("/api/member/report/draft", json=payload, headers=headers)
        assert draft.status_code == 200, draft.text
        submitted = client.post(
            "/api/member/report/submit",
            json={"week_id": week_id},
            headers=headers,
        )
        assert submitted.status_code == 200, submitted.text
        return submitted.json(), headers

    return _submit
