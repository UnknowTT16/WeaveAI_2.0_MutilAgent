# WeaveAI 2.0 重构与升级迭代计划

> **版本**: 2.1  
> **创建日期**: 2026-02-07  
> **最后更新**: 2026-02-07  
> **目标**: 多 Agent 协作工作流升级（市场洞察 + 多轮辩论 + 评论分析）

---

## 目录

1. [项目现状分析](#一项目现状分析)
2. [目标架构设计](#二目标架构设计)
3. [技术选型](#三技术选型)
4. [分阶段迭代计划](#四分阶段迭代计划)
5. [数据模型设计](#五数据模型设计)
6. [API 设计](#六api-设计)
7. [风险与缓解措施](#七风险与缓解措施)
8. [验收标准](#八验收标准)

---

## 一、项目现状分析

### 1.1 当前架构概览

```
当前架构：单体式 Agent + 线性工作流
┌──────────────────────────────────────────────────────────────┐
│  前端 (Next.js 15 + React 19)                                │
│  └─ 三步式工作流：Insight → Validation → Action             │
└────────────────────────┬─────────────────────────────────────┘
                         │ REST API (流式/JSON)
┌────────────────────────▼─────────────────────────────────────┐
│  后端 (FastAPI)                                              │
│  ├─ AI Agent 1: 市场洞察分析师 (generate_full_report_stream) │
│  ├─ AI Agent 2: 行动规划师 (agent_action_planner)            │
│  ├─ AI Agent 3: 评论分析师 (generate_review_summary_report)  │  ← 保留
│  └─ 数据处理模块 (LSTM/KMeans/Anomaly/Sentiment) ← 删除      │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 现有技术栈

| 层级 | 技术 | 版本 |
|-----|------|------|
| 前端框架 | Next.js | 15.5.6 |
| UI 库 | React | 19.1.0 |
| 样式 | Tailwind CSS | 3.4.18 |
| 后端框架 | FastAPI | latest |
| AI/LLM | 火山引擎 Ark (doubao-seed-1-6-250615) | - |
| ~~机器学习~~ | ~~TensorFlow/Keras, scikit-learn~~ | ❌ 删除 |

### 1.3 现有 Agent 架构问题诊断

| 问题类别 | 具体表现 | 影响 |
|---------|---------|-----|
| **线性耦合** | 三个 Agent 串行执行，无并行能力 | 响应时间长，用户等待 |
| **无协作机制** | Agent 之间无通信，仅通过前端串联 | 无法交叉验证、迭代优化 |
| **无辩论机制** | Agent 输出直接作为最终结论 | 缺乏多角度验证，结论质量不稳定 |
| **Context 隔离不足** | 每个 Agent 独立 Prompt，无共享记忆 | 信息断层，重复输入 |
| **无状态持久化** | 会话结束后知识丢失 | 无法学习、无法复用 |
| **工具设计过于专化** | 分析工具高度耦合数据格式 | 扩展困难，维护成本高 |
| **缺乏编排层** | 无 Supervisor/Orchestrator | 无法动态调度、错误恢复 |
| **数据源单一** | 仅依赖通用 web_search | 缺乏社交舆情等多元数据 |

### 1.4 技术债务清单

| 文件/模块 | 问题 | 处理方式 |
|----------|------|---------|
| `backend/WAIapp_core.py` | 986 行单文件，职责过重 | 拆分重构 |
| `frontend/app/page.js` | 15+ useState，状态分散 | Context + Reducer |
| 流式处理 | 手动解析标记符，缺乏统一协议 | 统一 SSE 协议 |
| 错误处理 | Agent 失败后无重试/降级机制 | 编排层处理 |
| 数据持久化 | 分析结果仅文件存储，无法查询 | Supabase |
| ~~LSTM/KMeans 模块~~ | ~~效果不佳，不符合使用场景~~ | ❌ 删除 |

### 1.5 范围调整说明

> **重要变更**：经评估，原 Data Validation Swarm（销售预测、商品聚类、异常检测、情感分析）不符合实际使用场景，**已从迭代范围中删除**。
> 
> **保留功能**：评论分析师 Agent（`generate_review_summary_report`）作为**独立功能**保留，用户可上传评论数据获取分析报告。
> 
> 重点转向：**市场洞察多 Agent 协作 + 多轮辩论机制 + 社交舆情数据源**。

---

## 二、目标架构设计

### 2.1 Supervisor-Worker + Debate 混合模式

```
                    ┌────────────────────────────────────────────┐
                    │            WeaveAI Orchestrator            │
                    │    (Supervisor Agent - 中央调度器)          │
                    │  • 任务分解 • 路由决策 • 辩论协调 • 结果聚合 │
                    └─────────────────┬──────────────────────────┘
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            │                                                   │
            ▼                                                   ▼
┌───────────────────────────────┐             ┌───────────────────────────────┐
│   Market Intelligence Swarm   │             │   Strategy Synthesis Swarm    │
│  ┌─────────┐  ┌────────────┐  │             │  ┌──────────┐  ┌──────────┐   │
│  │ Trend   │  │ Competitor │  │             │  │Strategic │  │  Risk    │   │
│  │ Scout   │  │  Analyst   │  │             │  │ Planner  │  │Evaluator │   │
│  └────┬────┘  └─────┬──────┘  │             │  └──────────┘  └──────────┘   │
│       │             │         │             └───────────────────────────────┘
│  ┌────┴────┐  ┌─────┴──────┐  │
│  │Regulation│ │  Social    │  │  ← 新增
│  │ Checker │  │ Sentinel   │  │
│  └─────────┘  └────────────┘  │
│       │                       │
│       └───────────┬───────────┘
│                   ▼                         
│  ┌────────────────────────────┐             
│  │    DebateCoordinator       │  ← 新增：多轮辩论机制
│  │   • Round 1: 独立分析      │
│  │   • Round 2: 交叉质疑      │
│  │   • Round 3: 回应辩护      │
│  │   • Round 4: 共识形成      │
│  └────────────────────────────┘
└───────────────────────────────┘
            │
            ▼
┌───────────────────────────────┐
│   ToolRegistry (统一工具层)    │
│  ┌─────────┐  ┌────────────┐  │
│  │web_search│ │ reddit_api │  │
│  │(火山引擎)│ │  (PRAW)    │  │
│  └─────────┘  └────────────┘  │
│  ┌────────────────────────────┐│
│  │  RateLimiter (限流 5 QPS)  ││
│  └────────────────────────────┘│
└───────────────────────────────┘
            │
            ▼
┌───────────────────────────────┐
│      Shared Memory Layer      │
│  • Entity Graph (知识图谱)    │
│  • Session State (会话上下文) │
│  • Supabase (持久化)          │
└───────────────────────────────┘
```

### 2.2 Agent 角色定义

| Agent 名称 | 职责 | 工具集 | 输入 | 输出 |
|-----------|------|-------|-----|------|
| **Orchestrator** | 任务分解、路由、辩论协调、聚合、错误恢复 | `dispatch`, `aggregate`, `retry` | 用户请求 | 最终报告 |
| **TrendScout** | 市场趋势研究 | `web_search`, `reddit_api` | 市场定义 | 趋势数据 |
| **CompetitorAnalyst** | 竞品分析 | `web_search`, `reddit_api` | 品类定义 | 竞品矩阵 |
| **RegulationChecker** | 法规合规检查 | `web_search` | 目标市场 | 合规清单 |
| **SocialSentinel** | 社交舆情采集与分析 | `reddit_api`, `web_search` | 关键词 | 舆情报告 |
| **DebateCoordinator** | 多轮辩论协调 | 内部调度 | Agent 结论 | 共识报告 |
| **ReviewAnalyst** | 评论数据分析（独立功能）[保留] | `review_parser`, `sentiment_llm` | 评论数据 | 评论分析报告 |
| **StrategicPlanner** | 行动规划 | `plan_template`, `kpi_generator` | 洞察结果 | 行动计划 |
| **RiskEvaluator** | 风险评估 | `risk_matrix`, `mitigation_suggest` | 所有数据 | 风险报告 |

### 2.3 多轮辩论（Debate）机制设计

```
═══════════════════════════════════════════════════════════════════════
│  Round 1：独立分析                                                  │
═══════════════════════════════════════════════════════════════════════
   TrendScout          CompetitorAnalyst      RegulationChecker      SocialSentinel
   "市场趋势..."        "竞品分析..."          "法规要求..."          "社交舆情..."
        │                     │                     │                     │
        └─────────────────────┴─────────────────────┴─────────────────────┘
                                        │
                                        ▼
═══════════════════════════════════════════════════════════════════════
│  Round 2：交叉质疑                                                  │
═══════════════════════════════════════════════════════════════════════
   CompetitorAnalyst → TrendScout:
   "你说德国市场增长 15%，但我发现竞品 X 正在收缩，是否矛盾？"
   
   SocialSentinel → CompetitorAnalyst:
   "Reddit 上用户对竞品 Y 的评价很差，你的分析是否考虑了这点？"
   
   TrendScout → RegulationChecker:
   "新法规对消费趋势的影响你如何评估？"
                                        
                                        ▼
═══════════════════════════════════════════════════════════════════════
│  Round 3：回应与辩护                                                │
═══════════════════════════════════════════════════════════════════════
   TrendScout 回应:
   "竞品 X 收缩是因为供应链问题，整体市场仍在增长，数据来源..."
   
   CompetitorAnalyst 修正:
   "接受 SocialSentinel 的反馈，将竞品 Y 的用户口碑纳入分析..."
                                        │
                                        ▼
═══════════════════════════════════════════════════════════════════════
│  Round 4：共识形成                                                  │
═══════════════════════════════════════════════════════════════════════
   DebateCoordinator 综合输出:
   ├─ 共识结论（所有 Agent 认同的点）
   ├─ 分歧标注（仍存争议的点，供用户决策）
   ├─ 置信度评分（基于证据充分性）
   └─ 数据溯源（每个结论的来源 Agent 与工具）
```

### 2.4 市场洞察分析师拆分设计

```
原 Agent: generate_full_report_stream (单体)
                    ↓ 拆分为
┌────────────────────────────────────────────────────────────────┐
│                    MarketInsightOrchestrator                    │
│  • 接收用户档案，分解为 4 个并行子任务                          │
│  • 协调多轮辩论，处理质疑与回应                                 │
│  • 聚合子 Agent 结果，生成最终共识报告                          │
└───────────────────────────┬────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┬───────────────┐
            ▼               ▼               ▼               ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │ TrendScout  │  │ Competitor  │  │ Regulation  │  │   Social    │
    │             │  │  Analyst    │  │  Checker    │  │  Sentinel   │
    │ • 宏观趋势  │  │ • 竞品矩阵  │  │ • 法规清单  │  │ • Reddit    │
    │ • 市场规模  │  │ • 定价分析  │  │ • 关税税率  │  │ • Twitter*  │
    │ • 消费习惯  │  │ • SWOT分析  │  │ • 认证要求  │  │ • 舆情分析  │
    └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
         │                 │                 │                 │
         └─────────────────┴─────────────────┴─────────────────┘
                                   │
                                   ▼
                          DebateCoordinator
                          (多轮辩论协调)
                                   │
                                   ▼
                          Supabase Entities
                          (市场/竞品/法规/舆情实体)
```

---

## 三、技术选型

### 3.1 确定的技术栈

| 领域 | 选择 | 理由 |
|-----|------|-----|
| **Agent 框架** | **接口与协议原生实现 + 图/状态机编排内核（优先 LangGraph，保留可替换层）** | 保持自主可控，同时获得并发、重试、checkpoint、可回放等工作流能力 |
| **编排接口** | `IGraphEngine` 抽象接口 | 可替换实现（LangGraph → 自研 → 其他） |
| **记忆存储** | Supabase | 云原生，自带 Auth/Storage/Realtime |
| **API 设计** | 全新 v2 API | 新的请求/响应 schema，不兼容旧版 |
| **状态管理** | Context + Reducer | 集中管理复杂状态 |
| **可观测性** | Langsmith / Phoenix (后续) | Agent 调试与监控 |

### 3.2 技术决策记录

| 问题 | 决策 | 理由 |
|-----|------|-----|
| **LangGraph 集成深度** | 抽象接口 + 可插拔实现 | 定义 `IGraphEngine` 接口，Phase 1-2 用 LangGraph 作为唯一实现，未来可替换 |
| **Checkpoint 存储** | Phase 2 用 LangGraph 原生 Saver → Phase 3 迁移自定义 | 避免 Phase 2 开发阻塞 |
| **tool_invocations 写入** | 异步写入 + 脱敏 + 失败不阻塞 | 工具调用不阻塞主流程，敏感数据自动脱敏 |
| **前端 SSE 解析** | 先用 switch-case，按需引入 XState | 12 种事件用 switch 可控，复杂依赖再引入状态机 |

**模型兼容性备注（火山方舟 Web Search）**

- 当前项目的市场洞察链路依赖 Responses API 的工具调用能力（`web_search`），因此需要选择“联网搜索工具”支持列表中的模型。
- 兼容 `web_search` 的 model_id（以官方模型列表的“联网搜索工具”章节为准）：`doubao-seed-1-8-251228`、`doubao-seed-1-6-250615`、`deepseek-v3-2-251201`、`deepseek-v3-1-terminus`、`deepseek-v3-1-250821`、`kimi-k2-thinking-251104`、`kimi-k2-250905`。
- 推荐策略：主力优先选择 `doubao-seed-1-8-251228`；兼容保底使用 `doubao-seed-1-6-250615`（当前项目默认）；DeepSeek/Kimi 作为备选需额外关注其 RPM/TPM 配额与整体吞吐。
- 若选择不在该支持列表中的模型：需关闭 `use_websearch` 或改为“外部搜索 → 再喂给模型”的工具链，否则会出现工具不可用或调用失败。

### 3.3 编排内核工程约束

> 多 Agent 协作的难点在"工作流编排"，不是"写很多 Agent"。以下约束在 Phase 1/2 必须满足：

- **图/状态机表达**：明确 Node、Edge、State；支持 `fan-out -> fan-in` 并行收敛。
- **辩论循环支持**：支持多轮迭代（Round 1-4），可配置轮数与终止条件。
- **checkpoint + 断点续跑**：以 `session_id + run_id + node_id` 为最小单位持久化状态。
- **幂等与审计**：所有对外工具调用必须通过 ToolRegistry，记录输入/输出/错误/耗时/成本。
- **失败策略**：节点级重试（退避）、降级（skip/partial）、熔断（circuit breaker）。
- **结果契约化**：Agent/Tool/Orchestrator 的产出用可解析 schema（JSONB + Pydantic）。

### 3.4 后端新目录结构

```
backend/
├── main.py                      # FastAPI 入口（精简）
├── core/
│   ├── __init__.py
│   ├── config.py               # Pydantic Settings
│   ├── supabase.py             # Supabase 客户端
│   ├── exceptions.py           # 自定义异常
│   └── dependencies.py         # 依赖注入
├── agents/
│   ├── __init__.py
│   ├── base.py                 # BaseAgent 抽象类
│   ├── orchestrator.py         # OrchestratorAgent
│   ├── market/
│   │   ├── __init__.py
│   │   ├── insight_orchestrator.py  # 市场洞察编排器
│   │   ├── trend_scout.py           # 趋势研究员
│   │   ├── competitor.py            # 竞品分析师
│   │   ├── regulation.py            # 法规检查员
│   │   ├── social_sentinel.py       # 社交舆情员 [新增]
│   │   └── debate_coordinator.py    # 辩论协调器 [新增]
│   ├── review/
│   │   ├── __init__.py
│   │   └── review_analyst.py        # 评论分析师 [保留独立功能]
│   └── strategy/
│       ├── __init__.py
│       ├── planner.py               # 行动规划
│       └── risk_eval.py             # 风险评估
├── tools/
│   ├── __init__.py
│   ├── registry.py             # 工具注册表 + 限流器
│   ├── web_search.py           # 网络搜索（火山引擎）
│   ├── reddit_api.py           # Reddit 采集 [新增]
│   ├── social_sentiment.py     # 社交舆情聚合 [新增]
│   └── report_generator.py     # 报告生成
├── memory/
│   ├── __init__.py
│   ├── entity_store.py         # 实体图存储
│   ├── session_state.py        # 会话状态
│   └── temporal_facts.py       # 时效性事实
├── routers/
│   ├── __init__.py
│   └── v2/
│       ├── __init__.py
│       ├── sessions.py         # 会话管理
│       ├── insights.py         # 洞察分析
│       ├── actions.py          # 行动计划
│       └── reports.py          # 报告导出
├── schemas/
│   ├── __init__.py
│   └── v2/
│       ├── __init__.py
│       ├── requests.py         # 请求模型
│       ├── responses.py        # 响应模型
│       └── agents.py           # Agent 相关模型
└── utils/
    ├── __init__.py
    ├── markdown.py             # Markdown 处理
    └── pdf_export.py           # PDF 导出
```

---

## 四、分阶段迭代计划

### Phase 1: 基础架构重构 (2 周)

**目标**: 拆分单体、建立模块化基础、定义协议

| 任务 ID | 任务描述 | 优先级 | 预计工时 |
|--------|---------|-------|---------| 
| P1-1 | 后端模块化拆分（WAIapp_core.py → agents/tools/memory 模块）| 高 | 3 天 |
| P1-2 | BaseAgent 抽象类设计与实现 | 高 | 2 天 |
| P1-3 | 前端 Context + Reducer 状态管理重构（删除 validation 相关状态）| 高 | 2 天 |
| P1-4 | 配置 Supabase 项目并创建数据模型 | 高 | 1 天 |
| P1-5 | 实现 Supabase 客户端封装 | 高 | 1 天 |
| P1-6 | 定义 IGraphEngine 接口 + 事件协议 + 表结构 + 最小写入（不含成本统计/重放工具链）| 高 | 1.5 天 |

> **P1-6 范围控制说明**：
> - ✅ Phase 1 做：事件协议定义（SSE 事件类型）、表结构设计（tool_invocations）、最小写入（fire-and-forget）、IGraphEngine 接口定义
> - ❌ Phase 4 做：成本统计（tokens/费用计算）、重放工具链（根据流水重跑）、完整审计 UI

**交付物**:
- 模块化的后端代码结构
- BaseAgent 抽象类及文档
- 前端 WeaveContext 状态管理
- Supabase 项目及数据表
- IGraphEngine 接口定义
- v2 流式协议（含辩论事件）

### Phase 2: 多 Agent 协作框架 (2.5 周)

**目标**: 实现 Supervisor-Worker + Debate 协作模式

| 任务 ID | 任务描述 | 优先级 | 预计工时 |
|--------|---------|-------|---------| 
| P2-1 | Orchestrator Agent 实现（LangGraph 内核：任务分解/路由/并行/聚合/重试/checkpoint）| 高 | 3 天 |
| P2-2 | 实现 MarketInsightOrchestrator（市场洞察编排器）| 高 | 2 天 |
| P2-3 | 实现 TrendScout Agent（趋势研究员）| 高 | 1.5 天 |
| P2-4 | 实现 CompetitorAnalyst Agent（竞品分析师）| 高 | 1.5 天 |
| P2-5 | 实现 RegulationChecker Agent（法规检查员）| 高 | 1.5 天 |
| P2-6 | 实现 SocialSentinel Agent（社交舆情员）[新增] | 高 | 2 天 |
| P2-7 | 实现 DebateCoordinator（辩论协调器）[新增] | 高 | 2 天 |
| P2-8 | Agent 间通信协议设计与实现（含辩论语义）| 中 | 1 天 |

**交付物**:
- Orchestrator Agent（基于 LangGraph）
- Market Intelligence Swarm (4 个子 Agent + 辩论协调器)
- Agent 通信协议文档
- 多轮辩论流程实现
- 最小可回放执行链路

### Phase 3: 共享记忆系统 (1.5 周)

**目标**: 实现跨 Agent 的知识共享与持久化

| 任务 ID | 任务描述 | 优先级 | 预计工时 |
|--------|---------|-------|---------| 
| P3-1 | EntityStore 实体图存储实现（使用 Supabase）| 中 | 2 天 |
| P3-2 | SessionState 会话状态管理（使用 Supabase Realtime）| 中 | 2 天 |
| P3-3 | Agent Context 注入与记忆检索 | 中 | 2 天 |
| P3-4 | 自定义 SupabaseCheckpointSaver（迁移 LangGraph 原生 Saver）| 中 | 1 天 |

**交付物**:
- EntityStore 实现
- SessionState 实现
- SupabaseCheckpointSaver
- 记忆系统使用文档

### Phase 4: 工具系统重构 (1.5 周)

**目标**: 实现可扩展的工具注册与调用、接入社交数据源

| 任务 ID | 任务描述 | 优先级 | 预计工时 |
|--------|---------|-------|---------| 
| P4-1 | ToolRegistry 工具注册表 + RateLimiter 限流器 | 中 | 1.5 天 |
| P4-2 | web_search 工具封装（通过 Registry 统一调用）| 中 | 1 天 |
| P4-3 | reddit_api 工具实现（PRAW 集成）[新增] | 中 | 1.5 天 |
| P4-4 | social_sentiment 聚合工具（Reddit + 间接 Twitter）[新增] | 中 | 1 天 |
| P4-5 | tool_invocations 审计写入（异步 + 脱敏）| 中 | 1 天 |

**交付物**:
- ToolRegistry + RateLimiter 实现
- 迁移后的工具集
- Reddit API 集成
- 社交舆情采集工具
- 工具开发指南

### Phase 5: 前端体验升级 (1.5 周)

**目标**: 可视化多 Agent 协作与辩论过程

| 任务 ID | 任务描述 | 优先级 | 预计工时 |
|--------|---------|-------|---------| 
| P5-1 | v2 API 适配（api.js 更新）| 中 | 1 天 |
| P5-2 | 流式协议升级（支持 Agent 生命周期 + 辩论事件）| 中 | 1.5 天 |
| P5-3 | AgentOrchestrationView 协作可视化组件 | 低 | 1.5 天 |
| P5-4 | DebateViewer 辩论过程可视化 [新增] | 低 | 1.5 天 |
| P5-5 | AgentTimeline 执行时间线组件 | 低 | 1 天 |

**交付物**:
- 前端 v2 API 适配
- Agent 协作可视化组件
- 辩论过程可视化
- 流式协议文档

---

## 五、数据模型设计

### 5.1 Supabase 数据表

```sql
-- ============================================
-- 用户档案表
-- ============================================
CREATE TABLE profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users,
  target_market TEXT NOT NULL,
  supply_chain TEXT NOT NULL,
  seller_type TEXT NOT NULL,
  min_price INT,
  max_price INT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 会话表
-- ============================================
CREATE TABLE sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID REFERENCES profiles,
  status TEXT DEFAULT 'active', -- active, completed, archived
  created_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'
);

-- ============================================
-- Agent 执行记录表
-- ============================================
CREATE TABLE agent_executions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES sessions,
  agent_name TEXT NOT NULL,
  status TEXT DEFAULT 'pending', -- pending, running, completed, failed
  thinking TEXT,
  output TEXT,
  artifacts JSONB DEFAULT '{}',
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_message TEXT
);

-- ============================================
-- 工具调用流水表（审计 / 成本 / 回放 / 失败定位）
-- ============================================
CREATE TABLE tool_invocations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES sessions,
  execution_id UUID REFERENCES agent_executions,
  tool_name TEXT NOT NULL,
  status TEXT DEFAULT 'pending', -- pending, running, completed, failed
  input JSONB DEFAULT '{}',      -- 已脱敏
  output JSONB DEFAULT '{}',     -- 已脱敏
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_message TEXT,
  cost JSONB DEFAULT '{}',       -- tokens / 费用 / 资源用量
  idempotency_key TEXT           -- session_id + node_id + tool_name + 序号
);

-- ============================================
-- 辩论记录表 [新增]
-- ============================================
CREATE TABLE debate_rounds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES sessions,
  round_number INT NOT NULL,
  round_type TEXT NOT NULL,      -- independent, challenge, respond, consensus
  participants JSONB DEFAULT '[]',
  challenges JSONB DEFAULT '[]', -- [{from, to, content}]
  responses JSONB DEFAULT '[]',  -- [{agent, content, revised}]
  consensus JSONB DEFAULT '{}',  -- {summary, dissent_points, confidence}
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 实体表（知识图谱）
-- ============================================
CREATE TABLE entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES sessions,
  entity_type TEXT NOT NULL,     -- market, competitor, product, trend, sentiment
  name TEXT NOT NULL,
  properties JSONB DEFAULT '{}',
  source_agent TEXT,             -- 来源 Agent
  confidence FLOAT DEFAULT 1.0,  -- 置信度
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 实体关系表
-- ============================================
CREATE TABLE entity_relations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID REFERENCES entities,
  target_id UUID REFERENCES entities,
  relation_type TEXT NOT NULL,   -- competes_with, targets, influences, contradicts
  properties JSONB DEFAULT '{}',
  valid_from TIMESTAMPTZ DEFAULT NOW(),
  valid_until TIMESTAMPTZ
);

-- ============================================
-- Row Level Security
-- ============================================
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_invocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE debate_rounds ENABLE ROW LEVEL SECURITY;
ALTER TABLE entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_relations ENABLE ROW LEVEL SECURITY;

-- ============================================
-- RLS 策略（完整版）
-- ============================================

-- profiles 表策略
CREATE POLICY "Users can view own profiles"
  ON profiles FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own profiles"
  ON profiles FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own profiles"
  ON profiles FOR UPDATE
  USING (auth.uid() = user_id);

-- sessions 表策略（通过 profile_id 关联到 user_id）
CREATE POLICY "Users can view own sessions"
  ON sessions FOR SELECT
  USING (
    profile_id IN (
      SELECT id FROM profiles WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own sessions"
  ON sessions FOR INSERT
  WITH CHECK (
    profile_id IN (
      SELECT id FROM profiles WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "Users can update own sessions"
  ON sessions FOR UPDATE
  USING (
    profile_id IN (
      SELECT id FROM profiles WHERE user_id = auth.uid()
    )
  );

-- agent_executions 表策略（通过 session_id -> profile_id -> user_id 链式关联）
CREATE POLICY "Users can view own executions"
  ON agent_executions FOR SELECT
  USING (
    session_id IN (
      SELECT s.id FROM sessions s
      JOIN profiles p ON s.profile_id = p.id
      WHERE p.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own executions"
  ON agent_executions FOR INSERT
  WITH CHECK (
    session_id IN (
      SELECT s.id FROM sessions s
      JOIN profiles p ON s.profile_id = p.id
      WHERE p.user_id = auth.uid()
    )
  );

-- tool_invocations 表策略（同 agent_executions）
CREATE POLICY "Users can view own tool invocations"
  ON tool_invocations FOR SELECT
  USING (
    session_id IN (
      SELECT s.id FROM sessions s
      JOIN profiles p ON s.profile_id = p.id
      WHERE p.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own tool invocations"
  ON tool_invocations FOR INSERT
  WITH CHECK (
    session_id IN (
      SELECT s.id FROM sessions s
      JOIN profiles p ON s.profile_id = p.id
      WHERE p.user_id = auth.uid()
    )
  );

-- debate_rounds 表策略
CREATE POLICY "Users can view own debate rounds"
  ON debate_rounds FOR SELECT
  USING (
    session_id IN (
      SELECT s.id FROM sessions s
      JOIN profiles p ON s.profile_id = p.id
      WHERE p.user_id = auth.uid()
    )
  );

-- entities 表策略
CREATE POLICY "Users can view own entities"
  ON entities FOR SELECT
  USING (
    session_id IN (
      SELECT s.id FROM sessions s
      JOIN profiles p ON s.profile_id = p.id
      WHERE p.user_id = auth.uid()
    )
  );

-- entity_relations 表策略（通过 source_id -> entities -> session_id 关联）
CREATE POLICY "Users can view own entity relations"
  ON entity_relations FOR SELECT
  USING (
    source_id IN (
      SELECT e.id FROM entities e
      JOIN sessions s ON e.session_id = s.id
      JOIN profiles p ON s.profile_id = p.id
      WHERE p.user_id = auth.uid()
    )
  );

-- ============================================
-- 幂等键唯一约束
-- ============================================
ALTER TABLE tool_invocations 
ADD CONSTRAINT unique_idempotency_key UNIQUE (idempotency_key);
```

### 5.2 实体类型定义

| 实体类型 | 属性示例 | 关系类型 |
|---------|---------|---------| 
| `market` | name, region, size, growth_rate | targets, influences |
| `competitor` | name, pricing, strengths, weaknesses | competes_with |
| `product` | sku, category, price, features | belongs_to |
| `trend` | name, description, impact, timeframe | affects |
| `regulation` | name, type, requirements, deadline | applies_to |
| `sentiment` | platform, topic, polarity, volume | relates_to |

---

## 六、API 设计

### 6.1 v2 API 端点

```
基础路径: /api/v2

# 会话管理
POST   /sessions                    # 创建新会话
GET    /sessions/{id}               # 获取会话详情
GET    /sessions/{id}/agents        # 获取会话中所有 Agent 执行状态
GET    /sessions/{id}/entities      # 获取会话中识别的实体
GET    /sessions/{id}/debates       # 获取会话中辩论记录 [新增]
DELETE /sessions/{id}               # 归档会话

# 洞察分析
POST   /insights/market             # 流式市场洞察分析（含辩论）
GET    /insights/market/{id}/status # 获取分析进度

# 评论分析（独立功能，保留）
POST   /reviews/analyze             # 流式评论分析报告
GET    /reviews/{id}/status         # 获取分析进度

# 行动计划
POST   /actions/plan                # 生成行动计划
POST   /actions/evaluate-risk       # 风险评估

# 报告导出
POST   /reports/generate            # 生成 HTML 报告
POST   /reports/export-pdf          # 导出 PDF
GET    /reports/{id}                # 获取报告详情
```

### 6.2 请求/响应示例

**创建会话**

```json
// POST /api/v2/sessions
// Request
{
  "profile": {
    "target_market": "Germany",
    "supply_chain": "Consumer Electronics",
    "seller_type": "Cross-border E-commerce",
    "min_price": 50,
    "max_price": 200
  }
}

// Response
{
  "session_id": "uuid-xxx",
  "status": "active",
  "created_at": "2026-02-07T10:00:00Z"
}
```

**流式市场洞察（含辩论）**

```json
// POST /api/v2/insights/market
// Request
{
  "session_id": "uuid-xxx",
  "options": {
    "enable_websearch": true,
    "enable_social": true,
    "debate_rounds": 2,
    "parallel_agents": true
  }
}

// Response (SSE Stream)
data: {"event": "orchestrator_start", "timestamp": "..."}
data: {"event": "agent_start", "agent": "trend_scout"}
data: {"event": "agent_thinking", "agent": "trend_scout", "content": "我需要分析..."}
data: {"event": "tool_start", "tool": "web_search", "agent": "trend_scout"}
data: {"event": "tool_end", "tool": "web_search", "agent": "trend_scout", "duration": 1.2}
data: {"event": "agent_output", "agent": "trend_scout", "content": "## 市场趋势..."}
data: {"event": "agent_end", "agent": "trend_scout", "status": "completed"}
data: {"event": "debate_round_start", "round": 2, "type": "challenge"}
data: {"event": "agent_challenge", "from": "competitor_analyst", "to": "trend_scout", "content": "..."}
data: {"event": "agent_respond", "agent": "trend_scout", "content": "...", "revised": true}
data: {"event": "consensus_reached", "summary": "...", "confidence": 0.85}
data: {"event": "orchestrator_end", "final_report": "..."}
```

### 6.3 流式协议事件类型

| 事件类型 | 说明 | 载荷 |
|---------|------|-----|
| `orchestrator_start` | 编排器开始 | timestamp |
| `orchestrator_end` | 编排器结束 | final_report |
| `agent_start` | Agent 开始执行 | agent, task |
| `agent_thinking` | Agent 思考过程 | agent, content |
| `agent_output` | Agent 输出内容 | agent, content |
| `agent_end` | Agent 执行结束 | agent, status, duration |
| `agent_error` | Agent 执行错误 | agent, error, retry |
| `tool_start` | 工具开始执行 | tool, agent, input |
| `tool_end` | 工具执行结束 | tool, agent, output, duration |
| `tool_error` | 工具执行错误 | tool, agent, error, retry |
| `checkpoint` | 工作流保存断点 | node_id, state_ref |
| `retry` | 节点/工具重试 | target_type, target_id, attempt |
| `debate_round_start` | 辩论轮次开始 [新增] | round_number, type, participants |
| `agent_challenge` | Agent 提出质疑 [新增] | from_agent, to_agent, challenge_content |
| `agent_respond` | Agent 回应质疑 [新增] | agent, response_content, revised |
| `consensus_reached` | 达成共识 [新增] | consensus_summary, dissent_points, confidence |
| `memory_update` | 记忆更新 | entity_type, entity_id |
| `handoff` | Agent 交接 | from, to, context |

---

## 七、风险与缓解措施

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|-----|---------| 
| **辩论死循环** | Agent 反复质疑无法收敛 | 中 | 限制最大辩论轮数（默认 2-3 轮），设置超时 |
| **火山引擎 API 限流** | 多 Agent 并发触发限流 | 高 | ToolRegistry 内置 RateLimiter（5 QPS），排队机制 |
| **Reddit API 限制** | 免费层每分钟 60 请求 | 中 | 缓存策略 + 按需调用 + 降级到 web_search |
| **Twitter 数据获取困难** | API 付费门槛高 | 高 | 优先使用间接方式（web_search + site:twitter.com） |
| **Supervisor 瓶颈** | 中央调度器成为性能瓶颈 | 中 | 实现 `forward_message` 直通机制 |
| **Context 膨胀** | 辩论多轮导致 Token 超限 | 高 | 分层记忆 + 摘要压缩 + 只保留关键质疑 |
| **协调开销** | 多 Agent + 辩论增加延迟 | 中 | 并行执行无依赖任务，辩论轮次可配置 |
| **错误传播** | 单 Agent 失败影响全流程 | 中 | 熔断机制 + 降级策略 + 重试逻辑 |
| **复杂性增加** | 维护成本上升 | 高 | 完善文档 + 单元测试 + 可观测性工具 |

---

## 八、验收标准

### 8.1 Phase 1 验收标准

- [ ] 后端代码按新目录结构组织（无 validation 模块）
- [ ] BaseAgent 抽象类可被子类正确继承
- [ ] 前端 WeaveContext 正常管理全局状态（无 validation 相关）
- [ ] Supabase 数据表创建成功且可正常 CRUD
- [ ] IGraphEngine 接口定义完成
- [ ] SSE 事件协议文档完成（含 debate_* 事件）

### 8.2 Phase 2 验收标准

- [ ] Orchestrator 能正确分解用户请求
- [ ] 4 个市场洞察子 Agent 可并行执行
- [ ] SocialSentinel 能获取 Reddit 数据
- [ ] DebateCoordinator 能协调 2-3 轮辩论
- [ ] 辩论过程中 Agent 能提出质疑并回应
- [ ] 最终输出包含共识结论与分歧标注
- [ ] Orchestrator 支持节点级重试/降级
- [ ] Agent 执行状态正确记录到 Supabase
- [ ] 流式输出包含辩论生命周期事件
- [ ] 最终报告质量不低于原单体 Agent

### 8.3 Phase 3 验收标准

- [ ] 实体识别并存储到 Supabase
- [ ] 跨 Agent 可查询共享实体
- [ ] 会话状态正确持久化
- [ ] SupabaseCheckpointSaver 正常工作
- [ ] Supabase Realtime 订阅正常工作

### 8.4 Phase 4 验收标准

- [ ] ToolRegistry 支持动态注册工具
- [ ] RateLimiter 正确限制并发（5 QPS）
- [ ] web_search 通过 Registry 调用
- [ ] reddit_api 工具功能正常
- [ ] social_sentiment 能聚合 Reddit + 间接 Twitter
- [ ] 所有工具调用写入 tool_invocations（异步 + 脱敏）
- [ ] 工具文档完整

### 8.5 Phase 5 验收标准

- [ ] 前端正确调用 v2 API
- [ ] Agent 协作过程可视化展示
- [ ] 辩论过程可视化（质疑/回应/共识）
- [ ] 执行时间线实时更新
- [ ] 无明显性能退化

---

## 九、时间线总览

```
Week 1-2: Phase 1 - 基础架构重构
  └─ 模块拆分 + BaseAgent + Supabase + IGraphEngine + 事件协议

Week 3-4.5: Phase 2 - 多 Agent 协作
  └─ Orchestrator + Market Swarm (4 Agent) + DebateCoordinator

Week 5-6: Phase 3 - 共享记忆 + Phase 4 - 工具系统
  └─ EntityStore + SessionState + ToolRegistry + Reddit/Twitter

Week 7-8: Phase 5 - 前端升级 + 测试 + 文档
  └─ Agent 可视化 + DebateViewer + 流式协议 + 验收测试
```

---

## 十、附录
### C. 参考资源

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/) - 多 Agent 模式参考
- [Supabase Documentation](https://supabase.com/docs) - 数据库与 Realtime
- [PRAW Documentation](https://praw.readthedocs.io/) - Reddit API
- [FastAPI Streaming](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse) - 流式响应
- [React Context](https://react.dev/reference/react/useContext) - 状态管理

---

> **文档维护**: 本文档将随项目进展持续更新  
> **版本历史**:
> - v1.0 (2026-02-07): 初始版本
> - v2.0 (2026-02-07): 删除 Data Validation Swarm，新增多轮辩论机制与社交舆情数据源
> - v2.1 (2026-02-07): 保留评论分析师 Agent（独立功能）；补强 P1-6 范围控制、RLS 策略、幂等键规则、IGraphEngine 接口定义
