# backend/database/pg_client.py
"""\
Postgres 直连客户端（Phase 1）

说明：
- 当前项目使用 docker-compose 启动本地 Supabase/Postgres
- Phase 1 为了快速验收，采用直连 Postgres 的方式做最小写入闭环
- 后续可再切换为 Supabase API（service role key）并收紧 RLS
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Any, Optional

import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

from tools.metrics import aggregate_tool_metrics


logger = logging.getLogger(__name__)


def _getenv_any(*keys: str) -> Optional[str]:
    for k in keys:
        v = os.getenv(k)
        if v is not None and str(v).strip() != "":
            return v
    return None


@dataclass(frozen=True)
class PgDsn:
    user: str
    password: str
    host: str
    port: int
    dbname: str
    sslmode: Optional[str] = None
    connect_timeout: Optional[int] = None


def load_pg_dsn_from_env() -> PgDsn:
    """从环境变量加载直连 Postgres 的连接参数。

    兼容两套命名：
    - 小写：user/password/host/port/dbname（你当前 .env 是这套）
    - 大写：PGUSER/PGPASSWORD/PGHOST/PGPORT/PGDATABASE
    """

    # 允许通过 backend/.env 提供连接配置（Phase 1 开发体验）
    # 注意：load_dotenv 不会覆盖已存在的环境变量
    load_dotenv()

    user = _getenv_any("user", "PGUSER")
    password = _getenv_any("password", "PGPASSWORD")
    host = _getenv_any("host", "PGHOST")
    port = _getenv_any("port", "PGPORT")
    dbname = _getenv_any("dbname", "PGDATABASE")
    sslmode = _getenv_any("sslmode", "PGSSLMODE")
    connect_timeout = _getenv_any("connect_timeout", "PGCONNECT_TIMEOUT")

    missing = [
        k
        for k, v in [
            ("user", user),
            ("password", password),
            ("host", host),
            ("port", port),
            ("dbname", dbname),
        ]
        if not v
    ]
    if missing:
        raise RuntimeError(f"Postgres 连接配置缺失: {', '.join(missing)}")

    # 类型收敛：走到这里说明必填项均存在
    port_s = str(port)

    try:
        port_i = int(port_s)
    except Exception as e:
        raise RuntimeError(f"Postgres 端口无效: {port_s}") from e

    timeout_i: Optional[int] = None
    if connect_timeout is not None:
        try:
            timeout_i = int(connect_timeout)
        except Exception:
            timeout_i = None

    return PgDsn(
        user=str(user),
        password=str(password),
        host=str(host),
        port=port_i,
        dbname=str(dbname),
        sslmode=sslmode,
        connect_timeout=timeout_i,
    )


class PgClient:
    """最小化的 Postgres 客户端。"""

    def __init__(self, dsn: PgDsn):
        self._dsn = dsn
        self._conn = None

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _connect(self):
        params: dict[str, Any] = {
            "user": self._dsn.user,
            "password": self._dsn.password,
            "host": self._dsn.host,
            "port": self._dsn.port,
            "dbname": self._dsn.dbname,
        }
        if self._dsn.sslmode:
            params["sslmode"] = self._dsn.sslmode
        if self._dsn.connect_timeout is not None:
            params["connect_timeout"] = self._dsn.connect_timeout

        conn = psycopg2.connect(**params)
        conn.autocommit = True
        return conn

    def conn(self):
        if self._conn is None or getattr(self._conn, "closed", 1) != 0:
            self._conn = self._connect()
        return self._conn

    def execute(self, sql: str, params: Optional[tuple[Any, ...]] = None) -> None:
        with self.conn().cursor() as cur:
            cur.execute(sql, params)

    def fetchone(self, sql: str, params: Optional[tuple[Any, ...]] = None):
        with self.conn().cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def fetchall(self, sql: str, params: Optional[tuple[Any, ...]] = None):
        with self.conn().cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    # ============================================
    # WeaveAI Phase 1 写入接口
    # ============================================

    def create_session(
        self,
        session_id: str,
        profile: dict[str, Any],
        config: dict[str, Any],
    ) -> None:
        """创建 sessions 记录（幂等）。"""

        # 兼容旧列：industry 仍存在，Phase 2/3 再逐步废弃
        industry = profile.get("supply_chain") or profile.get("industry")

        sql = """
        INSERT INTO public.sessions (
          id,
          industry,
          target_market,
          supply_chain,
          seller_type,
          min_price,
          max_price,
          profile,
          debate_rounds,
          enable_followup,
          enable_websearch,
          status,
          phase,
          current_debate_round,
          started_at
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()
        )
        ON CONFLICT (id) DO NOTHING;
        """

        params = (
            session_id,
            industry,
            profile.get("target_market"),
            profile.get("supply_chain"),
            profile.get("seller_type"),
            profile.get("min_price"),
            profile.get("max_price"),
            Json(profile),
            config.get("debate_rounds"),
            config.get("enable_followup"),
            config.get("enable_websearch"),
            "running",
            "init",
            0,
        )

        self.execute(sql, params)

    def update_session_fields(self, session_id: str, fields: dict[str, Any]) -> None:
        if not fields:
            return

        # 允许更新的列白名单（防止拼 SQL 误注入）
        allowed = {
            "status",
            "phase",
            "current_debate_round",
            "synthesized_report",
            "evidence_pack",
            "memory_snapshot",
            "evidence_generated_at",
            "memory_snapshot_generated_at",
            "error_message",
            "completed_at",
            "started_at",
            "enable_followup",
            "enable_websearch",
            "debate_rounds",
            "profile",
            "target_market",
            "supply_chain",
            "seller_type",
            "min_price",
            "max_price",
        }

        sets = []
        values: list[Any] = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k in {"profile", "evidence_pack", "memory_snapshot"} and isinstance(
                v, dict
            ):
                v = Json(v)
            sets.append(f"{k} = %s")
            values.append(v)

        if not sets:
            return

        sql = f"UPDATE public.sessions SET {', '.join(sets)} WHERE id = %s"
        values.append(session_id)
        self.execute(sql, tuple(values))

    def upsert_agent_result(
        self, session_id: str, agent_name: str, fields: dict[str, Any]
    ) -> None:
        allowed = {
            "content",
            "thinking",
            "sources",
            "confidence",
            "duration_ms",
            "status",
            "error_message",
            "completed_at",
        }

        insert_cols = ["session_id", "agent_name"]
        insert_vals: list[Any] = [session_id, agent_name]

        for k, v in fields.items():
            if k in allowed:
                insert_cols.append(k)
                insert_vals.append(v)

        # 构建 update set
        update_sets = []
        for k in insert_cols:
            if k in ("session_id", "agent_name"):
                continue
            update_sets.append(f"{k} = EXCLUDED.{k}")

        sql = f"""
        INSERT INTO public.agent_results ({", ".join(insert_cols)})
        VALUES ({", ".join(["%s"] * len(insert_cols))})
        ON CONFLICT (session_id, agent_name) DO UPDATE
        SET {", ".join(update_sets)};
        """

        self.execute(sql, tuple(insert_vals))

    def insert_debate_exchange(self, session_id: str, fields: dict[str, Any]) -> None:
        allowed = {
            "round_number",
            "challenger",
            "responder",
            "challenge_content",
            "response_content",
            "followup_content",
            "debate_type",
            "revised",
        }
        cols = ["session_id"]
        vals: list[Any] = [session_id]
        for k in allowed:
            if k in fields and fields[k] is not None:
                cols.append(k)
                vals.append(fields[k])

        sql = f"""
        INSERT INTO public.debate_exchanges ({", ".join(cols)})
        VALUES ({", ".join(["%s"] * len(cols))});
        """
        self.execute(sql, tuple(vals))

    def insert_workflow_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        agent_name: Optional[str] = None,
    ) -> None:
        sql = """
        INSERT INTO public.workflow_events (session_id, event_type, agent_name, payload)
        VALUES (%s, %s, %s, %s);
        """
        self.execute(sql, (session_id, event_type, agent_name, Json(payload)))

    def insert_tool_invocation(self, fields: dict[str, Any]) -> None:
        """写入工具调用审计记录。"""
        allowed = {
            "session_id",
            "invocation_id",
            "agent_name",
            "tool_name",
            "status",
            "duration_ms",
            "input",
            "output",
            "error_message",
            "context",
            "model_name",
            "cache_hit",
            "estimated_input_tokens",
            "estimated_output_tokens",
            "estimated_cost_usd",
            "started_at",
            "finished_at",
        }
        cols: list[str] = []
        vals: list[Any] = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k in {"input", "output"} and isinstance(v, dict):
                v = Json(v)
            cols.append(k)
            vals.append(v)

        if not cols:
            return

        sql = f"""
        INSERT INTO public.tool_invocations ({", ".join(cols)})
        VALUES ({", ".join(["%s"] * len(cols))});
        """
        self.execute(sql, tuple(vals))

    # ============================================
    # Phase 1 读侧接口（status / 重连）
    # ============================================

    def get_session_full(self, session_id: str) -> Optional[dict[str, Any]]:
        """读取会话完整数据（依赖 DB 侧函数 get_session_full）。"""
        row = self.fetchone("SELECT public.get_session_full(%s)", (session_id,))
        if not row:
            return None
        data = row[0]
        return data if isinstance(data, dict) else None

    def get_session_row(self, session_id: str) -> Optional[dict[str, Any]]:
        """读取 sessions 记录（最小字段）。"""
        sql = """
        SELECT id, status, phase, current_debate_round, synthesized_report, error_message,
               created_at, started_at, completed_at, profile,
               target_market, supply_chain, seller_type, min_price, max_price,
               debate_rounds, enable_followup, enable_websearch,
               evidence_pack, memory_snapshot, evidence_generated_at, memory_snapshot_generated_at
        FROM public.sessions
        WHERE id = %s
        """
        with self.conn().cursor() as cur:
            cur.execute(sql, (session_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d.name for d in cur.description]
            return dict(zip(cols, row))

    def list_sessions_summary(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """读取会话摘要列表（用于历史会话页面）。"""
        safe_limit = max(1, min(int(limit), 100))
        safe_offset = max(0, int(offset))

        where_sql = ""
        params: list[Any] = []
        if status:
            where_sql = "WHERE status = %s"
            params.append(str(status))

        sql = f"""
        SELECT
          id,
          status,
          phase,
          current_debate_round,
          created_at,
          started_at,
          completed_at,
          profile,
          target_market,
          supply_chain,
          seller_type,
          min_price,
          max_price,
          debate_rounds,
          enable_followup,
          enable_websearch,
          error_message,
          LEFT(COALESCE(synthesized_report, ''), 260) AS report_preview,
          CASE WHEN synthesized_report IS NULL OR synthesized_report = '' THEN FALSE ELSE TRUE END AS has_report
        FROM public.sessions
        {where_sql}
        ORDER BY COALESCE(started_at, created_at) DESC
        LIMIT %s OFFSET %s
        """

        params.extend([safe_limit, safe_offset])

        with self.conn().cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    def list_agent_results(self, session_id: str) -> list[dict[str, Any]]:
        sql = """
        SELECT agent_name, status, duration_ms, confidence, error_message, content, thinking, sources,
               created_at, completed_at
        FROM public.agent_results
        WHERE session_id = %s
        ORDER BY created_at ASC
        """
        with self.conn().cursor() as cur:
            cur.execute(sql, (session_id,))
            rows = cur.fetchall()
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    def list_debate_exchanges(self, session_id: str) -> list[dict[str, Any]]:
        sql = """
        SELECT round_number, challenger, responder, revised,
               debate_type, challenge_content, response_content, followup_content,
               created_at
        FROM public.debate_exchanges
        WHERE session_id = %s
        ORDER BY round_number ASC, created_at ASC
        """
        with self.conn().cursor() as cur:
            cur.execute(sql, (session_id,))
            rows = cur.fetchall()
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    def list_workflow_events(
        self, session_id: str, limit: int = 200
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT event_type, agent_name, tool_name, node_id, payload, created_at
        FROM public.workflow_events
        WHERE session_id = %s
        ORDER BY created_at ASC
        LIMIT %s
        """
        with self.conn().cursor() as cur:
            cur.execute(sql, (session_id, limit))
            rows = cur.fetchall()
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    def list_tool_invocations(self, session_id: str) -> list[dict[str, Any]]:
        """读取工具调用记录，兼容 Phase 4 迁移前结构。"""
        sql_v4 = """
        SELECT id, session_id, invocation_id, agent_name, tool_name, status, duration_ms,
               input, output, error_message, context, model_name, cache_hit,
               estimated_input_tokens, estimated_output_tokens, estimated_cost_usd,
               started_at, finished_at, created_at
        FROM public.tool_invocations
        WHERE session_id = %s
        ORDER BY created_at ASC, id ASC
        """
        sql_legacy = """
        SELECT id, session_id, NULL::uuid AS invocation_id, agent_name, tool_name, status,
               duration_ms, input, output, error_message, NULL::text AS context,
               NULL::text AS model_name, FALSE AS cache_hit,
               NULL::int AS estimated_input_tokens,
               NULL::int AS estimated_output_tokens,
               NULL::numeric AS estimated_cost_usd,
               NULL::timestamptz AS started_at,
               NULL::timestamptz AS finished_at,
               created_at
        FROM public.tool_invocations
        WHERE session_id = %s
        ORDER BY created_at ASC, id ASC
        """

        with self.conn().cursor() as cur:
            try:
                cur.execute(sql_v4, (session_id,))
            except Exception:
                cur.execute(sql_legacy, (session_id,))
            rows = cur.fetchall()
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    def aggregate_tool_metrics(self, session_id: str) -> dict[str, Any]:
        invocations = self.list_tool_invocations(session_id)
        return aggregate_tool_metrics(invocations)


def pg_is_configured() -> bool:
    try:
        load_pg_dsn_from_env()
        return True
    except Exception:
        return False


def create_pg_client() -> PgClient:
    dsn = load_pg_dsn_from_env()
    return PgClient(dsn)
