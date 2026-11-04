"""异常链路：退回理由、历史版本、重提与重新汇总。"""


def test_return_and_resubmit_keep_versions(client, seed, login, submit_report):
    week_id = seed["week1_id"]
    submit_report("member_a", week_id, done=["完成护理质控检查"])
    submit_report("member_b", week_id, done=["完成护理质控检查"])

    director_headers = login("director")
    aggregated = client.post(
        "/api/director/aggregate", json={"week_id": week_id}, headers=director_headers
    )
    assert aggregated.status_code == 200
    dept_report_id = aggregated.json()["id"]

    member_headers = login("member_a")
    member_report = client.get(
        "/api/member/report", params={"week_id": week_id}, headers=member_headers
    ).json()
    member_report_id = member_report["id"]
    assert member_report["status"] == "已提交"

    reason = "内容过于笼统，请补充量化数据"
    returned = client.post(
        f"/api/director/dept-report/{dept_report_id}/return",
        json={"member_report_id": member_report_id, "reason": reason},
        headers=director_headers,
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["dept_report"]["status"] == "已退回"
    assert returned.json()["member_report"]["status"] == "已退回"

    # 成员看到退回理由，且恢复可编辑
    after_return = client.get(
        "/api/member/report", params={"week_id": week_id}, headers=member_headers
    ).json()
    assert after_return["status"] == "已退回"
    assert after_return["return_reason"] == reason
    assert after_return["locked"] is False

    # 退回前已提交的版本仍在
    versions_before = client.get(
        "/api/member/report/versions", params={"week_id": week_id}, headers=member_headers
    ).json()
    assert len(versions_before) == 1
    assert versions_before[0]["snapshot"]["done"] == ["完成护理质控检查"]

    # 成员修改后重新提交 → 已提交、版本 +1
    resaved = client.post(
        "/api/member/report/draft",
        json={
            "week_id": week_id,
            "done": ["完成护理质控检查 3 次，覆盖 100% 病房"],
            "plan": ["继续跟踪整改"],
            "issue": [],
            "coord": [],
        },
        headers=member_headers,
    )
    assert resaved.status_code == 200
    assert resaved.json()["status"] == "已退回"

    resubmitted = client.post(
        "/api/member/report/submit", json={"week_id": week_id}, headers=member_headers
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["status"] == "已提交"
    assert resubmitted.json()["version"] == 2
    assert resubmitted.json()["return_reason"] is None

    versions_after = client.get(
        "/api/member/report/versions", params={"week_id": week_id}, headers=member_headers
    ).json()
    assert [item["version"] for item in versions_after] == [1, 2]
    assert versions_after[1]["snapshot"]["done"] == ["完成护理质控检查 3 次，覆盖 100% 病房"]

    # 重新汇总：退回后汇总稿回到已汇总，且包含成员的新内容
    reaggregated = client.post(
        "/api/director/aggregate", json={"week_id": week_id}, headers=director_headers
    )
    assert reaggregated.status_code == 200, reaggregated.text
    assert reaggregated.json()["id"] == dept_report_id
    assert reaggregated.json()["status"] == "已汇总"

    # 数字冲突时保留每个来源的量化信息，而不是只保留其中一条
    nursing_items = [
        item for item in reaggregated.json()["items"] if "护理质控" in item["content"]
    ]
    assert len(nursing_items) == 1
    merged_content = nursing_items[0]["content"]
    assert merged_content.startswith("完成护理质控检查（")
    assert "张医生 3 次" in merged_content
    assert "100%" in merged_content
    assert "李医生未注明次数" in merged_content
    assert set(nursing_items[0]["source_user_ids"]) == {
        seed["user_ids"]["member_a"],
        seed["user_ids"]["member_b"],
    }

    # 退回与重提均留痕
    timeline = client.get(
        f"/api/audit/member_report/{member_report_id}", headers=director_headers
    )
    actions = [event["action"] for event in timeline.json()]
    assert "submit" in actions
    assert "return" in actions
    assert "resubmit" in actions


def test_only_submitted_member_report_can_be_returned(client, seed, login, submit_report):
    week_id = seed["week1_id"]
    submit_report("member_a", week_id)
    submit_report("member_b", week_id)
    director_headers = login("director")
    dept_report_id = client.post(
        "/api/director/aggregate", json={"week_id": week_id}, headers=director_headers
    ).json()["id"]

    # member_d 未提交，没有可退回的周报
    member_d_report = client.get(
        "/api/member/report", params={"week_id": week_id}, headers=login("member_d")
    ).json()
    assert member_d_report is None

    response = client.post(
        f"/api/director/dept-report/{dept_report_id}/return",
        json={"member_report_id": 999999, "reason": "不存在"},
        headers=director_headers,
    )
    assert response.status_code == 404
