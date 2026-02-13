# Phase 1 验收（WeaveAI 2.0）

目标：完成 Phase 1 的“模块化 + 协议 + 最小落库闭环”，确保可复现验收。

## 0. 前置条件

- 本地 Supabase/Postgres 通过 docker-compose 已启动（含容器 `supabase-db` / `supabase-pooler`）。
- 后端使用本机 Python 3.11 虚拟环境运行。

## 1. 数据库迁移（一次性）

以 `supabase_admin` 身份在容器内执行：

```bash
docker exec -i supabase-db psql -U supabase_admin -d postgres < backend/database/migrations/002_align_v2_schema.sql
docker exec -i supabase-db psql -U supabase_admin -d postgres < backend/database/migrations/003_update_views_and_functions.sql
```

校验关键列是否存在：

```bash
docker exec supabase-db psql -U supabase_admin -d postgres -c "\\d+ public.sessions"
docker exec supabase-db psql -U supabase_admin -d postgres -c "\\d+ public.debate_exchanges"
docker exec supabase-db psql -U supabase_admin -d postgres -c "\\d public.agent_results"
```

## 2. 后端配置（backend/.env）

后端采用 Postgres 直连（Phase 1），以下键名兼容小写：

```env
user=...
password=...
host=127.0.0.1
port=5432
dbname=postgres
sslmode=disable
connect_timeout=8
```

说明：Phase 1 为快速验收，使用高权限账号直连写入（等价“service role”）。

## 3. 启动后端

```bash
cd backend
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v2/market-insight/health
```

## 4. 触发一次工作流（SSE）

```bash
curl -N -H "Accept: text/event-stream" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8000/api/v2/market-insight/stream \
  -d '{"profile":{"target_market":"Germany","supply_chain":"Consumer Electronics","seller_type":"品牌方","min_price":30,"max_price":90},"debate_rounds":2,"enable_followup":true,"enable_websearch":false}'
```

## 5. 验收：落库闭环

在数据库中查询最新 session：

```sql
select id, status, phase, created_at
from public.sessions
order by created_at desc
limit 5;
```

替换 `<SESSION_UUID>`：

```sql
select agent_name, status, duration_ms, error_message, created_at, completed_at
from public.agent_results
where session_id = '<SESSION_UUID>'
order by created_at asc;

select round_number, debate_type, challenger, responder, revised, created_at
from public.debate_exchanges
where session_id = '<SESSION_UUID>'
order by round_number asc, created_at asc;

select event_type, agent_name, created_at
from public.workflow_events
where session_id = '<SESSION_UUID>'
order by created_at asc;
```

（可选）状态接口：

```bash
curl http://127.0.0.1:8000/api/v2/market-insight/status/<SESSION_UUID>
```
