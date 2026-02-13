-- backend/database/migrations/002_align_v2_schema.sql
-- WeaveAI 2.0 Phase 1: 对齐 v2 schema（增量变更，不删除旧列）

-- sessions: 解除旧字段约束，新增 v2 所需列
ALTER TABLE public.sessions
  ALTER COLUMN industry DROP NOT NULL;

ALTER TABLE public.sessions
  ADD COLUMN IF NOT EXISTS profile JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS supply_chain TEXT,
  ADD COLUMN IF NOT EXISTS seller_type TEXT,
  ADD COLUMN IF NOT EXISTS min_price INTEGER,
  ADD COLUMN IF NOT EXISTS max_price INTEGER,
  ADD COLUMN IF NOT EXISTS enable_followup BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS enable_websearch BOOLEAN NOT NULL DEFAULT FALSE;

-- phase: 扩展为更细的 debate 阶段（保持向后兼容）
ALTER TABLE public.sessions
  DROP CONSTRAINT IF EXISTS sessions_phase_check;

ALTER TABLE public.sessions
  ADD CONSTRAINT sessions_phase_check CHECK (
    phase = ANY (
      ARRAY[
        'init',
        'gather',
        'debate',
        'debate_peer',
        'debate_redteam',
        'synthesize',
        'complete',
        'error'
      ]
    )
  );

-- agent_results: 增加幂等唯一键（便于 upsert）
CREATE UNIQUE INDEX IF NOT EXISTS ux_agent_results_session_agent
  ON public.agent_results(session_id, agent_name);

-- debate_exchanges: 补齐 followup 与 debate_type
ALTER TABLE public.debate_exchanges
  ADD COLUMN IF NOT EXISTS debate_type TEXT,
  ADD COLUMN IF NOT EXISTS followup_content TEXT;

-- tool_invocations: Phase 1 先建表，Phase 4 再做脱敏/审计增强
CREATE TABLE IF NOT EXISTS public.tool_invocations (
  id BIGSERIAL PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
  agent_name TEXT,
  tool_name TEXT NOT NULL,
  status TEXT DEFAULT 'completed',
  duration_ms INTEGER,
  input JSONB DEFAULT '{}'::jsonb,
  output JSONB DEFAULT '{}'::jsonb,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_invocations_session
  ON public.tool_invocations(session_id);

CREATE INDEX IF NOT EXISTS idx_tool_invocations_tool
  ON public.tool_invocations(tool_name);
