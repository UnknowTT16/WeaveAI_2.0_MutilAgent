# Phase 3 验收（WeaveAI 2.0）

目标：完成 Phase 3 的“证据链 + 轻量记忆 + 可回放”闭环，支持比赛前稳定复核。

## 0. 前置条件

- 已完成 `PHASE1_ACCEPTANCE.md` 与 `PHASE2_ACCEPTANCE.md` 的环境准备。
- 后端可连接本地 Postgres/Supabase Postgres。

## 1. 执行 Phase 3 迁移

运行位置：`PowerShell`，项目根目录

```powershell
docker exec -i supabase-db psql -U supabase_admin -d postgres < backend/database/migrations/004_phase3_evidence_memory.sql
```

校验新增列：

```powershell
docker exec supabase-db psql -U supabase_admin -d postgres -c "\\d+ public.sessions"
```

## 2. 启动后端

运行位置：`PowerShell`，`backend` 目录

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

## 3. 单会话验收（Evidence Pack + 记忆快照）

运行位置：`PowerShell`，项目根目录

```powershell
$sid = [guid]::NewGuid().ToString()
$payload = @"
{
  "session_id": "$sid",
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
"@

C:\Windows\System32\curl.exe -s -H "Content-Type: application/json" -X POST http://127.0.0.1:8000/api/v2/market-insight/generate -d "$payload"
C:\Windows\System32\curl.exe -s http://127.0.0.1:8000/api/v2/market-insight/status/$sid
```

预期：

- `status.session.evidence_pack` 存在，且包含 `claims` / `sources` / `traceability`。
- `status.session.memory_snapshot` 存在，且包含 `entities` / `agent_highlights`。

## 4. 批量回放验收（10 组样本）

运行位置：`PowerShell`，`backend` 目录

```powershell
.\.venv\Scripts\python.exe .\scripts\replay_phase3.py --samples-dir .\scripts\samples\phase3 --api-base http://127.0.0.1:8000 --out ..\artifacts\phase3\replay_results.jsonl
```

预期：

- 输出文件 `artifacts/phase3/replay_results.jsonl` 生成成功。
- 脚本汇总中 `通过` 数量与样本数量一致或接近（受外部模型波动影响）。

## 5. 数据库验收

运行位置：`PowerShell`，项目根目录

```powershell
docker exec supabase-db psql -U supabase_admin -d postgres -c "select id,status,phase,evidence_generated_at,memory_snapshot_generated_at from public.sessions order by created_at desc limit 10;"
```

```powershell
docker exec supabase-db psql -U supabase_admin -d postgres -c "select id, (evidence_pack is not null) as has_evidence, (memory_snapshot is not null) as has_memory from public.sessions order by created_at desc limit 10;"
```

## 6. Phase 3 通过标准

- [ ] 任意 `session_id` 会话可生成 `evidence_pack`。
- [ ] `/status/{session_id}` 能返回并回补 `memory_snapshot`。
- [ ] `evidence_pack.traceability` 可用于回答“结论来源于哪个 Agent/来源”。
- [ ] 10 组样本可通过回放脚本批量运行并产出结果文件。
