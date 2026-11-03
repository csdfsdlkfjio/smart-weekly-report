智能周报系统 技术方案
河南科技大学第一附属医院 互联网医院 · 人工智能应用开发岗位实操测试
版本 v2.0 · 2026-11-03 · 配套产品方案 v2.0（LangGraph 编排 + 4 Agent + 双通道降级）

一、技术选型与理由
1.1 选型总表
层	选型	版本	理由
后端语言	Python	3.10+	生态成熟、评委环境易装、AI 库丰富
Web 框架	FastAPI	锁定版本	自带 OpenAPI、类型校验、启动快
数据校验	Pydantic v2	锁定版本	Agent 契约强类型，LLM 输出 schema 校验
数据库	SQLite	内置	单文件零依赖，随程序启动，5 分钟可跑
ORM	SQLAlchemy 2.x	锁定版本	成熟、支持类型注解、SQLite 兼容好
Agent 编排	LangGraph	锁定主版本	题目要求 agent 架构，本地运行不依赖外网
大模型	OpenAI 兼容接口（可配 base_url）	—	兼容多供应商，key 可配，无 key 走规则
分词	jieba	锁定版本	规则版归并基础
密码	bcrypt	锁定版本	演示账号密码哈希
测试	pytest	锁定版本	Agent 契约与降级路径单测
部署	uvicorn 单进程	锁定版本	一条命令启动
前端	原生 HTML/JS + 轻量 CSS	—	无构建链，降低启动失败风险
核心取舍：全链路本地可跑，唯一外部依赖是"可选的大模型调用"。去掉该依赖，系统仍能完整演示——这是对"5 分钟启动 + 降级可用"两条红线的技术承诺。

1.2 明确不引入
不引入前端框架/打包器：增加构建步骤 = 增加启动失败点

不引入 Redis/消息队列/容器编排：题目明确不做高并发集群

不引入重型 agent 框架扩展组件：LangGraph 仅用 StateGraph 核心能力，不用 checkpointer（纯内存运行）

不引入独立数据库服务：SQLite 单文件足够

1.3 requirements.txt 示意（锁版本）
text
fastapi==0.11x.x
uvicorn==0.3x.x
sqlalchemy==2.x.x
pydantic==2.x.x
langgraph==0.2.x
jieba==0.42.1
bcrypt==4.x.x
python-multipart==0.0.x
httpx==0.2x.x
pytest==8.x.x
README 写明"已在 Python 3.10 + 上述版本验证"，并给出离线 wheel 安装说明。

二、总体架构
2.1 分层视图
text
┌──────────────────────────────────────────────────────────────┐
│  表现层：Chrome 浏览器（原生 HTML/JS）                          │
│  登录 / 成员填报 / 主任看板与汇总编辑 / 院领导查阅 / 审计时间线    │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP REST (JSON)
┌──────────────────────────────▼───────────────────────────────┐
│  接口层：FastAPI Routers                                       │
│  auth / member / director / leader / admin                    │
│  职责：参数校验、身份注入、角色与归属鉴权、错误映射               │
├──────────────────────────────────────────────────────────────┤
│  服务层：services/                                             │
│  report_service（状态机+业务编排）                              │
│  audit_service（留痕）                                         │
│  ai_service（调 LangGraph 图，落 agent_traces）                 │
├──────────────────────────────────────────────────────────────┤
│  AI 层：agents/                                                │
│  graph.py（StateGraph 构建，固定 DAG）                          │
│  nodes.py（4 个 node，节点内双通道降级）                         │
│  merger / validator / summarizer / risk（Agent 实现）          │
│  llm_client.py（LLM 封装：超时、重试、schema 校验）              │
├──────────────────────────────────────────────────────────────┤
│  数据层：models.py（ORM）+ db.py（engine/session）              │
│  SQLite 单文件 + seed.py（启动灌演示数据，幂等）                 │
└──────────────────────────────────────────────────────────────┘
分层硬约束：

降级逻辑只在 agents/ 内，不依赖 LangGraph，不依赖接口层

状态机只在 report_service，接口层不直接改状态

留痕统一走 audit_service，任何业务写操作后调用

2.2 关键数据流（一键汇总）
text
主任点击"一键汇总"
  → POST /api/director/aggregate {dept_id, week_id, engine_switch}
  → director router：鉴权（role=director 且 dept 匹配）
  → report_service.aggregate()：
       校验状态（本周成员已提交集合非空）
       组装 raw_items（四类条目+人员映射）
       调用 ai_service.run_aggregate(raw_items, engine_switch)
  → ai_service：
       构建 WeekReportState → graph.invoke(state)
       graph 内 merger→validator→summarizer，risk 并行
       每个 node 内部 try LLM → except → 规则，写 engine_trace
       返回 merged/checked/summary/risks/engine_trace
  → report_service：
       创建 dept_reports（状态=已汇总）+ dept_report_items（含 source_user_ids）
       写 agent_traces、audit_logs
  → 返回汇总稿 ID，前端跳转编辑页
三、数据模型
3.1 表结构
表	关键字段	约束/索引	说明
users	id, username, name, role, dept_id, password_hash	username 唯一	role ∈ {member, director, leader, admin}
departments	id, name	name 唯一	科室
weeks	id, week_no, start_date, end_date, deadline	week_no 唯一	周次与截止时间
member_reports	id, user_id, week_id, status, version, submitted_at, locked	(user_id, week_id) 唯一	成员周报主表
member_report_items	id, report_id, category, content, sort_order	report_id 索引	category ∈ {done, plan, issue, coord}
dept_reports	id, dept_id, week_id, status, summary, finalized_at, reported_at	(dept_id, week_id) 唯一	科室汇总稿
dept_report_items	id, dept_report_id, category, content, source_user_ids, sort_order, edited_by	dept_report_id 索引	source_user_ids 存 JSON 数组
audit_logs	id, entity_type, entity_id, action, operator_id, before_json, after_json, created_at	(entity_type, entity_id) 索引	全链路留痕
report_versions	id, report_type, report_id, version, snapshot_json, created_at	(report_type, report_id) 索引	退回/重提快照
agent_traces	id, dept_report_id, agent_name, engine, status, detail, created_at	dept_report_id 索引	Agent 执行与降级留痕
3.2 状态枚举
python
class MemberReportStatus(str, Enum):
    DRAFT = "草稿"
    SUBMITTED = "已提交"
    RETURNED = "已退回"      # 退回后回到成员侧可编辑

class DeptReportStatus(str, Enum):
    AGGREGATED = "已汇总"
    FINALIZED = "已定稿"
    REPORTED = "已上报"
    RETURNED = "已退回"
3.3 状态机实现（集中在 service 层）
python
ALLOWED_TRANSITIONS = {
    ("member", "草稿"): {"已提交"},
    ("member", "已提交"): {"已退回"},
    ("member", "已退回"): {"已提交"},
    ("dept", "已汇总"): {"已定稿", "已退回"},
    ("dept", "已定稿"): {"已上报", "已退回"},
    ("dept", "已退回"): {"已汇总"},
}

def transit(entity_type, current, target, operator, entity):
    if target not in ALLOWED_TRANSITIONS.get((entity_type, current), set()):
        raise StateTransitionError(f"{current} 不能流转到 {target}")
    # 写 audit_logs：before/after 状态、操作人、时间
非法流转抛 StateTransitionError → 接口层映射 400，前端友好提示。

四、AI 层设计（核心）
4.1 Agent 清单：4 个
#	Agent	能力	输入 → 输出	LLM 实现	规则实现
1	MergerAgent	A1 归并	四类条目+人员 → 合并条目+source_users	结构化提示词，JSON 强约束	分词+同义词+相似度合并
2	ValidatorAgent	A3 校验	合并结果 → 问题列表+建议	逐条判定提示词	空泛词词典+量化检测
3	SummarizerAgent	A2 摘要	合并+校验 → ≤150字摘要	公文语体提示词	模板填充
4	RiskAgent	A4 风险	原始数据+历史周报 → 风险清单	不调 LLM	未交/未推进/超期检测
4.2 Agent 契约（统一接口，强类型）
python
class AgentResult(BaseModel):
    data: Any
    engine: Literal["llm", "rule"]
    status: Literal["ok", "degraded"]
    detail: str = ""

class BaseAgent(ABC):
    name: str
    @abstractmethod
    def run_llm(self, *args, timeout: int = 8) -> Any: ...
    @abstractmethod
    def run_rule(self, *args) -> Any: ...
每个 Agent 对外只暴露 run_llm / run_rule，返回经 pydantic 校验的结构。LLM 返回不合法 → InvalidJSON 异常 → 触发降级。

4.3 LangGraph 编排
python
class WeekReportState(TypedDict):
    dept_id: str
    week_id: str
    engine_switch: str                        # "llm" | "rule"
    raw_items: list[dict]
    merged: list[dict]
    checked: list[dict]
    summary: str
    risks: list[dict]
    engine_trace: Annotated[list, operator.add]

def build_graph():
    g = StateGraph(WeekReportState)
    g.add_node("merger", merger_node)
    g.add_node("validator", validator_node)
    g.add_node("summarizer", summarizer_node)
    g.add_node("risk", risk_node)

    g.add_edge(START, "merger")
    g.add_edge(START, "risk")          # risk 与 merger 并行
    g.add_edge("merger", "validator")
    g.add_edge("validator", "summarizer")
    g.add_edge("summarizer", END)
    g.add_edge("risk", END)

    return g.compile()   # 无 checkpointer，纯内存，零外部依赖
关键决策：

固定 DAG，无条件边、无循环——流程确定，结果可复现

不用 checkpointer——避免持久化依赖；审计由 audit_logs / agent_traces 负责，职责不重叠

risk 并行——只读原始数据，不依赖 merger 输出，缩短耗时

4.4 节点内降级（硬约束）
python
def merger_node(state: WeekReportState) -> dict:
    agent = MergerAgent()
    if state.get("engine_switch") == "llm" and agent.llm_healthy():
        try:
            result = agent.run_llm(state["raw_items"], timeout=8)
            return {"merged": result,
                    "engine_trace": [("merger", "llm", "ok")]}
        except (TimeoutError, NetworkError, QuotaExceeded, InvalidJSON) as e:
            result = agent.run_rule(state["raw_items"])
            return {"merged": result,
                    "engine_trace": [("merger", "rule", str(e))]}
    result = agent.run_rule(state["raw_items"])
    return {"merged": result,
            "engine_trace": [("merger", "rule", "switch=rule")]}
三层降级保障：

agent 粒度：单 agent LLM 失败只降它自己，图照常走完

全局开关：主任页显式切换，演示现场可切

无 key 默认规则：启动即规则引擎运行，不报错、功能完整

engine_trace 落 agent_traces 表，前端展示"哪个 agent 用了哪个引擎、降级原因"。

4.5 LLM 客户端封装
python
class LLMClient:
    def __init__(self, api_key, base_url, model, timeout=8, max_retries=1):
        ...
    def call_json(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        # 1. 构造请求（OpenAI 兼容 /chat/completions，response_format=json）
        # 2. httpx 超时 8s，重试 1 次
        # 3. 解析 JSON → schema 校验，不合法抛 InvalidJSON
        # 4. 网络错误抛 NetworkError，额度错误抛 QuotaExceeded
密钥通过环境变量 LLM_API_KEY 注入；LLM_BASE_URL、LLM_MODEL 可配

超时/重试统一；失败抛具体异常类型，供节点捕获降级

未配置 key 时 llm_healthy() 返回 False，直接走规则

4.6 规则实现要点
MergerAgent 规则版：

jieba 分词 → 去停用词

同义词归一（可配词表：检查/自查/核查、完成/已完成/开展）

相似度 = α·Jaccard(词集) + (1-α)·归一化编辑距离，α 可配

超阈值合并；source_user_ids 取并集；保留信息量最大表述为主条目

阈值与词表放 config.py，便于调优

ValidatorAgent 规则版：空泛词词典（"继续推进相关工作""日常工作正常开展"）+ 正则量化检测（数字/百分比/次数），命中即生成具体建议。

SummarizerAgent 规则版：模板 "本周科室完成{N}项工作，重点包括{前3条要点}；下周计划推进{...}；需协调{...}。" 从归并结果抽取填充。

RiskAgent 规则版：

未提交：weeks 当前周内该科室无 member_reports.submitted 的成员

连续两周未推进：跨周比对 member_report_items 中同类事项关键词，连续两周未出现视为停滞

超期未闭环：coord 类事项标记后跨周未在 done 中出现

4.7 提示词模板（存放与版本管理）
提示词集中放 agents/prompts/，按 merger_v1.txt、summarizer_v1.txt 命名，便于迭代与回溯

每个提示词固定包含：角色设定、输入 JSON 结构、输出 JSON schema、硬约束（不新增事实/不丢来源/不用第一人称）、示例一条

提示词变更记入设计说明，电话沟通可讲清取舍

五、接口设计
5.1 接口清单
方法	路径	角色	说明
POST	/api/auth/login	公开	登录，返回 session
POST	/api/auth/logout	登录态	登出
GET	/api/member/report?week_id=	member	查看本人周报（含退回理由、历史版本）
POST	/api/member/report/draft	member	存草稿
POST	/api/member/report/submit	member	提交（锁定）
GET	/api/director/overview?week_id=	director	提交看板（已交/未交）
POST	/api/director/aggregate	director	一键汇总（含 engine_switch）
PUT	/api/director/dept-report/{id}/items	director	编辑汇总条目（增删改排序）
PUT	/api/director/dept-report/{id}/summary	director	编辑摘要
POST	/api/director/dept-report/{id}/return	director	退回指定成员（附理由）
POST	/api/director/dept-report/{id}/finalize	director	定稿
POST	/api/director/dept-report/{id}/report	director	上报
GET	/api/leader/reports?week_id=&dept_id=	leader	查阅已上报周报（只读）
GET	/api/audit/{entity_type}/{id}	director/leader	操作时间线
GET	/api/admin/traces/{dept_report_id}	director/admin	Agent 执行与降级 trace
5.2 鉴权实现
python
def require_role(*roles):
    def dep(current_user=Depends(get_current_user)):
        if current_user.role not in roles:
            audit_log(action="forbidden_access",
                      operator_id=current_user.id, ...)
            raise HTTPException(403, "无权限访问")
        return current_user
    return dep
每个业务接口声明角色

数据归属校验在 service 层：member 只能操作 user_id == current_user.id 的 report；director 只能操作 dept_id == current_user.dept_id 的汇总稿；leader 只读 status == 已上报

越权访问 → 403 + audit_logs(action=forbidden_access)，满足剧本二第 3 条

5.3 统一错误处理
业务异常（StateTransitionError、PermissionError）→ 400/403 + 友好中文提示

LLM 异常在 agent 内消化为降级，不冒泡到接口

未捕获异常 → 500 + 日志（含 trace_id），前端提示"系统繁忙"

六、前端设计
6.1 页面结构（单页多视图，原生 HTML/JS）
视图	角色	关键元素
登录页	公开	用户名/密码
成员填报	member	周次选择、四类条目增删、存草稿/提交、退回理由与版本对比
主任看板	director	已交/未交列表、未交标红、一键汇总、AI 引擎开关
汇总编辑	director	归并条目（含来源人员标签）、逐条编辑/删/补/排序、摘要编辑、校验建议、风险清单、退回入口、定稿/上报
院领导查阅	leader	周次+科室筛选、只读全文
审计时间线	director/leader	操作记录时间轴
Agent Trace	director/admin	每个 agent 的引擎、状态、降级原因
6.2 降级可视化
汇总编辑页顶部：AI 引擎：[大模型 | 规则] 开关 + 结果区 trace 徽标（如"归并：规则（LLM超时）"）。评委现场切换即可看到差异，满足"演示时能够切换"。

6.3 前端安全
菜单按角色隐藏（第二道防线）

所有数据请求带 session；后端鉴权为准，前端隐藏不作为安全依赖

七、审计与留痕
事件	表	内容
状态变更	audit_logs	操作人、时间、before/after 状态、变更摘要
编辑汇总条目	audit_logs	条目 ID、改前/改后内容、edited_by
退回	audit_logs + report_versions	退回理由、被退回成员、快照
重提	audit_logs + report_versions	新版本快照，旧版保留
越权	audit_logs	action=forbidden_access，操作人与目标
Agent 执行	agent_traces	agent 名、引擎、状态、降级原因
留痕只记操作与状态，不全文落日志；正文在业务表与版本快照表中。

八、目录结构
text
weekly-report/
├── app/
│   ├── main.py                  # FastAPI 入口 + 静态文件挂载
│   ├── config.py                # 环境变量、LLM 配置、规则阈值与词表路径
│   ├── db.py                    # engine/session
│   ├── models.py                # ORM 模型
│   ├── schemas.py               # pydantic 契约（含 AgentResult）
│   ├── exceptions.py            # 业务异常定义
│   ├── auth.py                  # 登录、session、require_role
│   ├── routers/
│   │   ├── auth.py
│   │   ├── member.py
│   │   ├── director.py
│   │   ├── leader.py
│   │   └── admin.py
│   ├── services/
│   │   ├── report_service.py    # 状态机 + 业务编排
│   │   ├── audit_service.py     # 留痕
│   │   └── ai_service.py        # 调 graph，落 agent_traces
│   ├── agents/
│   │   ├── base.py              # BaseAgent / AgentResult
│   │   ├── graph.py             # StateGraph 构建
│   │   ├── nodes.py             # 4 个 node + 降级
│   │   ├── merger.py
│   │   ├── validator.py
│   │   ├── summarizer.py
│   │   ├── risk.py
│   │   ├── llm_client.py
│   │   └── prompts/
│   │       ├── merger_v1.txt
│   │       ├── validator_v1.txt
│   │       └── summarizer_v1.txt
│   └── seed.py                  # 建表 + 演示数据（幂等）
├── static/                      # 前端页面与 JS
├── data/
│   ├── synonyms.json            # 同义词表
│   └── vague_words.json         # 空泛词词典
├── tests/
│   ├── test_agents.py
│   ├── test_state_machine.py
│   └── test_auth.py
├── requirements.txt
├── README.md
├── DESIGN.md
└── AI_USAGE.md
九、启动与演示
9.1 启动步骤（README 首屏，≤3 条命令）
bash
pip install -r requirements.txt
python -m app.seed          # 建表 + 灌演示数据（幂等，可重复执行）
uvicorn app.main:app --port 8000
浏览器打开 http://localhost:8000。

9.2 演示账号
账号	角色	说明
member_a / b / c	成员	已交，含重复事项
member_d	成员	故意未交，演示剧本二第 1 条
director	主任	汇总/编辑/退回/上报
leader	院领导	查阅
admin	管理员	维护
密码统一	demo123	README 明示
9.3 演示数据设计（M7）
1 个科室、5 名成员、连续 2 周

第 1 周：5 人全交；第 2 周：4 人交、member_d 未交

刻意埋入：A 与 B 都写"护理质控"近义表述（验证 A1 归并）；C 写空泛表述（验证 A3 校验）；某事项连续两周未推进（验证 A4 风险）；某协调事项超期未闭环

seed.py 幂等：已存在则不重复插入，保证评委可反复启动

9.4 降级演示路径
主任汇总页 → 切换"AI 引擎：规则" → 重新汇总 → 结果区 trace 徽标显示"规则"；切回"大模型"（有 key 时）→ 显示"大模型"。断网/无 key 时自动规则，无需人工干预。

十、测试策略
测试文件	覆盖	关键断言
test_agents.py	4 agent 双通道	规则版归并合并近义表述且来源正确；模拟 LLM 超时/非法 JSON/额度耗尽 → 降级到规则且结构完整；engine_trace 记录降级原因
test_state_machine.py	状态流转	合法流转通过；非法流转抛异常；退回保留版本快照；重提后旧版可查
test_auth.py	权限	成员访问主任/院领导接口返回 403；越权写审计；数据归属校验（操作他人 report 被拒）
聚焦题目两条剧本的关键路径，不堆覆盖率。

十一、风险与对策
风险	对策
LangGraph 依赖导致安装失败	requirements 锁版本；纯内存图无 checkpointer；README 写已验证版本；附离线 wheel 说明
评委环境无 Python/装依赖慢	README 首行写版本要求；依赖精简；seed.py 幂等可重复
LLM 密钥不可用	默认规则引擎，启动不报错；README 说明无 key 演示方式
规则归并质量不足	同义词表+阈值可配；演示数据刻意含近义表述，规则版可命中
Agent 间 State 契约出错	pydantic 强类型 + 单测每个 node 输入输出
越权访问	后端逐接口鉴权 + 归属校验 + 越权审计，前端隐藏仅第二道防线
十二、交付与自测清单
交付物	技术要点
源代码	目录结构如上，requirements 锁版本
README	3 条命令启动、演示账号、目录说明、LLM 配置与费用归属、降级切换说明、LangGraph 版本
演示数据	seed.py 自动灌入，幂等
DESIGN.md	≤1 页 A4：需求理解、结构图、4 Agent + LangGraph 编排、降级方案、已知缺陷
AI_USAGE.md	逐处声明 AI 工具使用位置、占比、修改与验证
录屏（可选）	≤3 分钟，正常+异常两段，拍到降级开关与 trace
提交前自测清单：

□ 干净环境按 README 5 分钟内启动见数据
□ 剧本一五步全通
□ 剧本二四步全通（未交提示、退回重提、越权 403、断网降级可用）
□ 降级开关现场可切，agent_traces 前端可见
□ LangGraph 版本锁定，pip install 成功
□ seed.py 重复执行不报错
□ 单测全绿
□ AI 使用声明如实，电话能解释每处实现
