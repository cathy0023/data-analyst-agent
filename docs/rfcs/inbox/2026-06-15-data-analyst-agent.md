---
title: 数据分析 Agent（嵌入式 SDK/API 原型）
created: 2026-06-15
source: brainstorm
status: inbox
---

# 数据分析 Agent（嵌入式 SDK/API 原型）

## 背景

- **来源**：用户主动发起 brainstorm（`/rfc-brainstorm`），主题是对应工作目录名 `data-analyst-agent` 的推测方向 — 数据分析 Agent。
- **现状**：工作目录为空，无任何既有代码、依赖或 manifest，属于全新项目立项阶段。
- **痛点**：作为技术原型验证项目，动机是验证「LLM + tool use + NL2SQL」这套技术路线在嵌入式 SDK 形态下的可行性，识别硬伤点（幻觉率、延迟、成本、边界场景），为后续是否产品化提供决策依据。

## 目标（用户视角）

- 提供一个可被宿主应用 `pip install` 并 `import` 调用的 SDK，让开发者能在自己的 Python 应用里嵌入对话式数据分析能力。
- 终端用户（宿主应用的使用者）用自然语言提问，SDK 自动完成 NL → SQL → 查询 → 结论/结构化数据的完整链路。
- 验证分层架构（Agent / Tool / Executor）在 NL2SQL 场景下的可调试性、可测试性与可扩展性。
- 在 demo 数据集 + 典型问题集上达到约定的准确率门槛（具体目标见「待解决问题」）。
- 暴露并记录整套技术路线的硬伤点，输出可量化指标。

## 范围

### 在范围内（In Scope）

- Python SDK 包，对外暴露核心类（如 `DataAnalyst`）和 `ask()` 方法。
- 三层分层架构落地：Agent 层（LLM 决策）/ Tool 层（`list_tables` / `get_schema` / `execute_sql`）/ Executor 层（DB 连接 + 安全沙箱）。
- 单一数据源适配器实现（PostgreSQL，作为 prototype 默认；MySQL 视「待解决问题」结果再定）。
- 基于 Claude（默认）或 OpenAI 的 tool use 协议。
- 可观测的最小日志：每轮工具调用、SQL、耗时、token。
- 一个 demo 数据集 + 20-30 个典型问题的测试集，用于验收。

### 不在范围内（Non-Goals）

- **不做产品化**：账号、权限、多租户、计费、SSO 等一律不纳入原型。假设单租户、互信环境。
- **不做高级统计建模**：预测、聚类、时序预测、机器学习训练等重 ML 工作不在范围内；SDK 只负责取数 + 轻量汇总。
- **不做多数据源抽象**：prototype 阶段不实现「Backend 抽象层 + 多 driver 注册」的完整设计；虽然架构上预留 Backend 接口，但只落地一种实现。
- **前端图表渲染**：当前为「待定」。若 Q6 调研后确认需要，SDK 只返回结构化数据，渲染交宿主应用；若不需要，SDK 仅返回文本/表格数据。详见「待解决问题」。

## 约束

- **技术栈**：Python（与 pandas / sqlalchemy / agent 生态对齐）。
- **数据源**：PostgreSQL 或 MySQL 二选一（与 Non-Goal「不做多源抽象」存在表述张力，详见「待解决问题 #1」）。
- **LLM 协议**：基于原生 tool use（Claude / OpenAI），具体选型见「待解决问题 #3」。
- **时间盒**：未在 brainstorm 中明确锁定。建议 prototype 阶段控制在 3-4 周（与方案 C 的「中」工作量对齐），需用户后续确认。
- **目录约束**：当前工作目录 `/Users/chenyan/Documents/cy-test/data-analyst-agent` 为空，可自由初始化项目结构。

## 已讨论的方案

### 方案 A：极简自撸（已讨论，未选）

- **核心思路**：直接用 Claude/OpenAI 原生 tool use，不引入 LangChain / LlamaIndex。单文件核心类 `DataAnalyst`，注入 schema，提供 `ask()` 方法。Prototype 阶段硬选 PostgreSQL。
- **优点**：依赖极少、调试链路短、每一步可观测、代码量最小。
- **缺点**：重试、错误修复、schema 注入等基础能力需要自己撸；架构扁平，后续扩展（多源、多模型）需要重构。
- **工作量**：小（1-2 周）。
- **驳回理由**：用户更看重架构清晰度和可扩展性，方案 A 的扁平结构与项目「为后续产品化打基础」的隐性目标冲突。

### 方案 B：基于 LlamaIndex（已讨论，未选）

- **核心思路**：用 LlamaIndex 的 `NLSQLTableQueryEngine` 或 LangChain 的 `SQLDatabaseChain`，包一层 SDK；通过 SQLAlchemy 隐式抽象数据源。
- **优点**：起步最快、社区组件丰富、天然支持多数据源。
- **缺点**：依赖重、抽象层 opaque 导致 NL2SQL 错误时难以定位；与 Non-Goal「不做多源抽象」直接冲突；框架版本迭代快，API 易碎。
- **工作量**：小（1-2 周）。
- **驳回理由**：与已确认的 Non-Goal 冲突（隐式多源抽象），且框架黑盒对「识别技术路线硬伤」这一核心目标不利 — 原型阶段需要看清每一步。

### 方案 C：分层架构（已选 ✓）

- **核心思路**：明确的分层设计 —
  - **Agent 层**：LLM 决策循环（决定调哪个 tool、何时返回最终答案），基于 Claude/GPT 原生 tool use。
  - **Tool 层**：`list_tables` / `get_schema` / `execute_sql` 等原子工具，每个 tool 有清晰的 schema 与错误返回契约。
  - **Executor 层**：DB 连接池 + 安全沙箱（只读、超时、行数上限）。
  - 预留 `Backend` 抽象接口，prototype 阶段只落地 PostgreSQL 实现。
- **优点**：架构清晰、每一层可独立测试、为后续扩展（多源、多模型、缓存、权限）打基础；调试时能精确定位是 Agent 决策错、Tool schema 错、还是 SQL 执行错。
- **缺点**：对 prototype 阶段而言颗粒度偏重，前期需要花时间定义层间接口；工作量比方案 A/B 大。
- **工作量**：中（3-4 周）。

## 成功标准

- **端到端链路跑通**：从「自然语言提问 → SQL → 查询 → 结论/结构化数据」整条链路在 demo 数据集上稳定运行，不崩、不卡死。验收方式：跑通 demo 数据集的全部 20-30 个典型问题，无人工干预。
- **准确率达标**：在测试集上 NL2SQL + 结论生成的整体正确率 ≥ 80%（具体评测方法见「待解决问题 #2」）。验收方式：测试集自动跑分，输出 accuracy 报告。
- **SDK 可集成**：可以 `pip install` 装上，`import` 之后 ≤ 10 行代码完成初始化和提问，能在独立的 demo 宿主应用里调起来。验收方式：提供 `examples/` 目录下的可运行 demo 脚本，第三方 clone 后按 README 步骤能在 5 分钟内跑通。

## 待解决问题

> 以下问题留给 rfc-driven-dev Stage 1 的 research agent 并行调研。每条都对应方案 C 设计中需要落地的决策点。

- **#1 数据源范围准确定义**：Q3（Non-Goal「不做多源抽象」）与 Q4（约束「pg 或 mysql」）存在表述张力。需要澄清：
  - 是 prototype 阶段硬选一种（推荐 PG）？
  - 还是 SDK 内部需要一个**轻量**的 Backend 接口（只抽象 connect/execute，不抽象 SQL 方言），同时落地 PG + MySQL 两个实现？
  - 调研输出：给出 prototype 阶段的明确建议 + trade-off 分析。

- **#2 准确率评测方法**：用什么测准确率？
  - 候选：Spider benchmark / BIRD benchmark / 自建领域测试集 / 人工抽检。
  - 目标门槛定多少（80%? 90%?）？以「执行结果正确」还是「SQL 字符串完全一致」为准？
  - 调研输出：评测方法选型 + 推荐门槛 + 评测脚本设计要点。

- **#3 模型与框架选型**：
  - LLM：Claude Sonnet 4.6 / GPT 系列 / 开源模型（Qwen / DeepSeek）各自的 NL2SQL 能力对比、成本、延迟。
  - 是否引入轻量框架（如 `pydantic-ai`、`instructor`）做 tool schema 管理，还是纯手撸 tool use 协议？
  - 调研输出：模型推荐 + 框架推荐（含「不用框架」的可行性评估）。

- **#4 Schema 注入策略**：
  - 怎么把库 schema 喂给 LLM：全量 schema 一次性注入 / 按需 `get_schema(table)` 工具调用 / RAG 检索相关表 / schema linking？
  - 大库（几十张表、上千字段）场景下哪种策略 token 成本和准确率最优？
  - 字段语义注释（业务术语 → 字段映射）怎么维护？要不要在 schema 之外维护一份「业务字典」？
  - 调研输出：schema 注入策略推荐 + token 成本估算。

- **#5（衍生）前端图表渲染是否在范围内**：Q3 用户未勾选「不做前端图表渲染」作为 Non-Goal，需要澄清 SDK 是否要返回图表 spec（如 ECharts option / Vega-Lite spec），还是只返回纯数据。如返回 spec，需调研 spec 格式选型。

- **#6（衍生）时间盒与里程碑**：brainstorm 阶段未锁定时间盒，需要在 RFC 阶段确认 3-4 周是否可接受，并拆分里程碑（如 W1 架构骨架、W2 NL2SQL 主链路、W3 准确率调优 + 测试集、W4 SDK 打包 + demo）。
