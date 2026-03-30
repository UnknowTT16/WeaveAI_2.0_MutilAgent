# WeaveAI 2.0 混合架构重构迭代计划：Go Gateway + Python Agent Service

> 基于对现有代码库的逐文件分析，制定的精确到函数/文件级别的迁移方案。

---

## 一、架构总览

```
Frontend (Next.js :3000)
    │
    ▼  HTTP / SSE
Go Gateway (:8080)
    ├── API 路由、CORS、请求 ID、日志、限流
    ├── SSE 流式中继（消费 Python → 重发前端）
    ├── PostgreSQL 直连 (pgx/v5 连接池)
    ├── Event Sink（goroutine + buffered channel）
    ├── 报告生成 / 导出（goldmark + archive/zip）
    └── 状态查询 / 会话管理 / 指标计算
    │
    ▼  内部 HTTP / SSE（不对外暴露）
Python Agent Service (:8000)
    ├── LangGraph 状态机编排 (graph_engine.py, 84KB)
    ├── 6 个 Agent (trend_scout, competitor_analyst, regulation_checker, social_sentinel, synthesizer, debate_challenger)
    ├── 火山引擎 Ark API 调用 (ark_client.py)
    ├── 工具注册 / 缓存 / 护栏 (tools/)
    └── 证据链 / 记忆快照 (core/evidence_pack.py, memory/)
```

### 通信方式：内部 HTTP/SSE（非 gRPC）

**理由**：Python 端 `graph_engine.py` 已原生产出 SSE 流，Go 只需消费并中继，无需改动 Python 核心逻辑。

---

## 二、现有代码库关键文件清单

| 文件路径 | 行数 | 职责 | 迁移动作 |
|---------|------|------|---------|
| `backend/api/main.py` | 83 | FastAPI 入口、CORS | → Go `cmd/gateway/main.go` |
| `backend/api/routers/v2/__init__.py` | 17 | 路由前缀 `/api/v2` | → Go chi 路由 |
| `backend/api/routers/v2/market_insight.py` | 983 | 8 个 HTTP handler | → Go `internal/handler/` |
| `backend/infrastructure/db/pg_client.py` | 556 | 18 个 DB 方法 (psycopg2) | → Go `internal/db/` (pgx) |
| `backend/infrastructure/db/event_sink.py` | 724 | SSE 事件聚合 + 后台 DB 写入线程 | → Go `internal/sse/eventsink.go` |
| `backend/schemas/v2/events.py` | 248 | 30+ SSE 事件类型枚举 + SSEEvent 模型 | → Go `internal/model/event.go` |
| `backend/schemas/v2/requests.py` | 87 | UserProfile + MarketInsightRequest | → Go `internal/model/request.go` |
| `backend/schemas/v2/responses.py` | 107 | 7 个响应模型 | → Go `internal/model/response.go` |
| `backend/infrastructure/exports/report_export.py` | 349 | HTML 报告生成 (markdown2) | → Go `internal/report/html.go` (goldmark) |
| `backend/infrastructure/exports/roadshow_export.py` | 237 | ZIP 导出 | → Go `internal/report/roadshow.go` |
| `backend/infrastructure/exports/report_charts.py` | 246 | Vega-Lite 图表配置 | → Go `internal/report/charts.go` |
| `backend/infrastructure/exports/markdown.py` | 34 | Markdown→HTML | → Go goldmark 直接替代 |
| `backend/infrastructure/tools/metrics.py` | 146 | 工具指标聚合 | → Go `internal/metrics/tool_metrics.go` |
| `backend/core/config.py` | 219 | Pydantic Settings | Go 网关只需读自己的 env |
| `backend/domain/workflows/market_insight_graph.py` | 84KB | LangGraph 状态机 | **保留 Python** |
| `backend/infrastructure/llm/ark_client.py` | ~100 | 火山引擎 SDK | **保留 Python** |
| `backend/domain/agents/` | 多文件 | 6 Agent 实现 | **保留 Python** |
| `backend/infrastructure/tools/` | 多文件 | 工具注册/缓存/护栏 | **保留 Python** |
| `backend/domain/services/evidence_pack.py` | ~200 | 证据链构建 | **保留 Python** |
| `backend/domain/services/session_snapshot.py` | 多文件 | 记忆快照 | **保留 Python** |
| `frontend/hooks/useStreamV2.js` | 373 | SSE 消费 + 自动恢复 | **无需修改** |
| `frontend/lib/constants.js` | 9 | API 端点定义 | 改 `API_BASE_URL` 指向 `:8080` |

---

## 三、Go 项目结构

```
gateway/
  cmd/gateway/main.go              # 入口，组装依赖
  internal/
    config/config.go                # 环境变量配置
    server/
      server.go                     # HTTP 服务器、优雅关闭
      middleware.go                 # CORS、请求 ID、日志、限流
      routes.go                     # chi 路由注册
    handler/
      health.go                     # GET /, /health, /api/v2/market-insight/health
      stream.go                     # POST /api/v2/market-insight/stream (SSE 中继)
      generate.go                   # POST /api/v2/market-insight/generate (同步代理)
      status.go                     # GET /api/v2/market-insight/status/{session_id}
      sessions.go                   # GET /api/v2/market-insight/sessions
      report.go                     # GET /api/v2/market-insight/report/{session_id}.html
      export.go                     # GET /api/v2/market-insight/export/{session_id}.zip
    db/
      postgres.go                   # pgx 连接池初始化
      session.go                    # create_session, update_session_fields, get_session_row, list_sessions_summary
      agent_result.go               # upsert_agent_result, list_agent_results
      debate.go                     # insert_debate_exchange, list_debate_exchanges
      workflow_event.go             # insert_workflow_event, list_workflow_events
      tool_invocation.go            # insert_tool_invocation, list_tool_invocations
    sse/
      relay.go                      # SSE 中继：消费 Python SSE → 重发给前端 + ping 保活
      event.go                      # SSE 帧解析（逐行 bufio.Scanner）
      eventsink.go                  # goroutine + buffered channel 替代 Python 后台线程
    report/
      html.go                       # HTML 报告 (goldmark + 内嵌 CSS 模板)
      roadshow.go                   # ZIP 导出 (archive/zip)
      charts.go                     # Vega-Lite 图表配置生成
    metrics/
      demo_metrics.go               # _build_demo_metrics 移植
      tool_metrics.go               # aggregate_tool_metrics 移植
    model/
      request.go                    # MarketInsightRequest, UserProfile struct
      response.go                   # MarketInsightResponse, SessionsListResponse 等
      event.go                      # SSE 事件类型常量
      session.go                    # WorkflowStatus 常量
  go.mod
  go.sum
  Dockerfile
```

### Go 技术选型

| 关注点 | 库 | 理由 |
|--------|---|------|
| HTTP 路由 | `net/http` + `go-chi/chi/v5` | 轻量，100% stdlib 兼容，中间件链 |
| PostgreSQL | `jackc/pgx/v5` + `pgxpool` | Go 最优 Postgres 驱动，原生 JSONB |
| SSE 输出 | `http.Flusher` (手写) | SSE 在 Go 中极简，无需第三方 |
| SSE 输入 | `bufio.Scanner` | 逐行读取 Python 响应 |
| 配置 | 手写 `os.Getenv` | 足够简单，无需框架 |
| 日志 | `log/slog` (stdlib) | Go 1.21+ 结构化日志 |
| Markdown→HTML | `yuin/goldmark` | 社区标准，替代 Python markdown2 |
| UUID | `google/uuid` | Session ID 生成 |
| ZIP | stdlib `archive/zip` | 无需第三方 |

---

## 四、分阶段迭代计划

---

### Phase 0：脚手架搭建

**目标**：Go 服务能启动、健康检查可达。前端仍连 Python :8000。

#### 要做的事

1. **初始化 Go module**
   - `gateway/` 目录，`go mod init`
   - 添加依赖：`chi/v5`, `pgx/v5`, `google/uuid`, `goldmark`

2. **实现入口 `cmd/gateway/main.go`**
   - 加载 `config.Load()`
   - 调用 `server.Run(cfg)`

3. **实现 `internal/config/config.go`**
   - 从环境变量读取：`LISTEN_ADDR`, `PYTHON_SERVICE_URL`, `CORS_ORIGINS`, PG 连接参数, 超时参数
   - 提供 `PGConfigured() bool` 判断数据库是否可用

4. **实现 `internal/server/server.go`**
   - `net/http.Server` + 优雅关闭（`signal.NotifyContext`）
   - 初始化 pgx 连接池（可选，连不上不影响启动）

5. **实现 `internal/server/middleware.go`**
   - CORS 中间件（复刻 Python `main.py` 第 33-48 行的 origins 列表）
   - 请求 ID 中间件（`X-Request-ID`）
   - 请求日志中间件（slog）

6. **实现 `internal/handler/health.go`**
   - `GET /` → `{"message":"Welcome to WeaveAI Backend!","version":"2.0.0",...}`
   - `GET /health` → `{"status":"healthy","version":"2.0.0","v2_available":true}`
   - `GET /api/v2/market-insight/health` → `{"status":"healthy","version":"2.0.0","features":{...}}`
   - **注意**：JSON 响应格式必须与 Python 版完全一致

7. **添加 `gateway/Dockerfile`**
   ```dockerfile
   FROM golang:1.22-alpine AS builder
   WORKDIR /app
   COPY go.* ./
   RUN go mod download
   COPY . .
   RUN CGO_ENABLED=0 go build -o /gateway ./cmd/gateway

   FROM alpine:3.19
   COPY --from=builder /gateway /gateway
   EXPOSE 8080
   CMD ["/gateway"]
   ```

8. **更新 `docker-compose.yml`**：添加 `gateway` 服务（port 8080），但前端仍指向 backend

#### 验收标准

- `curl http://localhost:8080/health` 返回 200
- `curl http://localhost:8080/api/v2/market-insight/health` 返回 200
- Go 服务与 Python 服务并行运行，互不干扰
- CORS 预检请求 (OPTIONS) 返回正确头

---

### Phase 1：透明代理 + SSE 中继

**目标**：前端切换到 Go :8080，Go 透明转发所有请求到 Python :8000，用户无感知。

#### 要做的事

1. **实现 `internal/sse/relay.go` — SSE 中继核心**
   ```
   Go handler 收到前端 POST /api/v2/market-insight/stream
     → 构造相同 POST 发给 Python http://agent:8000/api/v2/market-insight/stream
     → 获取 Python 的 streaming HTTP 响应
     → 设置响应头: Content-Type: text/event-stream, Cache-Control: no-cache, X-Accel-Buffering: no
     → 启动 ping goroutine: 每 15 秒写 ": ping\n\n" 并 Flush
     → 主循环:
          bufio.Scanner 逐行读取 Python 响应体
          累积完整 SSE 帧 (data: {...}\n\n)
          写入 Go 响应 → Flush
     → EOF / 客户端断连 (r.Context().Done()): 退出
   ```
   - **关键细节**：
     - Python `sse-starlette` 的 `ping=15` 发送 `: ping\n\n`，Go 必须在 Python ping 间隔内转发或自己补 ping
     - 前端 `STREAM_IDLE_TIMEOUT_MS = 20000`（20 秒），所以 Go 的 15 秒 ping 间隔有 5 秒余量
     - Python 的 SSE 格式是 `event: xxx\ndata: {json}\n\n`，Go 需要原样转发两行

2. **实现 `internal/sse/event.go` — SSE 帧解析**
   - 解析 `event:` 行和 `data:` 行
   - 处理 `: ping` 注释行（SSE 标准规定冒号开头为注释）
   - 处理 `data: [DONE]` 终止标记

3. **实现 `internal/handler/stream.go`**
   - `POST /api/v2/market-insight/stream`
   - 读取请求体 JSON → 原样转发给 Python
   - 调用 `sse.Relay()` 中继 Python 响应到前端
   - 客户端断连检测：`r.Context().Done()`
   - 超时：5 分钟（`cfg.StreamTimeout`）

4. **实现 `internal/handler/generate.go`**
   - `POST /api/v2/market-insight/generate`
   - 纯反向代理：转发请求到 Python，原样返回 JSON 响应

5. **实现 `internal/handler/status.go`**
   - `GET /api/v2/market-insight/status/{sessionID}`
   - Phase 1 中纯代理：转发到 Python

6. **实现 `internal/handler/sessions.go`**
   - `GET /api/v2/market-insight/sessions?limit=20&offset=0&status=completed`
   - Phase 1 中纯代理

7. **实现 `internal/handler/report.go`**
   - `GET /api/v2/market-insight/report/{sessionID}.html`
   - Phase 1 中纯代理

8. **实现 `internal/handler/export.go`**
   - `GET /api/v2/market-insight/export/{sessionID}.zip`
   - Phase 1 中纯代理

9. **前端切换**
   - `.env.local` 中 `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8080`
   - `docker-compose.yml` 中前端 `depends_on` 改为 `gateway`

10. **Python 改为内部访问**
    - `docker-compose.yml` 中 backend 的 `ports: ["8000:8000"]` 改为 `expose: ["8000"]`

#### 代理实现注意事项

```go
// 非 SSE 端点的通用代理模式
func (h *Handler) proxyToAgent(w http.ResponseWriter, r *http.Request) {
    targetURL := h.cfg.PythonServiceURL + r.URL.Path
    if r.URL.RawQuery != "" {
        targetURL += "?" + r.URL.RawQuery
    }
    proxyReq, _ := http.NewRequestWithContext(r.Context(), r.Method, targetURL, r.Body)
    proxyReq.Header = r.Header.Clone()
    resp, err := h.httpClient.Do(proxyReq)
    // ... 复制 resp.Body → w
}
```

#### 验收标准

- 前端指向 `:8080` 后，所有功能不变：
  - 流式分析完整运行（SSE 事件全部到达前端）
  - 状态轮询正常
  - 报告下载正常
  - ZIP 导出正常
- Go 的 ping 保活生效（前端 20 秒内不触发恢复模式）
- 客户端断连后 Go 正确关闭上游 Python 连接
- `useStreamV2.js` 的 30+ 种 SSE 事件类型全部正确中继

---

### Phase 2：数据库迁移到 Go

**目标**：Go 直接读写 PostgreSQL，Python 停止所有 DB 操作，仅产出 SSE 事件流。

#### 2.1 实现 `internal/db/` 包 — pgx 连接池

**文件 `postgres.go`**：
- `pgxpool.NewWithConfig` 初始化连接池
- 最大连接数 10（可配置）
- `Ping` 验证连通性

#### 2.2 移植 `pg_client.py` 的 18 个方法

**文件 `session.go`** — 会话 CRUD：

| Python 方法 | Go 函数 | SQL 逻辑 |
|------------|---------|---------|
| `create_session(session_id, profile, config)` | `CreateSession(ctx, sessionID, profile, config)` | INSERT ... ON CONFLICT DO NOTHING |
| `update_session_fields(session_id, fields)` | `UpdateSessionFields(ctx, sessionID, fields)` | 白名单列动态 UPDATE |
| `get_session_row(session_id)` | `GetSessionRow(ctx, sessionID)` | SELECT 22 列 |
| `get_session_full(session_id)` | `GetSessionFull(ctx, sessionID)` | SELECT get_session_full() |
| `list_sessions_summary(limit, offset, status)` | `ListSessionsSummary(ctx, limit, offset, status)` | 分页 + LEFT() + has_report |

- **注意**：`update_session_fields` 有列白名单（20 列），profile/evidence_pack/memory_snapshot 需 JSONB 处理
- pgx 原生支持 `map[string]any` → JSONB，无需 psycopg2 的 `Json()` 包装

**文件 `agent_result.go`**：

| Python 方法 | Go 函数 |
|------------|---------|
| `upsert_agent_result(session_id, agent_name, fields)` | `UpsertAgentResult(ctx, sessionID, agentName, fields)` |
| `list_agent_results(session_id)` | `ListAgentResults(ctx, sessionID)` |

- UPSERT 使用 `ON CONFLICT (session_id, agent_name) DO UPDATE`

**文件 `debate.go`**：

| Python 方法 | Go 函数 |
|------------|---------|
| `insert_debate_exchange(session_id, fields)` | `InsertDebateExchange(ctx, sessionID, fields)` |
| `list_debate_exchanges(session_id)` | `ListDebateExchanges(ctx, sessionID)` |

**文件 `workflow_event.go`**：

| Python 方法 | Go 函数 |
|------------|---------|
| `insert_workflow_event(session_id, event_type, payload, agent_name)` | `InsertWorkflowEvent(ctx, sessionID, eventType, payload, agentName)` |
| `list_workflow_events(session_id, limit)` | `ListWorkflowEvents(ctx, sessionID, limit)` |

**文件 `tool_invocation.go`**：

| Python 方法 | Go 函数 |
|------------|---------|
| `insert_tool_invocation(fields)` | `InsertToolInvocation(ctx, fields)` |
| `list_tool_invocations(session_id)` | `ListToolInvocations(ctx, sessionID)` |

- **兼容性**：需处理 Phase 4 迁移前后两种表结构（Python 中有 `sql_v4` 和 `sql_legacy` 两套 SQL）

#### 2.3 移植 `event_sink.py` → Go goroutine + channel

**文件 `internal/sse/eventsink.go`**：

核心结构：
```go
type EventSink struct {
    sessionID string
    profile   map[string]any
    config    map[string]any
    pool      *db.Pool
    ch        chan sinkJob   // buffered channel, cap=2000
    done      chan struct{}

    // 运行期聚合缓存
    agentBufs    map[string]*agentBuf     // agent_chunk/thinking 累积
    exchangeParts map[exchangeKey]*exchangeBuf // 辩论交换组装
    toolStarts   map[string]*toolStartBuf  // tool_start 缓存
    debateCtx    debateContext             // 当前辩论轮次/类型
}
```

**需移植的事件处理逻辑**（event_sink.py `on_event` 方法，按事件类型）：

| 事件类型 | 处理逻辑 |
|---------|---------|
| `orchestrator_start` | 更新 session: status=running, phase=gather, 写入 profile 字段 |
| `orchestrator_end` | 更新 session: status=completed, phase=complete, 写入 synthesized_report/evidence_pack/memory_snapshot |
| `error` | 更新 session: status=failed, phase=error |
| `agent_start` | 初始化 agentBuf，upsert agent_result status=running |
| `agent_chunk` | 追加到 agentBuf.content |
| `agent_thinking` | 追加到 agentBuf.thinking |
| `agent_end` | 拼接 buf → upsert agent_result (content, thinking, sources, duration_ms) |
| `agent_error` | upsert agent_result status=failed |
| `tool_start` | 缓存 toolStartBuf (invocation_id, tool_name, agent_name, input, started_at) |
| `tool_end` / `tool_error` | 与 tool_start 配对 → insert_tool_invocation |
| `guardrail_triggered` | 更新 session: enable_websearch=false |
| `debate_round_start` | 更新 debateCtx，更新 session phase |
| `agent_challenge` / `agent_respond` / `agent_followup` | 向 exchangeParts 追加内容 |
| `agent_challenge_end` / `agent_respond_end` / `agent_followup_end` | 完成交换，调用 flushExchange |
| `challenge_chunk` / `respond_chunk` / `followup_chunk` | 追加到对应 exchangeParts |

**关键移植细节**：
- Python 的 exchange key 是 `(round_number, challenger, responder)`
- `agent_respond` 的 from/to 与 challenge 相反，需翻转
- `revised` 判断：显式字段 OR 响应内容包含"修订"/"修改"
- 非 chunk 事件都要写 `workflow_events` 表（`_log_workflow_event`）

#### 2.4 移植指标计算

**文件 `internal/metrics/tool_metrics.go`**：
- 移植 `tools/metrics.py` 的 `aggregate_tool_metrics(invocations)` 函数
- 按 session 和 by_agent 两个维度聚合：total_calls, error_count, error_rate, avg_duration_ms, total_estimated_cost_usd, cache_hit_count, cache_hit_rate

**文件 `internal/metrics/demo_metrics.go`**：
- 移植 `market_insight.py` 的 `_build_demo_metrics()` 函数（第 67-184 行）
- 输入：session_row, agent_results, workflow_events, tool_metrics
- 计算：stability_score（惩罚公式）, evidence_coverage_rate, degrade_count 等

#### 2.5 修改 handler 为 Go 直连 DB

- `handler/status.go`：不再代理到 Python，Go 直接查询 DB 并组装响应
  - 调用 `db.GetSessionRow` → `db.ListAgentResults` → `db.ListDebateExchanges` → `db.ListWorkflowEvents` → `db.ListToolInvocations` → `db.AggregateToolMetrics`
  - 调用 `metrics.BuildDemoMetrics` 和 `report.BuildReportCharts`
  - 按需回补 evidence_pack / memory_snapshot（**注意**：这部分逻辑依赖 Python 的 `build_evidence_pack` 和 `build_memory_snapshot`，Phase 2 中仍需代理到 Python 或暂不回补）

- `handler/sessions.go`：Go 直接查 `db.ListSessionsSummary`

- `handler/stream.go`：SSE 中继 + 同时解析事件喂给 EventSink（Go goroutine 旁路写 DB）

#### 2.6 Python 停止 DB 写入

- `market_insight.py` 中 `stream_market_insight` 不再创建 `event_sink`
- `generate_market_insight` 不再直接写 DB
- Python 服务仅产出 SSE 事件流，Go 负责所有持久化

#### 验收标准

- 运行一次完整流式分析，Go Event Sink 正确写入所有 5 张表
- `GET /status/{sessionID}` 返回的数据与 Python 版完全一致
- `GET /sessions` 分页、过滤正常
- 模拟 2000+ 事件队列满的情况，Go 丢弃但不阻塞 SSE
- stability_score / evidence_coverage_rate 与 Python 版计算结果一致

---

### Phase 3：报告导出迁移

**目标**：Go 生成 HTML 报告和 ZIP 导出包，Python 不再参与报告生成。

#### 3.1 移植 `report_export.py` → `internal/report/html.go`

**需移植的函数**：

| Python 函数 | Go 函数 | 说明 |
|------------|---------|------|
| `get_reports_dir()` | `ReportsDir(cfg)` | 返回 `{artifacts}/reports/` |
| `get_report_file_path(session_id)` | `ReportFilePath(cfg, sessionID)` | 路径拼接 |
| `_build_profile_meta(profile)` | `buildProfileMeta(profile)` | HTML 元信息 |
| `_build_chart_section(chart_bundle)` | `buildChartSection(chartBundle)` | Vega-Lite 图表 + JS 渲染脚本 |
| `build_report_html(...)` | `BuildReportHTML(sessionID, reportMD, profile, chartBundle)` | 完整 HTML 文档 |
| `write_html_report(...)` | `WriteHTMLReport(cfg, sessionID, reportMD, profile, chartBundle)` | 写入文件 |

**Markdown → HTML**：
- Python 使用 `markdown2` 库（extras: tables, fenced-code-blocks, strike, target-blank-links）
- Go 使用 `goldmark` + 扩展（table, strikethrough, linkify）
- **注意**：两者可能有细微渲染差异，需视觉验证

**HTML 模板**：
- 完整内嵌 CSS（report_export.py 第 232-305 行的样式）
- Vega-Lite CDN 引用 + 渲染脚本（第 121-193 行）
- 用 Go `html/template` 或字符串拼接均可

#### 3.2 移植 `roadshow_export.py` → `internal/report/roadshow.go`

| Python 函数 | Go 函数 |
|------------|---------|
| `get_roadshow_zip_path(session_id)` | `RoadshowZipPath(cfg, sessionID)` |
| `build_executive_summary_markdown(...)` | `BuildExecutiveSummary(...)` |
| `write_roadshow_zip(...)` | `WriteRoadshowZip(...)` |

**ZIP 内容**（8 个文件）：
```
weaveai-roadshow-{session_id}/
  ├── report.html
  ├── executive_summary.md
  ├── session_snapshot.json
  ├── evidence_pack.json
  ├── memory_snapshot.json
  ├── demo_metrics.json
  ├── tool_metrics.json
  ├── report_charts.json
  ├── workflow_timeline.json
  └── manifest.json
```

- 使用 stdlib `archive/zip` + `ZIP_DEFLATED`

#### 3.3 移植 `report_charts.py` → `internal/report/charts.go`

| Python 函数 | Go 函数 |
|------------|---------|
| `_overview_chart(demo_metrics)` | `overviewChart(demoMetrics)` |
| `_tool_agent_chart(tool_metrics)` | `toolAgentChart(toolMetrics)` |
| `_degrade_breakdown_chart(demo_metrics)` | `degradeBreakdownChart(demoMetrics)` |
| `build_report_charts(...)` | `BuildReportCharts(sessionID, profile, demoMetrics, toolMetrics)` |

- 输出纯 JSON 结构（Vega-Lite spec），无特殊依赖

#### 3.4 修改 handler

- `handler/report.go`：Go 直接生成 HTML 报告并 serve
- `handler/export.go`：Go 生成 ZIP 并返回 `FileResponse`

#### 验收标准

- Go 生成的 HTML 报告视觉上与 Python 版一致（打开浏览器对比）
- ZIP 包结构完整，manifest.json 字段正确
- Vega-Lite 图表在浏览器中正确渲染
- 表格、代码块、删除线等 Markdown 特性正确转换

---

### Phase 4：Python 精简

**目标**：删除 Python 中已迁移到 Go 的代码，创建最小内部 API。

#### 要做的事

1. **删除 Python 文件**：
   - `backend/api/routers/` — 整个目录（Go 已接管所有 HTTP 路由）
   - `backend/schemas/` — 整个目录（Go 已有对应 model）
   - `backend/infrastructure/db/pg_client.py` — Go 已接管 DB
   - `backend/infrastructure/db/event_sink.py` — Go 已接管 event sink
   - `backend/infrastructure/exports/report_export.py` — Go 已接管
   - `backend/infrastructure/exports/roadshow_export.py` — Go 已接管
   - `backend/infrastructure/exports/report_charts.py` — Go 已接管
   - `backend/infrastructure/exports/markdown.py` — Go 已接管
   - `backend/infrastructure/exports/rehearsal_log.py` — Go 可直接处理或删除

2. **创建最小 Python 入口 `backend/internal_app.py`**：
   ```python
   # 仅暴露两个内部端点，供 Go 网关调用
   app = FastAPI(title="WeaveAI Agent Service (Internal)")

   @app.post("/internal/stream")
   async def internal_stream(request: Request):
       # 与原 stream_market_insight 相同，但不创建 event_sink
       # 直接返回 EventSourceResponse

   @app.post("/internal/generate")
   async def internal_generate(request: Request):
       # 与原 generate_market_insight 相同，但不写 DB
       # 返回结果 JSON
   ```

3. **保留的 Python 文件**：
   - `core/graph_engine.py` — LangGraph 核心
   - `core/ark_client.py` — 火山引擎 SDK
   - `core/config.py` — Agent 配置
   - `core/evidence_pack.py` — 证据链构建
   - `core/exceptions.py`
   - `agents/` — 全部保留
   - `tools/` — 全部保留
   - `memory/` — 全部保留

4. **更新 Python Dockerfile**：
   - 入口改为 `internal_app:app`
   - 可删除 `markdown2`、`sse-starlette` 等不再需要的依赖（如果 internal 端点不用 SSE 则保留 sse-starlette）

5. **更新 Go 配置**：
   - `PYTHON_SERVICE_URL` 的路径从 `/api/v2/market-insight/stream` 改为 `/internal/stream`

#### 验收标准

- Python 服务仅暴露 `/internal/stream` 和 `/internal/generate`
- `curl http://agent:8000/api/v2/market-insight/stream` 返回 404
- Go 网关调用内部端点正常工作
- Python 镜像体积减小

---

### Phase 5：加固

**目标**：生产级加固，提升可靠性和可观测性。

#### 要做的事

1. **请求超时**
   - SSE stream: 5 分钟（可配置 `STREAM_TIMEOUT`）
   - 同步请求: 30 秒
   - Go → Python 连接超时: 10 秒

2. **熔断 / 重试**
   - Go → Python 内部调用加指数退避重试（最多 3 次）
   - Python 服务不可用时返回 503 而非挂死
   - Docker healthcheck + Go 端启动时等待 Python 就绪

3. **请求 ID 传播**
   - `X-Request-ID` 从前端 → Go → Python 全链路传递
   - 日志中统一打印 request_id

4. **结构化日志**
   - 全部使用 `slog.Info/Warn/Error`
   - 包含 session_id, request_id, method, path, status, duration_ms

5. **限流中间件**
   - `golang.org/x/time/rate` 令牌桶
   - 可配置 QPS 上限

6. **Prometheus 指标端点**
   - `GET /metrics`
   - 指标：request_count, request_duration_histogram, active_sse_connections, eventsink_queue_size, db_query_duration

7. **SSE 中继集成测试**
   - 录制一次完整 SSE 流 → 回放测试
   - 覆盖 30+ 种事件类型
   - 模拟 Python 中途断开
   - 模拟前端中途断开

#### 验收标准

- 模拟 Python 服务重启，Go 自动重试并恢复
- 日志可追踪完整请求链路
- `/metrics` 返回 Prometheus 格式指标
- 高并发压测无 goroutine 泄漏

---

## 五、Docker Compose 最终配置

```yaml
services:
  gateway:
    build: ./gateway
    image: weaveai-gateway:latest
    ports:
      - "8080:8080"
    environment:
      LISTEN_ADDR: ":8080"
      PYTHON_SERVICE_URL: "http://agent:8000"
      PGHOST: "${PGHOST:-127.0.0.1}"
      PGPORT: "${PGPORT:-5432}"
      PGUSER: "${PGUSER}"
      PGPASSWORD: "${PGPASSWORD}"
      PGDATABASE: "${PGDATABASE:-postgres}"
      PGSSLMODE: "${PGSSLMODE:-disable}"
      CORS_ORIGINS: "http://localhost:3000,http://127.0.0.1:3000"
      STREAM_TIMEOUT: "5m"
      SSE_PING_INTERVAL: "15s"
    depends_on:
      agent:
        condition: service_healthy

  agent:
    build: ./backend
    image: weaveai-agent:latest
    expose:
      - "8000"  # 仅内部访问
    env_file:
      - ./backend/.env
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  frontend:
    build: ./frontend
    image: weaveai-frontend:latest
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_BASE_URL: "http://gateway:8080"
    depends_on:
      - gateway
```

---

## 六、关键实现细节与陷阱

### 6.1 SSE Ping 保活

| 项目 | Python 现状 | Go 必须复刻 |
|------|-----------|-----------|
| Ping 间隔 | `sse-starlette` 的 `ping=15` | 每 15 秒 `: ping\n\n` |
| Ping 格式 | `: ping\n\n`（SSE 注释行） | 相同 |
| 前端超时 | `STREAM_IDLE_TIMEOUT_MS = 20000` | 15 秒 ping < 20 秒超时 |

### 6.2 客户端断连检测

| Python | Go |
|--------|-----|
| `await http_request.is_disconnected()` | `<-r.Context().Done()` |

### 6.3 Event Sink 后台写入

| Python | Go |
|--------|-----|
| `threading.Thread` + `queue.Queue(maxsize=2000)` | `goroutine` + `chan sinkJob (cap 2000)` |
| `queue.Full` → 丢弃 + log warning | `select { case ch <- job: default: slog.Warn(...) }` |
| `__stop__` 哨兵 → 退出 | `close(ch)` → for range 自动退出 |

### 6.4 JSONB 处理差异

| psycopg2 | pgx/v5 |
|----------|--------|
| `Json(dict)` 包装 | `map[string]any` 直接传入 |
| `cur.description` 获取列名 | `pgx.CollectRows` + `pgx.RowToMap` |

### 6.5 时间戳序列化

Python 的 `datetime.now().isoformat()` 输出 `2024-01-01T12:00:00.123456`（无时区）。前端 `useStreamV2.js` 不解析时间戳，直接存储，所以格式差异影响不大。但 DB 写入的 `completed_at` 等字段建议统一用 UTC。

### 6.6 前端 SSE 解析兼容性

`useStreamV2.js` 第 238-281 行的 `consumeSSEBlocks` 函数：
- 处理 `\r\n`、`\r`、`\n` 三种换行
- 忽略 `:` 开头的注释行
- 提取 `data:` 行并 JSON.parse
- 检测 `[DONE]` 标记

Go 只需确保输出格式为标准 SSE：
```
event: agent_chunk\n
data: {"event":"agent_chunk",...}\n
\n
```

---

## 七、风险与缓解

| 风险 | 严重度 | 缓解措施 |
|------|--------|---------|
| SSE 中继丢事件或破坏帧格式 | **高** | 录制 Python SSE 流做回放测试，覆盖 30+ 事件类型 |
| Event Sink 状态机移植错误 | **高** | 逐事件类型写单元测试，对比 Python 写入的 DB 记录 |
| DB 行为差异 (psycopg2 vs pgx) | 中 | 两端 autocommit；JSONB 用 pgx 原生支持 |
| Python 服务启动依赖 | 中 | docker-compose healthcheck + Go 指数退避重试 |
| 前端 SSE 解析兼容性 | 低 | Go 精确复刻 Python 的 SSE 帧格式（含 ping） |
| 报告 HTML 渲染差异 (goldmark vs markdown2) | 低 | 视觉对比验证；关键：表格扩展需启用 |
| evidence_pack 按需回补依赖 Python | 中 | Phase 2 保留代理到 Python 的回补逻辑 |

---

## 八、总工期估算

| 阶段 | 预估天数 | 核心风险 |
|------|---------|---------|
| Phase 0: 脚手架 | 1-2 | 无 |
| Phase 1: 透明代理 | 2-3 | SSE 中继帧格式、ping 保活 |
| Phase 2: DB 迁移 | 3-4 | Event Sink 状态机复杂度 |
| Phase 3: 报告导出 | 2-3 | Markdown 渲染差异 |
| Phase 4: Python 精简 | 1-2 | 内部 API 路由切换 |
| Phase 5: 加固 | 2-3 | 集成测试覆盖度 |
| **合计** | **11-17** | |

---

## 九、逐阶段验证方式

1. **Phase 0**：`curl :8080/health` 返回 200
2. **Phase 1**：前端切 `:8080`，跑 3 种 Demo Preset（60s / 3min / 深度），全流程无异常
3. **Phase 2**：Python 停止 DB 写入后，Go Event Sink 写入的数据与之前一致（对比 DB 记录）
4. **Phase 3**：Go 生成的 HTML 报告和 ZIP 与 Python 版视觉一致
5. **Phase 4**：Python 仅暴露 `/internal/*`，外部请求 `/api/v2/*` 返回 404
6. **Phase 5**：模拟 SSE 断连，前端自动恢复；`/metrics` 可达
7. **端到端**：运行 3 种 Demo Preset，全流程无错误，报告可下载
