# Phase 4 验收（WeaveAI 2.0）

目标：完成 Phase 4 的“工具层收敛 + 成本韧性 + 护栏降级 + 缓存复现 + 指标面板”闭环。

## 0. 前置条件

- 已完成 `PHASE3_ACCEPTANCE.md`。
- 本地 Supabase/Postgres 可用，后端可连接数据库。

## 1. 执行 Phase 4 迁移

运行位置：`PowerShell`，项目根目录

```powershell
docker exec -i supabase-db psql -U supabase_admin -d postgres < backend/database/migrations/005_phase4_tool_metrics.sql
```

校验字段：

```powershell
docker exec supabase-db psql -U supabase_admin -d postgres -c "\d+ public.tool_invocations"
```

## 2. 启动后端与前端

运行位置：`PowerShell`，`backend` 目录

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

运行位置：`PowerShell`，`frontend` 目录

```powershell
npm run dev
```

## 3. ToolRegistry 与指标回传验收

运行位置：`PowerShell`，项目根目录

```powershell
$sid=[guid]::NewGuid().ToString()
$body=@{
  session_id=$sid
  profile=@{
    target_market="Germany"
    supply_chain="Consumer Electronics"
    seller_type="brand"
    min_price=30
    max_price=90
  }
  debate_rounds=2
  enable_followup=$true
  enable_websearch=$true
  retry_max_attempts=2
  retry_backoff_ms=300
  degrade_mode="partial"
} | ConvertTo-Json -Depth 6 -Compress

C:\Windows\System32\curl.exe -s -H "Content-Type: application/json" -X POST "http://127.0.0.1:8000/api/v2/market-insight/generate" -d $body > $null
C:\Windows\System32\curl.exe -s "http://127.0.0.1:8000/api/v2/market-insight/status/$sid" | python -m json.tool
```

预期：

- `/status/{session_id}` 返回 `tool_invocations` 与 `tool_metrics`。
- `tool_invocations` 每条记录包含 `invocation_id`、`status`、`estimated_*`。

## 4. 护栏触发验收

先临时设置较低阈值后重启后端：

```powershell
$env:TOOL_GUARDRAIL_MAX_ESTIMATED_COST_USD="0.000001"
$env:TOOL_GUARDRAIL_MAX_ERROR_RATE="0.1"
$env:TOOL_GUARDRAIL_MIN_CALLS_FOR_ERROR_RATE="1"
```

复跑一次第 3 步，预期：

- SSE 流中出现 `guardrail_triggered` 事件。
- 后续工具调用减少或禁用，但会话仍能产出 `orchestrator_end.final_report`。

## 5. 缓存有效性验收

同一 `profile + debate_rounds + enable_websearch` 连续执行两次，比较两次状态接口输出：

- 第二次 `tool_metrics.session.cache_hit_rate` 高于第一次。
- 第二次 `tool_metrics.session.avg_duration_ms` 有下降趋势。

## 6. 数据库核验

运行位置：`PowerShell`，项目根目录

```powershell
docker exec supabase-db psql -U supabase_admin -d postgres -c "select session_id,invocation_id,agent_name,tool_name,status,duration_ms,cache_hit,estimated_input_tokens,estimated_output_tokens,estimated_cost_usd,started_at,finished_at,created_at from public.tool_invocations order by created_at desc limit 30;"
```

## 7. Phase 4 通过标准

- [ ] ToolRegistry Lite 接管当前 `web_search` 调用路径。
- [ ] `/status/{session_id}` 返回 `tool_invocations` 与 `tool_metrics.session/by_agent`。
- [ ] 成本数据使用估算口径并统一标记 `cost_mode=estimate`。
- [ ] 护栏触发后自动关闭后续 `web_search`，主流程仍能完成。
- [ ] 缓存命中可观测，重复请求时命中率可上升。
- [ ] 前端显示“成本与稳定性”指标面板，并兼容后端缺省字段。
- [ ] 复跑 `backend/scripts/replay_phase3.py` 不回退 Phase 3 核心能力。
