# 智能周报系统 · 设计说明

> 按 A4 单页排版编写。演示数据均为编造，不含真实患者信息。

## 1. 需求理解

医院周报的难点不是“把 Word 搬到线上”，而是**责任链、权限边界与可追溯性**：

- 成员按周填写四类内容（完成/计划/问题/协调），提交后锁定，只能由主任退回后重填。
- 主任查看提交看板、一键汇总、在**独立汇总稿**上编辑、退回成员、定稿并上报；不修改成员原文。
- 院领导只读查看已上报周报，可按周次/科室筛选。
- 每次状态变更记录操作人、时间与变更摘要；退回/重提保留历史版本。

状态机：`草稿 → 已提交 → 已汇总 → 已定稿 → 已上报`；任一编辑环节可退回，退回后回到成员侧重新提交。

## 2. 系统结构

```text
Chrome（原生 HTML/CSS/JS 单页）
        │ HTTP REST (Bearer Token)
FastAPI ── 接口层（auth/member/director/leader）
        ├── 服务层：report_service（状态机/归属校验）、audit_service、ai_service、admin_service
        ├── AI 层：LangGraph 固定 DAG + merger/validator/summarizer/risk（节点内降级）
        └── 数据层：SQLAlchemy + SQLite（users/departments/weeks/member_reports/
                    dept_reports/audit_logs/report_versions/sessions）
```

硬约束：降级只在 Agent 内；状态机只在 `report_service`；留痕统一走 `audit_service`；接口层不直接改状态。

## 3. 数据与状态

- `member_reports`：四类条目 JSON（`done_items/plan_items/issue_items/coord_items`）+ 状态 + 版本号 + 锁定标记。
- `dept_reports`：汇总条目 JSON（含 `source_user_ids/source_names`）+ 摘要 + `meta_json`（A3 校验、A4 风险、engine_trace）。
- `report_versions`：成员每次提交生成快照，退回不覆盖旧版。
- `audit_logs`：状态变更、编辑、退回、上报、越权访问全部留痕。

流转示例：成员提交后 `locked=True`；主任退回时成员状态转“已退回”、解除锁定并附理由；成员重提后版本 +1，旧版仍可查。

## 4. AI 方案

```text
START ──▶ merger ──▶ validator ──▶ summarizer ──▶ END
   └────▶ risk ─────────────────────────────────▶ END
```

| Agent | 能力 | 规则实现 | LLM |
|---|---|---|---|
| Merger | A1 归并 | jieba + 同义词 + Jaccard / 长句包含；数字冲突时按来源保留明细 | 预留 |
| Validator | A3 校验 | 空泛词词典 + 量化检测 | 预留 |
| Summarizer | A2 摘要 | 第三人称模板，≤150 字 | 预留 |
| Risk | A4 风险 | 未提交、协调超期、计划连续未推进 | 不调用 |

- 固定 DAG、无条件边、无循环、无 checkpointer，保证结果可复现且无外部依赖。
- 每个节点内部 `try LLM → except → run_rule`，单 Agent 失败不影响整图；`engine_trace` 记入 `meta_json` 并在前端展示。
- 当前交付版本以规则引擎运行；无 Key、断网、超时均可完整演示。前端提供“大模型/规则”显式开关。
- Merger 先剔除空泛条目，再把被剔除项交给 Validator，保证展示干净且 A3 有留痕。
- 相似条目合并时保留来源；若数字缺失或冲突，输出如“完成护理质控检查（张医生 3 次，李医生自查）”，避免丢失信息。

## 5. 关键取舍

- **规则优先**：规则通道是底线，LLM 是增强，符合医院内网无法直连外网的现实。
- **JSON 存条目**：MVP 阶段减少关联表与查询复杂度；来源/排序/编辑人仍完整保存。
- **SQLite 单文件**：零外部依赖，评委 5 分钟启动；多科室高并发需迁移。
- **管理员极简 CRUD**：新增/编辑用户、新增科室、新增周次、调整截止时间；不做删除，初始周次由 seed 维护，避免与真实排班表脱节。
- **无构建前端**：原生 HTML/JS，避免构建链带来的启动失败点。

## 6. 已知缺陷与改进

- 规则归并依赖同义词表，高度口语化表述召回有限，需用真实数据迭代词表与阈值。
- 当前 LLM 通道尚未接入真实 API；下一步补 `LLMClient`、JSON schema 校验、超时/重试与真实双通道对比。
- SQLite 并发能力有限；多科室部署需换 PostgreSQL 并加索引/连接池。
- A5 智能问答、提交率图表、催报、全文检索、容器化未实现（主动取舍）。
- 汇总中断恢复未使用 checkpointer；当前审计与 `meta_json` 已满足演示链路，可后续补持久化恢复。
