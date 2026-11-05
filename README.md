# 智能周报系统

科室周报自动汇总与上报系统。成员在线填报，主任一键智能汇总、编辑审定并上报，院领导按周次/科室查阅；AI 归并、校验、摘要、风险提示全部可在**无外网、无大模型 Key** 的情况下由规则引擎完整运行。

> 本项目为招聘实操测试交付物。所有演示人员、科室与周报内容均为编造数据，不含任何真实患者或医院内部数据。

## 功能一览

### 必做功能（M1–M7）

| 编号 | 功能 | 实现要点 |
|---|---|---|
| M1 | 角色与登录 | 成员 / 主任 / 院领导 / 管理员四类角色，Header Token 会话，逐接口鉴权 |
| M2 | 周报填报 | 四类条目（完成/计划/问题/协调）动态增删，保存草稿、提交锁定、退回后重填 |
| M3 | 自动汇总 | LangGraph 固定 DAG + MergerAgent，近义重复合并并标注来源人员 |
| M4 | 主任编辑 | 双击编辑、↑/↓ 调整顺序、删除、手动补充条目（来源标记“主任补充”）；已定稿/已上报后编辑锁定但保留追踪；任一环节均可退回指定成员并附理由 |
| M5 | 上报与查阅 | 定稿后上报，院领导按周次/科室筛选，只读查看 |
| M6 | 状态与留痕 | 严格状态机 + `audit_logs` + `report_versions`；成员端可看本人周报、主任端可看汇总稿的操作历史时间线（操作人/时间/动作/理由） |
| M7 | 演示数据 | 启动自动灌入 1 科室、5 成员、连续 2 周数据 + 第 3 周空白填报周 |

### AI 能力（A1–A4）

| 编号 | 能力 | 实现 |
|---|---|---|
| A1 | 智能归并 | jieba 分词 + 同义词归一 + Jaccard / 长句包含规则；数字冲突时保留每个来源的量化信息 |
| A2 | 摘要生成 | 第三人称模板摘要，≤150 字，排除空泛条目 |
| A3 | 规范校验 | 空泛词词典 + 量化检测，空泛条目从展示中剔除但仍在 A3 留痕 |
| A4 | 风险提示 | 未提交人员、协调事项超期未闭环、计划事项连续两周未推进 |
| A5 | 智能问答 | 未实现（加分项，主动取舍） |

### 加分项

| 功能 | 说明 |
|---|---|
| 跨周事项追踪 | 在归并条目右侧点击“⏱ 追踪”，条目下方直接内联展开逐周时间线：提出人、类别、原文，未出现的周次标记“未推进” |
| 管理员极简维护 | 新增/编辑用户（含重置密码）、新增科室、新增周次、修改提交截止时间；列表自动刷新，不提供删除 |
| 周次自动兜底 | 启动和每日凌晨检查是否有周次覆盖今天；存在则不操作，缺失才按当前自然周生成一个 |

**降级方案**：每个 Agent 节点内部 `try LLM → except → 规则实现`，无 Key / 断网 / 超时 / 额度耗尽均自动降级；主任页可显式切换“大模型 / 规则”，trace 徽标展示每个 Agent 使用的引擎与降级原因。

> 当前交付版本以规则引擎完整运行；LLM 通道保留了统一接口，但尚未接入真实模型 API。即使配置 Key，也会安全降级到规则引擎，不影响功能与演示。

## 技术栈

| 层 | 选型 | 版本 |
|---|---|---|
| 后端 | Python | 3.12.10（要求 3.10+） |
| Web 框架 | FastAPI | 0.162.0 |
| ASGI | uvicorn | 0.54.0 |
| ORM | SQLAlchemy | 2.1.6 |
| 数据校验 | Pydantic | 2.14.2 |
| 数据库 | SQLite | 内置，单文件 |
| AI 编排 | LangGraph | 1.2.19 |
| 中文分词 | jieba | 0.42.1 |
| 密码哈希 | bcrypt | 5.0.0 |
| 测试 | pytest + httpx | 9.2.0 / 0.28.1 |
| 前端 | 原生 HTML / CSS / JS | 无构建工具、无 CDN |

## 快速启动

环境：Windows 10/11、Python 3.10+、Chrome。

```bash
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --port 8000
```

访问 <http://localhost:8000>；接口文档 <http://localhost:8000/docs>。

- 启动时自动建表，并幂等灌入演示数据（`AUTO_SEED=0` 可关闭）。
- seed 生成第 1、2、3 周演示数据；系统启动及每日凌晨会检查是否存在覆盖今天的周次，缺失时才自动兜底生成一个，绝不修改管理员手动配置。
- 数据库文件位于 `data/weekly_report.db`，已加入 `.gitignore`。

## 演示账号

密码统一：`demo123`

| 账号 | 角色 | 说明 |
|---|---|---|
| `member_a` | 科室成员 | 张医生，第 1/2 周已提交，含护理质控近义表述 |
| `member_b` | 科室成员 | 李医生，第 1/2 周已提交，与 A 构成归并样例 |
| `member_c` | 科室成员 | 王医生，含空泛表述样例 |
| `member_d` | 科室成员 | 赵医生，第 2 周故意未提交 |
| `member_e` | 科室成员 | 陈医生，含跨周未推进的协调/计划事项 |
| `director` | 科室主任 | 王主任，汇总/编辑/退回/定稿/上报 |
| `leader` | 院领导 | 只读查阅已上报周报 |
| `admin` | 系统管理员 | 用户/科室/周次维护与截止时间调整 |

登录页提供演示账号快捷登录按钮，点击即可进入对应视图。

## 演示数据

| 周次 | 日期 | 数据 |
|---|---|---|
| 第 1 周 | 2026-10-19 ～ 2026-10-25 | 5 人全部提交；A/B 写护理质控近义表述；C 写空泛表述 |
| 第 2 周 | 2026-10-26 ～ 2026-11-01 | 4 人提交，`member_d` 未提交；A 写“抽查 3 次”，B 写“自查已完成” |
| 第 3 周 | 2026-11-02 ～ 2026-11-08 | **空白周**，用于体验从零填报 |

重点验收点：

- 第 1 周汇总：`完成护理质控检查` 与 `护理质控自查已完成` 合并为一条，来源为张医生、李医生。
- 第 2 周汇总：合并结果保留来源差异：`完成护理质控检查（张医生 3 次，李医生自查）`。
- 王医生的空泛条目不出现在归并条目中，但会在 A3 校验建议中显示。
- 第 2 周主任看板中 `member_d` 红色高亮为“未提交”，A4 风险提示同步列出。
- 第 3 周下拉框可见，成员进入后四类条目均为空白。

## 演示剧本

### 剧本一：正常链路

1. `member_a` 登录 → 选择第 1 周 → 查看已提交周报（锁定）。
2. `member_b` / `member_c` 登录 → 查看各自填报内容。
3. `director` 登录 → 选择第 1 周 → 一键汇总 → 检查护理质控已合并、来源徽章、A3/A4、trace；点击“查看操作历史”查看流转时间线。
4. 主任双击条目编辑、用 ↑/↓ 调整顺序、删除或“手动补充条目”（来源标记“主任补充”），修改摘要后定稿、上报；定稿/上报后编辑区锁定，仅保留追踪。
5. `leader` 登录 → 按第 1 周/心内科筛选 → 查看只读汇总。

### 剧本二：异常链路

1. 主任选择第 2 周 → 看板显示 `member_d` 未提交（红色），A4 风险提示列出未交人员。
2. 主任点击 `member_a` 的“退回”并填写理由 → `member_a` 重新登录后看到红色退回理由 → 修改后重新提交。
   - 退回按钮在“已汇总 / 已定稿 / 已上报”任一状态都保留；已定稿/已上报退回后，汇总稿自动回到“已退回”，需重新汇总、定稿、上报。
3. 成员直接访问主任/院领导接口 → 后端返回 403，并写入 `forbidden_access` 审计日志。
4. 将 AI 引擎切到“大模型”（当前无 Key）后汇总 → 三个 LLM Agent 自动降级到规则引擎，结果完整，trace 显示“（降级）”。

### 空白填报

`member_a` 登录后选择第 3 周，四类条目均为空白，可新增、保存草稿并提交。

### 跨周事项追踪（加分项）

`director` 登录并汇总后，在任意归并条目右侧点击“⏱ 追踪”：

- 包含“电子病历”的条目 → 条目下方展开第 1、2 周陈医生在【计划】中的原文，第 3 周标记“未推进”。
- 包含“护理质控”的条目 → 展开第 1、2 周张医生、李医生的相关原文，按周次串联展示。

时间线展示提出人、类别、原文与周次日期；后续周次没有匹配内容时显示“未推进”。再次点击“⏱ 收起”或点击其他条目的追踪按钮即可收起。

### 管理员维护

`admin` 登录后默认进入“系统管理员”页面，顶栏显示“系统管理员”角色：

- **系统用户**：新增用户（用户名/姓名/角色/科室/密码）；编辑用户信息并可重置密码
- **科室配置**：新增科室
- **周次配置**：新增周次（编号/起止日期/截止时间）；修改任意周次的提交截止时间
- 新增或修改成功后自动刷新列表；不提供删除操作

所有写操作均走 `/api/admin/*`，后端严格校验 admin 角色。

周次采用“手动配置 + 系统兜底”双轨：

- 管理员可随时新增周次、调整截止时间；
- 系统启动时及每日凌晨检查是否存在 `start_date <= 今天 <= end_date` 的周次；
- 已存在覆盖今天的周次时**不做任何修改**，不会覆盖管理员配置；
- 只有不存在时才按当前自然周（周一至周日）插入一个兜底周次。

## 目录结构

```text
smart-weekly-report/
├── app/
│   ├── main.py                 # FastAPI 入口、静态挂载、启动建表/灌数据/周次兜底
│   ├── config.py               # 数据库、会话、规则阈值、LLM 配置
│   ├── db.py                   # SQLAlchemy engine/session、SQLite 轻量迁移
│   ├── models.py               # ORM 模型
│   ├── schemas.py              # API 契约
│   ├── exceptions.py           # 业务异常
│   ├── auth.py                 # Header Token 会话、require_role
│   ├── seed.py                 # 幂等演示数据 + --reset
│   ├── routers/                # auth/member/director/leader/admin/audit/meta
│   ├── services/
│   │   ├── report_service.py   # 状态机与业务编排
│   │   ├── audit_service.py    # 留痕
│   │   ├── ai_service.py       # 调用 LangGraph
│   │   ├── admin_service.py    # 管理员用户/科室/周次维护
│   │   └── week_service.py     # 周次覆盖检查与兜底生成
│   └── agents/
│       ├── base.py             # AgentResult / BaseAgent
│       ├── merger.py           # A1 归并（同义词、相似度、数字冲突保留）
│       ├── validator.py        # A3 校验
│       ├── summarizer.py       # A2 摘要
│       ├── risk.py             # A4 风险
│       ├── vague.py            # 空泛词统一匹配
│       ├── nodes.py            # 节点内双通道降级
│       └── graph.py            # LangGraph StateGraph
├── static/                     # 原生 HTML/CSS/JS 单页应用
├── data/                       # 同义词表、空泛词表、SQLite 运行时库
├── tests/                      # pytest 测试
├── requirements.txt
├── README.md
├── DESIGN.md
└── AI_USAGE.md
```

## API 概览

| 方法 | 路径 | 角色 | 说明 |
|---|---|---|---|
| POST | `/api/auth/login` | 公开 | 登录，返回 Bearer Token |
| POST | `/api/auth/logout` | 登录态 | 退出 |
| GET | `/api/auth/me` | 登录态 | 当前用户 |
| GET | `/api/weeks` | 登录态 | 周次列表 |
| GET | `/api/departments` | 登录态 | 科室列表 |
| GET | `/api/member/report?week_id=` | member | 本人周报 |
| POST | `/api/member/report/draft` | member | 保存草稿 |
| POST | `/api/member/report/submit` | member | 提交/重提 |
| GET | `/api/member/report/versions?week_id=` | member | 历史版本 |
| GET | `/api/director/overview?week_id=` | director | 提交看板 |
| POST | `/api/director/aggregate` | director | 一键汇总（含 `engine_switch`） |
| GET | `/api/director/track-item?keyword=&dept_id=` | director | 跨周追踪关键词，返回逐周时间线 |
| GET | `/api/director/dept-report?week_id=` | director | 汇总稿详情 |
| PUT | `/api/director/dept-report/{id}/items` | director | 编辑条目 |
| PUT | `/api/director/dept-report/{id}/summary` | director | 编辑摘要 |
| POST | `/api/director/dept-report/{id}/return` | director | 退回成员 |
| POST | `/api/director/dept-report/{id}/finalize` | director | 定稿 |
| POST | `/api/director/dept-report/{id}/report` | director | 上报 |
| GET | `/api/leader/reports?week_id=&dept_id=` | leader | 已上报周报 |
| GET | `/api/admin/users` | admin | 全部用户（含所属科室） |
| POST | `/api/admin/users` | admin | 新增用户 |
| PUT | `/api/admin/users/{id}` | admin | 编辑用户 / 重置密码 |
| POST | `/api/admin/departments` | admin | 新增科室 |
| POST | `/api/admin/weeks` | admin | 新增周次 |
| PUT | `/api/admin/weeks/{id}/deadline` | admin | 修改提交截止时间 |
| GET | `/api/audit/{entity_type}/{id}` | director/leader/admin | 操作时间线 |

## 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/weekly_report.db` | 数据库连接 |
| `AUTO_SEED` | `1` | 启动时是否幂等灌入演示数据 |
| `SESSION_TTL_HOURS` | `12` | 登录会话有效期 |
| `MERGE_THRESHOLD` | `0.6` | 规则归并 Jaccard 阈值 |
| `LLM_API_KEY` | 空 | 预留，当前未接入真实 API |
| `LLM_BASE_URL` | OpenAI 兼容地址 | 预留 |
| `LLM_MODEL` | `gpt-4o-mini` | 预留 |

## 测试

```bash
python -m pytest -q
node --check static/app.js
```

当前测试覆盖：鉴权与越权审计、状态机、汇总到上报主链路、任一环节退回（已汇总/已定稿/已上报）、退回/重提/版本快照、操作历史时间线（成员自见/主任汇总稿/倒序/操作人）、A1 近义合并与数字冲突、A3 空泛校验、A4 风险、跨周追踪、LLM 降级 trace、种子数据、周次兜底与不覆盖手动配置、管理员 CRUD 与校验、静态页面。

## 数据重置

```bash
python -m app.seed --reset   # 清空全部表后重新灌入演示数据
```

演示数据固定包含第 1、2、3 周；第 3 周为空白填报周。

周次同时支持两种维护方式：

1. **管理员手动配置**：新增周次、修改截止时间（优先，系统不会覆盖）；
2. **系统定时兜底**：启动时和每日凌晨检查是否存在覆盖今天的周次，缺失才按当前自然周生成一个。

启动时只插入缺失的兜底周次，不更新、不删除任何已有周次。

## 已知限制

- 当前 LLM 通道未接入真实模型 API，交付版本以规则引擎运行。
- 规则归并依赖同义词表，面对高度口语化表述仍需维护词表。
- SQLite 适合单科室演示规模；多科室高并发需更换数据库。
- 管理员提供极简 CRUD（新增/编辑用户、新增科室、新增周次、修改截止时间），不提供删除；初始周次由 seed 维护。
- 未做移动端深度适配，仅保证 Chrome 与基础响应式可用。

## 相关文档

- [DESIGN.md](DESIGN.md) — 一页式设计说明
- [AI_USAGE.md](AI_USAGE.md) — AI 工具使用声明与验证方式
