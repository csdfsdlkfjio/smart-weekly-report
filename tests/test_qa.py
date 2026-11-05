"""A5 极简智能问答测试。"""

from app.seed import seed_demo_data
from app.services.report_service import extract_tracking_keyword


def _ask(client, headers, question, dept_id=None):
    payload = {"question": question}
    if dept_id is not None:
        payload["dept_id"] = dept_id
    return client.post("/api/director/ask", json=payload, headers=headers)


def test_extract_keyword_from_question():
    assert extract_tracking_keyword("请问电子病历最近四周的进展？") == "电子病历"
    assert extract_tracking_keyword("护理质控最近进展如何？") == "护理质控"


def test_ask_electronic_medical_record(client, session_factory, login):
    seed_demo_data(session_factory())
    response = _ask(client, login("director"), "请问电子病历最近四周的进展？")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["found"] is True
    assert body["keyword"] == "电子病历"
    assert "第1周" in body["answer"]
    assert "陈医生" in body["answer"]
    assert "第3周未推进" in body["answer"]
    assert "电子病历" in body["answer"]


def test_ask_nursing_quality(client, session_factory, login):
    seed_demo_data(session_factory())
    response = _ask(client, login("director"), "护理质控最近四周进展如何？")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert "张医生" in body["answer"]
    assert "李医生" in body["answer"]
    assert "第3周未推进" in body["answer"]


def test_ask_unknown_keyword(client, session_factory, login):
    seed_demo_data(session_factory())
    response = _ask(client, login("director"), "不存在的关键词最近四周进展")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is False
    assert "未找到" in body["answer"]


def test_ask_requires_director(client, session_factory, login):
    seed_demo_data(session_factory())
    assert _ask(client, login("member_a"), "电子病历进展").status_code == 403
    assert _ask(client, login("leader"), "电子病历进展").status_code == 403


def test_ask_rejects_other_department(client, session_factory, login):
    seed_demo_data(session_factory())
    response = _ask(client, login("director"), "电子病历进展", dept_id=999)
    assert response.status_code == 403


def test_ask_rejects_empty_question(client, session_factory, login):
    seed_demo_data(session_factory())
    response = client.post(
        "/api/director/ask", json={"question": " "}, headers=login("director")
    )
    assert response.status_code == 422
