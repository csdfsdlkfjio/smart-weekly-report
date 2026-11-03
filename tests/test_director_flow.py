"""主任主链路：看板、汇总、编辑、定稿、上报与院领导查阅。"""


def test_overview_shows_missing_members(client, seed, login, submit_report):
    submit_report("member_a", seed["week1_id"], done=["完成护理质控检查"])
    headers = login("director")

    response = client.get(
        "/api/director/overview", params={"week_id": seed["week1_id"]}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["submitted_count"] == 1
    assert body["missing_count"] == 4
    assert "赵医生" in body["missing_names"]
    statuses = {row["username"]: row["status"] for row in body["members"]}
    assert statuses["member_a"] == "已提交"
    assert statuses["member_d"] == "未提交"


def test_main_chain_merge_finalize_report_and_leader_read(client, seed, login, submit_report):
    # A 与 B 写同一事项，用于验证归并与来源标注
    submit_report("member_a", seed["week1_id"], done=["完成护理质控检查"], plan=["开展护理培训"])
    submit_report("member_b", seed["week1_id"], done=["完成护理质控检查"], plan=["优化排班"])
    director_headers = login("director")

    aggregated = client.post(
        "/api/director/aggregate",
        json={"week_id": seed["week1_id"]},
        headers=director_headers,
    )
    assert aggregated.status_code == 200, aggregated.text
    dept_report = aggregated.json()
    dept_report_id = dept_report["id"]
    assert dept_report["status"] == "已汇总"

    done_items = [item for item in dept_report["items"] if item["category"] == "done"]
    assert len(done_items) == 1, "重复事项必须合并为一条"
    merged = done_items[0]
    assert merged["content"] == "完成护理质控检查"
    assert set(merged["source_user_ids"]) == {
        seed["user_ids"]["member_a"],
        seed["user_ids"]["member_b"],
    }
    assert set(merged["source_names"]) == {"张医生", "李医生"}
    assert [item["sort_order"] for item in dept_report["items"]] == list(
        range(len(dept_report["items"]))
    )

    # 未上报前院领导不可见
    leader_headers = login("leader")
    assert client.get("/api/leader/reports", headers=leader_headers).json() == []

    # 主任编辑：保留原条目，补一条需协调事项，并调整顺序
    items = [dict(item) for item in dept_report["items"]]
    items.reverse()
    items.append(
        {
            "category": "coord",
            "content": "协调设备采购流程",
            "source_user_ids": [],
            "source_names": [],
        }
    )
    updated = client.put(
        f"/api/director/dept-report/{dept_report_id}/items",
        json={"items": items},
        headers=director_headers,
    )
    assert updated.status_code == 200, updated.text
    assert len(updated.json()["items"]) == len(items)
    assert [item["sort_order"] for item in updated.json()["items"]] == list(range(len(items)))
    assert all(
        item["edited_by"] == seed["user_ids"]["director"] for item in updated.json()["items"]
    )

    summary = client.put(
        f"/api/director/dept-report/{dept_report_id}/summary",
        json={"summary": "本周科室完成 3 项重点工作，护理质控覆盖全部病房。"},
        headers=director_headers,
    )
    assert summary.status_code == 200
    assert summary.json()["summary"].startswith("本周科室完成")

    finalized = client.post(
        f"/api/director/dept-report/{dept_report_id}/finalize", headers=director_headers
    )
    assert finalized.status_code == 200
    assert finalized.json()["status"] == "已定稿"
    assert finalized.json()["finalized_at"] is not None

    # 定稿后再次定稿属于非法流转
    repeated = client.post(
        f"/api/director/dept-report/{dept_report_id}/finalize", headers=director_headers
    )
    assert repeated.status_code == 400
    assert repeated.json()["code"] == "invalid_transition"

    # 未上报前，定稿稿对院领导仍不可见
    assert client.get("/api/leader/reports", headers=leader_headers).json() == []

    reported = client.post(
        f"/api/director/dept-report/{dept_report_id}/report", headers=director_headers
    )
    assert reported.status_code == 200
    assert reported.json()["status"] == "已上报"
    assert reported.json()["reported_at"] is not None

    # 院领导可查阅，并支持周次/科室筛选
    leader_reports = client.get("/api/leader/reports", headers=leader_headers)
    assert leader_reports.status_code == 200
    assert len(leader_reports.json()) == 1
    leader_view = leader_reports.json()[0]
    assert leader_view["dept_name"] == "心内科"
    assert leader_view["week_no"] == 1
    assert leader_view["status"] == "已上报"

    filtered = client.get(
        "/api/leader/reports",
        params={"week_id": seed["week1_id"], "dept_id": seed["dept2_id"]},
        headers=leader_headers,
    )
    assert filtered.json() == []

    # 上报后主任不能再编辑
    blocked = client.put(
        f"/api/director/dept-report/{dept_report_id}/summary",
        json={"summary": "试图修改已上报内容"},
        headers=director_headers,
    )
    assert blocked.status_code == 400

    # 全链路操作可在时间线中追溯
    timeline = client.get(
        f"/api/audit/dept_report/{dept_report_id}", headers=director_headers
    )
    assert timeline.status_code == 200
    actions = [event["action"] for event in timeline.json()]
    for expected in ("aggregate", "update_items", "update_summary", "finalize", "report"):
        assert expected in actions

    leader_timeline = client.get(
        f"/api/audit/dept_report/{dept_report_id}", headers=leader_headers
    )
    assert leader_timeline.status_code == 200


def test_aggregate_requires_submitted_reports(client, seed, login):
    response = client.post(
        "/api/director/aggregate",
        json={"week_id": seed["week1_id"]},
        headers=login("director"),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_aggregate_twice_is_rejected(client, seed, login, submit_report):
    submit_report("member_a", seed["week1_id"])
    headers = login("director")
    first = client.post(
        "/api/director/aggregate", json={"week_id": seed["week1_id"]}, headers=headers
    )
    assert first.status_code == 200

    second = client.post(
        "/api/director/aggregate", json={"week_id": seed["week1_id"]}, headers=headers
    )
    assert second.status_code == 409
    assert second.json()["code"] == "conflict"
