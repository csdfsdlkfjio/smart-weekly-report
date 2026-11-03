智能周报系统 产品方案 （完整版）
河南科技大学第一附属医院 互联网医院 · 人工智能应用开发岗位实操测试
版本 v2.0 · 2026-11-03 · 架构：LangGraph 编排 + 4 Agent + 双通道降级

一、需求理解
1.1 业务本质
这不是表单系统，而是一个责任链系统。核心不是把 Word 搬到线上，而是解决四件事：

痛点	产品对策
主任每周 1–2 小时机械复制粘贴	4 个 Agent 协作完成归并、校验、摘要、风险提示，把"整理"变成"审定"
格式不统一、内容空泛	结构化字段 + ValidatorAgent 规范校验，提交即约束
谁交了、谁改了、哪版是终稿全无记录	五态状态机 + 全链路操作留痕 + 版本快照
周报散落群聊邮箱、无法回溯	按周次/科室结构化沉淀，可检索、可跨周对比
1.2 角色与责任边界（产品第一原则）
医院信息化的特点是"角色、权限、责任边界极其清晰"。权限是本产品的一等公民，不是登录后的菜单过滤：

角色	能做什么	绝不能做什么
科室成员	填/存草稿/提交本人周报；查看退回理由；看本人历史版本	看他人周报、改已提交内容、进主任/院领导页面
科室主任	看本科室提交情况、一键汇总、编辑定稿、退回指定成员、上报	改成员原始提交（只能在汇总稿上编辑）、跨科室操作
院领导	查看已上报周报，按周次/科室筛选、检索	看到未上报稿子、编辑任何内容
系统管理员	维护科室/人员/周次/截止时间	参与业务审批（不做"万能账号"）
责任边界的关键设计：成员提交后锁定；主任的编辑发生在"汇总稿"这一独立实体上，不覆盖成员原文；退回时保留上一版，形成可追溯链。谁写的、谁改的、谁退回的、谁上报的，每一步落库。

1.3 状态机（严格按题目，不简化）
text
                    ┌──────────── 退回（附理由，保留历史版本）────────────┐
                    ▼                                                    │
草稿 ──提交──▶ 已提交 ──汇总──▶ 已汇总 ──定稿──▶ 已定稿 ──上报──▶ 已上报
  ▲                │                │                │
  └──保存草稿──     └──退回──────────┴──退回──────────┘
成员侧周报：草稿 / 已提交 / 已退回（回到可编辑，重提后回"已提交"）

科室周报（汇总稿）：已汇总 / 已定稿 / 已上报 / 已退回

每次状态变更写 audit_logs，含操作人、时间、变更前后状态、变更内容摘要

被退回的成员周报保留 report_versions 快照，成员可看"上一版 vs 本版"差异

二、系统结构
2.1 总体架构（单机可跑，评委 5 分钟启动）
text
┌──────────────────────────────────────────────────────────────┐
│  Chrome 浏览器（前端：原生 HTML/JS，单页多视图）                │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP (REST)
┌──────────────────────────────▼───────────────────────────────┐
│  后端服务（Python FastAPI，单进程）                             │
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────────────┐ │
│  │ 认证/鉴权 │ │ 业务服务  │ │   LangGraph 编排层            │ │
│  │ (Session)│ │(填报/定稿)│ │   StateGraph（固定 DAG）      │ │
│  └──────────┘ └──────────┘ │   ┌──────┐ ┌──────────┐       │ │
│                            │   │merger│→│validator │       │ │
│  ┌──────────────────────┐  │   └──┬───┘ └────┬─────┘       │ │
│  │ 审计/日志（留痕）      │  │      ▼          ▼             │ │
│  └──────────────────────┘  │  ┌───────────┐ ┌────────┐      │ │
│                            │  │summarizer │ │  risk  │      │ │
│                            │  └─────┬─────┘ └───┬────┘      │ │
│                            │        └─────┬─────┘           │ │
│                            │              ▼                 │ │
│                            │   4 个 Agent 各自双通道          │ │
│                            │   LLM实现 ⇄ 规则实现（降级）     │ │
│                            └──────────────────────────────┘ │
└──────────────────────────────┬───────────────────────────────┘
                               │
                 ┌─────────────▼─────────────┐
                 │  SQLite（单文件，随程序）  │
                 │  启动自动建表 + 灌演示数据 │
                 └───────────────────────────┘
选型理由：SQLite 单文件零外部依赖；后端单进程启动；LangGraph 仅作编排层本地运行，不依赖外网；前端用浏览器原生能力。评委在干净 Win10/11 上 pip install -r requirements.txt + 一条启动命令，5 分钟内必然看到演示数据。

2.2 数据模型（核心表）
表	关键字段	说明
users	id, name, role, dept_id, password_hash	四类角色
departments	id, name	科室
weeks	id, week_no, start_date, end_date, deadline	周次与截止时间
member_reports	id, user_id, week_id, status, version, submitted_at	成员周报主表
member_report_items	id, report_id, category(done/plan/issue/coord), content, order	四类条目
dept_reports	id, dept_id, week_id, status, summary, finalized_at, reported_at	科室汇总稿
dept_report_items	id, dept_report_id, category, content, source_user_ids, order, edited_by	汇总条目，source_user_ids 标注来源
audit_logs	id, entity_type, entity_id, action, operator_id, before, after, created_at	全链路留痕
report_versions	id, report_type, report_id, version, snapshot_json, created_at	退回/重提版本快照
agent_traces	id, dept_report_id, agent_name, engine(llm/rule), status, detail, created_at	Agent 执行与降级留痕，前端可展示
2.3 主链路时序（正常剧本）
成员A登录 → 按周次填四类条目 → 存草稿 → 提交（锁定，写 audit_logs）

成员B、C 提交含重复内容的事项（如都写了护理质控）

主任登录 → 看提交看板（已交/未交）→ 点"一键汇总"

触发 LangGraph：merger → validator → summarizer，risk 并行 → 产出初稿+摘要+校验+风险

主任逐条编辑/删/补/排序 → 可退回某成员并附理由 → 定稿 → 上报

院领导登录 → 按周次+科室筛选 → 查看已上报周报（只读）

2.4 异常链路（自测剧本二必须全过）
异常	产品处理
成员D未提交	主任端看板标红"未提交"，汇总前提示"存在N人未提交"；RiskAgent 自动列入风险提示
主任退回A	A登录见退回理由+上一版对比；修改后重提，状态回"已提交"，历史版本可查
A直接访问主任/院领导页面URL	后端每接口做角色+归属校验，返回403并记越权日志；前端隐藏菜单是第二道防线
断网/关大模型	汇总页"AI引擎"开关（大模型/规则）显式切换；每个 Agent 内 LLM 失败自动降级到规则实现，规则通道永远可用，输出结构完整、来源标注照常
三、AI 方案：LangGraph 多 Agent 架构
3.1 架构定位（先讲清取舍）
LangGraph 只做编排层，不做 AI 能力层。 它负责定义 DAG、传递状态；LLM 调用与降级由各 Agent 内部完成。LangGraph 官方明确"不抽象提示词与架构"，正好满足本方案"AI 逻辑透明可解释"的要求。

为什么用固定 DAG 而非自由协作：周报汇总本身是确定性流水线，不需要 Agent 自主决定下一步。固定拓扑保证两次点汇总结果一致（可复现），也避免多轮 ReAct 带来的延迟与不确定性。这是取舍，不是妥协。

3.2 4 个 Agent 与编排图
text
                         ┌─────────┐
                         │  START  │
                         └────┬────┘
                    ┌─────────┴──────────┐
                    ▼                    ▼
             ┌───────────┐        ┌───────────┐
             │  merger   │        │   risk    │
             │ (A1归并)  │        │ (A4风险)  │
             └─────┬─────┘        └─────┬─────┘
                   ▼                    │
             ┌───────────┐              │
             │ validator │              │
             │ (A3校验)  │              │
             └─────┬─────┘              │
                   ▼                    │
             ┌───────────┐              │
             │summarizer │              │
             │ (A2摘要)  │              │
             └─────┬─────┘              │
                   └─────────┬──────────┘
                             ▼
                         ┌───────┐
                         │  END  │
                         └───────┘
#	Agent	能力	职责	输入 → 输出	是否调 LLM
1	MergerAgent	A1	四类条目语义去重合并，标注来源	原始条目+人员 → 合并条目+source_users	是（可降级）
2	ValidatorAgent	A3	识别空泛表述、缺量化条目，给建议	合并结果 → 问题列表+建议	是（规则已很强）
3	SummarizerAgent	A2	生成 ≤150 字公文语体概述	合并+校验 → 摘要文本	是（可降级）
4	RiskAgent	A4	未提交名单、连续两周未推进、超期协调	原始数据+跨周数据 → 风险列表	否（纯规则）
主 DAG：merger → validator → summarizer；risk 与 merger 并行（只读原始数据，不依赖归并结果）。固定 DAG，无条件边、无循环。

3.3 State 定义
python
from typing import TypedDict, List, Annotated
import operator

class WeekReportState(TypedDict):
    dept_id: str
    week_id: str
    engine_switch: str                          # "llm" | "rule"
    raw_items: List[dict]                       # 输入
    merged: List[dict]                          # MergerAgent 输出
    checked: List[dict]                         # ValidatorAgent 输出
    summary: str                                # SummarizerAgent 输出
    risks: List[dict]                           # RiskAgent 输出
    engine_trace: Annotated[List, operator.add] # 降级记录，追加合并
engine_trace 用 Annotated + operator.add 实现追加，每个节点往 trace 里追加"哪个 Agent 用了哪个引擎"，前端据此展示"本次由规则引擎生成"。

3.4 双通道降级机制（重点考察项）
降级在 Agent 内部完成，LangGraph 无感知。 每个 Agent 对外一个契约，对内两套实现：

python
def merger_node(state: WeekReportState) -> dict:
    agent = MergerAgent()
    try:
        if state["engine_switch"] == "llm":
            result = agent.run_llm(state["raw_items"], timeout=8)
            trace = [("merger", "llm", "ok")]
        else:
            raise RuleFallback("switch=rule")
    except (TimeoutError, NetworkError, QuotaExceeded, InvalidOutput, RuleFallback) as e:
        result = agent.run_rule(state["raw_items"])
        trace = [("merger", "rule", str(e))]
    return {"merged": result, "engine_trace": trace}
三层保障：

Agent 粒度降级：单个 Agent 的 LLM 失败只影响它自己，其他 Agent 照常走，图照常走完

全局开关：主任页顶部"AI引擎：大模型 / 规则"显式切换，演示时现场切，满足"演示时能够切换"

无 key 即默认规则：启动时无密钥直接以规则引擎运行，功能完整可演示，不报错

必须向评委讲清：LangGraph 的 checkpointer 不是降级方案（它只管中断恢复）；LangGraph 核心库本地运行不依赖外网，断网只影响 LLM 调用，不影响编排。

3.5 各 Agent 的双通道实现
MergerAgent（A1）

LLM：结构化提示词，输入 {category: [{user, content}]}，输出 JSON [{category, merged_content, source_users}]；强约束"不新增事实、不丢来源、不改变原意"

规则：分词 → 去停用词 → 同义词归一（检查/自查/核查）→ 字符+词级相似度（Jaccard/编辑距离）→ 阈值合并 → source_users 取并集

取舍：规则可解释可复现零成本，是兜底底线；LLM 对"表述差异大但语义相同"更鲁棒

ValidatorAgent（A3）

LLM：逐条判定并给建议

规则：空泛词词典（"继续推进相关工作""日常工作正常开展"）+ 量化检测（有无数字/百分比/次数）→ 命中即给建议

特点：规则实现质量已很高，LLM 是增强而非必需，天然抗降级

SummarizerAgent（A2）

LLM：提示词明确"以科室名义、客观陈述、不用第一人称、概括重点与需协调事项"，输出 ≤150 字

规则：模板化——"本周科室完成 N 项工作，重点包括{前3条}；下周计划推进{...}；需协调{...}。"

摘要与归并结果同屏可编辑，主任可改

RiskAgent（A4）

纯规则，不调 LLM：未提交人员名单、连续两周未推进事项（跨周比对条目）、超期未闭环协调事项

低成本高价值，不增加降级负担

3.6 可选：A5 智能问答
独立交互入口，不并入主图，单独建 QAAgent + 子图（检索历史周报 → 回答"某项工作最近四周进展"）。规则通道用关键词检索兜底。加分项，时间够再做。

四、功能与验收对照
编号	功能	验收要点	本方案落点
M1	角色与登录	三类账号，仅见本角色功能与数据	后端逐接口鉴权，Session+角色，前端菜单二次隐藏
M2	周报填报	四类字段、多条、存草稿/提交、提交后锁定	条目子表+状态机，提交写 audit 并锁
M3	自动汇总	按四类归并，重复合并，不字符串拼接	MergerAgent 双通道归并，source_user_ids 标注来源
M4	主任编辑	逐条改/删/补/排序、退回附理由	汇总稿独立实体可编辑，退回写理由+版本快照
M5	上报与查阅	一键上报，院领导按周次科室筛选	状态流转+院领导只读检索页
M6	状态与留痕	状态明确，每步操作人/时间/变更可追溯	audit_logs+report_versions+agent_traces，时间线展示
M7	演示数据	1 科室 5 成员连续 2 周	启动自动灌库，含重复内容与未提交者，直接可演示
验收自检要点：

M3 必须验证"完成护理质控检查"与"护理质控自查已完成"被合并为一条，且来源人员为两人

M6 必须验证退回→重提全链路每一步在时间线可查

M7 必须验证评委启动后无需任何手工造数即可看到完整主链路数据

五、加分项规划（按优先级）
加分项	优先级	说明
提交情况看板	高	提交率、条目数趋势、退回次数，主任端首页
催报提醒	中	对未提交成员生成提醒清单（站内提示，不对接真实微信）
历史周报全文检索与跨周对比	中	支撑 A5 与 RiskAgent 的"连续两周未推进"判断
单元测试	中	至少覆盖 MergerAgent 规则版、状态机流转、权限拦截
容器化部署	低	Dockerfile，时间够再做
移动端适配	低	基础响应式，保证 Chrome 移动视图可用
部署到公网	低	视剩余时间，非必需
明确不做（题目已列，避免挤占时间）：不对接医院真实系统、不做多级组织架构/复杂审批流/电子签章、不做高并发集群容灾、不追求产品级精美界面。

六、已知缺陷与后续改进
已知缺陷（如实写进设计说明，体现清醒认知）：

规则通道归并依赖同义词表，面对高度口语化表述召回有限，需持续维护词表

SQLite 适合单科室演示规模，多科室高并发需换数据库

LangGraph 引入一层编排抽象，代码量略增；若 State 契约不严谨，Agent 间数据传递出错会放大故障，对策是强类型 + 单测

A5 问答在规则通道下仅关键词检索，语义理解弱于 LLM 通道

未做移动端深度适配（仅保证 Chrome 可用，基础响应式支持）

后续改进：

归并阈值与同义词表做成管理员可配，用真实数据迭代

提交看板增加趋势图与催报（加分项）

跨周全文检索与"某事项最近四周进展"视图（对应 A5）

容器化部署 + 接口文档 + 单元测试补全（加分项，时间允许）

LangGraph checkpointer 落 SQLite，支持汇总中断后恢复（当前为纯内存运行）

七、交付物与演示安排
交付物	内容要点
源代码	完整可运行，requirements.txt 锁版本（含 langgraph），目录结构在 README 说明
README	环境要求（Python 版本）、启动步骤（3 条命令内）、演示账号表、目录结构、AI 密钥配置与费用归属、降级切换说明、LangGraph 已验证版本
演示数据	启动自动灌入：1 科室、5 成员（含 1 人故意未交）、连续 2 周、含重复事项与空泛表述
设计说明	≤1 页 A4：需求理解、结构图、4 Agent 与 LangGraph 编排、降级方案、已知缺陷与改进
AI 使用声明	逐处列出使用了大模型/编程助手的位置、生成占比、本人修改与验证方式
演示录屏	可选，≤3 分钟，走正常+异常两段剧本，重点拍到降级开关切换与 engine_trace 展示
演示账号（建议）：member_a / member_b / member_c / member_d(未交) / director / leader / admin，密码统一 demo123，README 明示。

启动自测清单（提交前必做）：

□ 干净环境/虚拟机按 README 5 分钟内启动见数据
□ 剧本一五步全通
□ 剧本二四步全通（未交提示、退回重提、越权 403、断网降级出可用结果）
□ 降级开关现场可切，engine_trace 在前端可见
□ LangGraph 版本锁定，requirements 安装成功
□ AI 使用声明如实、电话能解释每处实现
八、评审维度自检
维度	权重	本方案对策
业务理解与需求落地	15	角色责任边界表、状态机严格实现、退回留版本
功能完整度	25	M1–M7 全覆盖，异常路径四条逐一处理
AI 能力应用	20	LangGraph 编排 + 4 Agent 单一职责；双通道+Agent 粒度降级+显式开关；归并真做语义合并非拼接；摘要公文语体；agent_traces 可展示
工程质量	15	分层（认证/业务/编排/Agent/审计）、State 强类型、统一异常处理、日志、错误提示
数据安全与权限	10	后端逐接口鉴权、越权拦截与日志、演示数据全编造（红线）
说明文档与可维护性	15	README 可独立跑、AI 声明如实、录屏讲清 LangGraph 取舍（编排不降级、固定 DAG 理由）
九、电话沟通预案（评委可能追问的点）
追问	回答要点
为什么用 LangGraph？	编排层标准化，状态传递清晰；但只用固定 DAG，业务不需要复杂编排，是取舍不是妥协
LangGraph 负责降级吗？	不负责。降级在各 Agent 内部完成，编排框架稳定性不影响降级能力
断网时 LangGraph 能跑吗？	能。核心库本地运行不依赖外网，断网只影响 LLM 调用，Agent 自动切规则
为什么不用条件边/循环？	周报汇总是确定性流水线，固定 DAG 保证可复现，避免多轮 ReAct 的延迟与不确定性
4 个 Agent 会不会过度拆分？	每个 Agent 单一职责、契约清晰、可独立单测；Merger/Validator/Summarizer 对应 A1/A3/A2 三项能力，Risk 纯规则零降级负担，数量与业务能力一一对应
两个 LLM 都失败怎么办？	各自独立降级到规则实现，图照常走完，输出结构完整，engine_trace 标记降级原因
5 分钟能启动吗？	pip install -r requirements.txt（锁版本）+ 一条启动命令，SQLite 自动建表灌数据，无需手工造数