# WeaveAI 2.0

WeaveAI 2.0 是一个面向市场洞察场景的多 Agent 协作系统，核心能力是：

- Supervisor-Worker 编排（并行采集 + 辩论 + 综合）
- SSE 实时流式可观测（过程可见，不是黑盒一次性输出）
- 证据链与轻量记忆快照（便于追溯与复盘）
- 报告 HTML 与路演 ZIP 一键导出（可交付）

---

## 1. 核心能力

- 多 Agent 采集：趋势、竞品、法规、社媒四条并行链路。
- 多轮辩论：支持 `0/1/2` 轮（跳过辩论 / 同行评审 / 同行+红队）。
- 稳定性策略：重试、降级（`skip/partial/fail`）、护栏、缓存。
- 演示保护模式：流中断时自动轮询 `status` 回补页面状态。
- 报告增强：支持 Vega-Lite 图表，渲染失败自动回退文本。

---

## 2. 项目结构

```text
WeaveAI_2.0/
├── backend/
│   ├── main.py                         # FastAPI 入口
│   ├── core/                           # 配置、Ark 客户端、LangGraph 引擎
│   ├── agents/                         # Worker / Debate / Synthesizer
│   ├── routers/v2/market_insight.py    # v2 业务路由
│   ├── schemas/v2/                     # 请求/响应/SSE 事件协议
│   ├── database/                       # pg 客户端、event sink、migrations
│   ├── tools/                          # ToolRegistry/Guardrail/Cache/Metrics
│   ├── utils/                          # 报告导出、图表增强、路演包
│   ├── scripts/                        # 回放与彩排脚本
│   ├── p2_smoke.py                     # Phase 2 离线冒烟
│   └── requirements.txt
├── frontend/
│   ├── app/page.js                     # 主工作台（首页/历史/偏好）
│   ├── hooks/useStreamV2.js            # SSE + 自动恢复
│   ├── contexts/WorkflowContext.js     # 全局状态管理
│   ├── reducers/workflowReducer.js     # 事件驱动状态更新
│   ├── app/components/                 # 表单、侧边栏、图表等组件
│   └── package.json
├── docker-compose.yml                  # 前后端容器编排（不含数据库）
├── ITERATION_PLAN.md
├── PHASE1_ACCEPTANCE.md ~ PHASE5_ACCEPTANCE.md
└── README.md
```

---

## 3. 技术栈

- 前端：Next.js 15 + React 19 + Tailwind + Vega-Lite。
- 后端：FastAPI + LangGraph + 火山引擎 Ark Responses API。
- 存储：Postgres（可选，启用后可用历史会话/状态回补/导出链路）。

---

## 4. 快速开始（先跑通）

### 4.1 启动后端

运行位置：`PowerShell`，项目根目录

```powershell
cd .\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 建议设置 Ark Key（未配置时可访问健康检查，但无法调用模型）
# $env:ARK_API_KEY="你的ArkKey"

.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

### 4.2 启动前端

运行位置：`PowerShell`，项目根目录（新开终端）

```powershell
cd .\frontend
npm install
Set-Content -Path .env.local -Value "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000"
npm run dev
```

### 4.3 健康检查

运行位置：`PowerShell`，项目根目录（新开终端）

```powershell
C:\Windows\System32\curl.exe http://127.0.0.1:8000/health
C:\Windows\System32\curl.exe http://127.0.0.1:8000/api/v2/market-insight/health
```

---

## 5. 启用数据库（推荐）

如果你需要完整能力（历史会话、状态恢复、图表增强导出、路演包），请配置 Postgres。

`backend/.env` 最小示例：

```env
user=postgres
password=postgres
host=127.0.0.1
port=5432
dbname=postgres
sslmode=disable
connect_timeout=8

ARK_API_KEY=your_ark_api_key
```

若你使用本地 Supabase 容器（容器名 `supabase-db`），可按顺序执行迁移：

运行位置：`PowerShell`，项目根目录

```powershell
docker exec -i supabase-db psql -U supabase_admin -d postgres < backend/database/migrations/001_initial_schema.sql
docker exec -i supabase-db psql -U supabase_admin -d postgres < backend/database/migrations/002_align_v2_schema.sql
docker exec -i supabase-db psql -U supabase_admin -d postgres < backend/database/migrations/003_update_views_and_functions.sql
docker exec -i supabase-db psql -U supabase_admin -d postgres < backend/database/migrations/004_phase3_evidence_memory.sql
docker exec -i supabase-db psql -U supabase_admin -d postgres < backend/database/migrations/005_phase4_tool_metrics.sql
```

---

## 6. API 快速参考

基础前缀：`/api/v2/market-insight`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | v2 健康检查 |
| `POST` | `/stream` | SSE 流式分析（推荐） |
| `POST` | `/generate` | 同步分析（一次性返回） |
| `GET` | `/status/{session_id}` | 会话状态/指标/图表/事件 |
| `GET` | `/sessions` | 历史会话分页查询 |
| `GET` | `/report/{session_id}.html` | HTML 报告预览/下载 |
| `GET` | `/export/{session_id}.zip` | 路演资产包导出 |

全局健康：

- `GET /`
- `GET /health`

---

## 7. 请求示例（stream）

```json
{
  "profile": {
    "target_market": "Germany",
    "supply_chain": "Consumer Electronics",
    "seller_type": "brand",
    "min_price": 30,
    "max_price": 90
  },
  "debate_rounds": 2,
  "enable_followup": true,
  "enable_websearch": false,
  "retry_max_attempts": 2,
  "retry_backoff_ms": 300,
  "degrade_mode": "partial"
}
```

关键参数：

- `debate_rounds`: `0~2`
- `degrade_mode`: `skip | partial | fail`
- `enable_websearch`: 是否启用联网搜索

---

## 8. SSE 关键事件

- 编排：`orchestrator_start` / `orchestrator_end` / `error`
- Agent：`agent_start` / `agent_thinking` / `agent_chunk` / `agent_end` / `agent_error`
- 工具：`tool_start` / `tool_end` / `tool_error` / `guardrail_triggered`
- 辩论：`debate_round_start` / `debate_round_end` / `agent_challenge_end` / `agent_respond_end` / `agent_followup_end`
- 稳定性：`retry` / `adaptive_concurrency`

---

## 9. 前端功能说明

- 首页：任务模板、评委模式、联网开关、快速启动。
- 执行进度：简版/专业版切换，Agent 思考与报告弹窗查看。
- 分析结果：关键建议、结论提炼、图表展示、报告预览、ZIP 导出。
- 历史会话：按状态筛选、分页加载、恢复会话。
- 偏好设置：默认场景、重试参数、降级策略、展示模式。

---

## 10. 脚本与验收

### 10.1 Phase 2 离线冒烟

运行位置：`PowerShell`，`backend` 目录

```powershell
python .\p2_smoke.py
```

### 10.2 Phase 3 样本回放

运行位置：`PowerShell`，`backend` 目录

```powershell
python .\scripts\replay_phase3.py --samples-dir .\scripts\samples\phase3 --api-base http://127.0.0.1:8000 --out ..\artifacts\phase3\replay_results.jsonl
```

### 10.3 Phase 5 三轮彩排

运行位置：`PowerShell`，`backend` 目录

```powershell
python .\scripts\rehearse_phase5.py --api-base http://127.0.0.1:8000 --rounds 3 --out ..\artifacts\phase5\rehearsal_results.jsonl --issues ..\artifacts\phase5\rehearsal_issues.md
```

---

## 11. Docker 运行

`docker-compose.yml` 当前只编排前后端，不包含数据库服务。

运行位置：`PowerShell`，项目根目录

```powershell
docker compose up --build
```

默认端口：

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`

---

## 12. 环境变量

### backend

| 变量 | 说明 |
| --- | --- |
| `ARK_API_KEY` | Ark API Key（模型调用必需） |
| `ARK_BASE_URL` | Ark 基础地址（可选） |
| `DEFAULT_MODEL` | 默认模型（可选） |
| `DEFAULT_DEBATE_ROUNDS` | 默认辩论轮数 |
| `TOOL_GUARDRAIL_MAX_ESTIMATED_COST_USD` | 工具护栏：成本阈值 |
| `TOOL_GUARDRAIL_MAX_ERROR_RATE` | 工具护栏：错误率阈值 |
| `TOOL_CACHE_TTL_SECONDS` | 工具缓存 TTL |
| `TOOL_CACHE_MAX_SIZE` | 工具缓存容量 |
| `user/password/host/port/dbname` | Postgres 直连配置（启用状态与历史能力时需要） |

### frontend

| 变量 | 说明 |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | 后端地址，如 `http://127.0.0.1:8000` |

---

## 13. 常见问题

- 启动后前端报网络错误：先检查 `frontend/.env.local` 的 `NEXT_PUBLIC_API_BASE_URL`。
- SSE 中途断开：前端会自动进入恢复模式，可查看状态提示条。
- `status` 返回 `unknown/not_found`：检查后端数据库连接与 `session_id` 是否正确。
- 导出失败：先确认该会话已生成 `synthesized_report`，再调用 `export`。

---

## 14. 文档导航

- 总体规划：`ITERATION_PLAN.md`
- 分阶段验收：`PHASE1_ACCEPTANCE.md`、`PHASE2_ACCEPTANCE.md`、`PHASE3_ACCEPTANCE.md`、`PHASE4_ACCEPTANCE.md`、`PHASE5_ACCEPTANCE.md`
- 路演资产：`PHASE5_DEMO_SCRIPT.md`、`PHASE5_FAQ.md`、`PHASE5_COMPETITOR_ONEPAGER.md`、`PHASE5_RISK_RESPONSE.md`

---

## 15. 许可证

MIT
