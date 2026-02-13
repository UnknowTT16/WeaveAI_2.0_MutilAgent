# Phase 2 收口验收（WeaveAI 2.0）

目标：完成 Phase 2 收口项，重点验证：

- `debate_rounds` 路由生效（0/1/2）。
- 节点级重试 + 降级策略（`skip/partial/fail`）可追踪（`retry` 事件）。
- SSE 契约一致性（含 `tool_start/tool_end`、`agent_challenge_end/agent_respond_end`）。
- 断连后可通过 `/status/{session_id}` 恢复状态。

## 0. 前置条件

- 已完成 `PHASE1_ACCEPTANCE.md` 中的数据库迁移与基础环境准备。
- `backend/.env` 可正常连接本地 Postgres（或 Supabase Postgres）。
- Windows 建议使用系统 curl：`C:\Windows\System32\curl.exe`。

## 1. 启动后端

运行位置：`PowerShell`，项目根目录

```powershell
cd .\backend
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

健康检查：

```powershell
C:\Windows\System32\curl.exe http://127.0.0.1:8000/health
C:\Windows\System32\curl.exe http://127.0.0.1:8000/api/v2/market-insight/health
```

### 1.1 可选：离线快速冒烟（无需真实 API Key）

运行位置：`PowerShell`，项目根目录

```powershell
cd .\backend
python .\p2_smoke.py
```

预期输出关键行：

- `rounds=0, debate_exchanges=0`
- `rounds=1, debate_exchanges=4`
- `rounds=2, debate_exchanges=8`
- `partial ... has_orchestrator_end=True`
- `fail ... has_error=True has_orchestrator_end=False`

## 2. 场景 A：`debate_rounds` 路由验收（0/1/2）

运行位置：`PowerShell`，项目根目录

```powershell
New-Item -ItemType Directory -Force -Path .\artifacts | Out-Null
$profile='{"target_market":"Germany","supply_chain":"Consumer Electronics","seller_type":"brand","min_price":30,"max_price":90}'

foreach($r in 0,1,2){
  $payload="{`"profile`":$profile,`"debate_rounds`":$r,`"enable_followup`":true,`"enable_websearch`":false,`"retry_max_attempts`":2,`"retry_backoff_ms`":300,`"degrade_mode`":`"partial`"}"
  C:\Windows\System32\curl.exe -sN -H "Accept: text/event-stream" -H "Content-Type: application/json" `
    -X POST http://127.0.0.1:8000/api/v2/market-insight/stream `
    -d "$payload" | Tee-Object -FilePath ".\artifacts\p2_round_$r.log" | Out-Null
}
```

检查事件：

```powershell
Write-Host "==== round 0 ===="
Select-String -Path .\artifacts\p2_round_0.log -Pattern "debate_round_start|debate_round_end|orchestrator_end" | % { $_.Line }

Write-Host "==== round 1 ===="
Select-String -Path .\artifacts\p2_round_1.log -Pattern "debate_round_start|debate_round_end|orchestrator_end" | % { $_.Line }

Write-Host "==== round 2 ===="
Select-String -Path .\artifacts\p2_round_2.log -Pattern "debate_round_start|debate_round_end|orchestrator_end" | % { $_.Line }
```

预期：

- `round=0`：无 `debate_round_start`，直接进入 `orchestrator_end`。
- `round=1`：仅出现第 1 轮（`peer_review`），不出现第 2 轮。
- `round=2`：出现第 1 轮与第 2 轮（`red_team`）。

## 3. 场景 B：重试与降级验收（`retry` + `degrade_mode`）

为可复现触发失败，建议临时在后端终端设置错误的 `ARK_API_KEY` 后重启后端。

### 3.1 `degrade_mode=partial`（应继续产出报告）

```powershell
$payload='{"profile":{"target_market":"Germany","supply_chain":"Consumer Electronics","seller_type":"brand","min_price":30,"max_price":90},"debate_rounds":0,"enable_followup":false,"enable_websearch":false,"retry_max_attempts":2,"retry_backoff_ms":200,"degrade_mode":"partial"}'
C:\Windows\System32\curl.exe -sN -H "Accept: text/event-stream" -H "Content-Type: application/json" -X POST http://127.0.0.1:8000/api/v2/market-insight/stream -d "$payload" | Tee-Object -FilePath .\artifacts\p2_retry_partial.log
```

```powershell
Select-String -Path .\artifacts\p2_retry_partial.log -Pattern '"event":"retry"|"event":"agent_error"|"event":"orchestrator_end"'
```

预期：

- 出现 `retry` 事件。
- 出现 `agent_error`（失败节点）。
- 最终仍出现 `orchestrator_end`（部分可用报告）。

### 3.2 `degrade_mode=fail`（应终止流程）

```powershell
$payload='{"profile":{"target_market":"Germany","supply_chain":"Consumer Electronics","seller_type":"brand","min_price":30,"max_price":90},"debate_rounds":0,"enable_followup":false,"enable_websearch":false,"retry_max_attempts":2,"retry_backoff_ms":200,"degrade_mode":"fail"}'
C:\Windows\System32\curl.exe -sN -H "Accept: text/event-stream" -H "Content-Type: application/json" -X POST http://127.0.0.1:8000/api/v2/market-insight/stream -d "$payload" | Tee-Object -FilePath .\artifacts\p2_retry_fail.log
```

```powershell
Select-String -Path .\artifacts\p2_retry_fail.log -Pattern '"event":"retry"|"event":"error"|"event":"orchestrator_end"'
```

预期：

- 出现 `retry`。
- 最终出现 `error`。
- 不应出现 `orchestrator_end`。

## 4. 场景 C：SSE 断连恢复验收

### 4.1 发起带固定 `session_id` 的流

运行位置：`PowerShell`，项目根目录

```powershell
$sid = "acc-" + [guid]::NewGuid().ToString()
$payload="{`"session_id`":`"$sid`",`"profile`":{`"target_market`":`"Germany`",`"supply_chain`":`"Consumer Electronics`",`"seller_type`":`"brand`",`"min_price`":30,`"max_price`":90},`"debate_rounds`":2,`"enable_followup`":true,`"enable_websearch`":false,`"retry_max_attempts`":2,`"retry_backoff_ms`":300,`"degrade_mode`":`"partial`"}"
C:\Windows\System32\curl.exe -N -H "Accept: text/event-stream" -H "Content-Type: application/json" -X POST http://127.0.0.1:8000/api/v2/market-insight/stream -d "$payload"
```

手动在中途 `Ctrl + C` 断开客户端连接。

### 4.2 使用状态接口恢复

```powershell
C:\Windows\System32\curl.exe http://127.0.0.1:8000/api/v2/market-insight/status/$sid
```

预期：

- 能返回 `session`、`agent_results`、`debate_exchanges`、`workflow_events`。
- `session.status` 为 `running/completed/failed` 之一（而不是 `not_found`）。

## 5. 数据库验收（事件可追踪）

在数据库中检查关键事件：

```sql
select id, status, phase, current_debate_round, created_at, completed_at
from public.sessions
order by created_at desc
limit 5;

-- 替换 <SESSION_UUID>
select event_type, agent_name, created_at
from public.workflow_events
where session_id = '<SESSION_UUID>'
  and event_type in (
    'retry',
    'tool_start',
    'tool_end',
    'agent_challenge_end',
    'agent_respond_end',
    'orchestrator_end'
  )
order by created_at asc;

select agent_name, status, duration_ms, error_message, completed_at
from public.agent_results
where session_id = '<SESSION_UUID>'
order by created_at asc;
```

## 6. 前端验收（SSE 契约一致性）

运行位置：`PowerShell`，`frontend` 目录

```powershell
npm run dev
```

手工检查：

- 发起一次分析后，页面能正常展示 Agent 状态与最终报告。
- 控制台不再持续打印 `Unknown SSE event` 噪音。
- 断网或手动中断后，刷新页面可通过后端状态接口回补结果。

## 7. Phase 2 通过标准（收口）

- [x] `debate_rounds=0/1/2` 路由符合预期。
- [x] 至少 1 次可复现 `retry` 事件，且可在 `workflow_events` 查询到。
- [x] `degrade_mode=partial` 能输出最终报告，`degrade_mode=fail` 能终止并返回错误。
- [x] SSE 断连后可通过 `/status/{session_id}` 恢复状态。
- [x] 前端无持续 `Unknown SSE event` 噪音。
