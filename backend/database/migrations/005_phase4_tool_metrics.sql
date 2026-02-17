-- backend/database/migrations/005_phase4_tool_metrics.sql
-- WeaveAI 2.0 Phase 4: tool_invocations 审计与估算字段扩展

ALTER TABLE public.tool_invocations
  ADD COLUMN IF NOT EXISTS invocation_id UUID,
  ADD COLUMN IF NOT EXISTS context TEXT,
  ADD COLUMN IF NOT EXISTS model_name TEXT,
  ADD COLUMN IF NOT EXISTS cache_hit BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS estimated_input_tokens INTEGER,
  ADD COLUMN IF NOT EXISTS estimated_output_tokens INTEGER,
  ADD COLUMN IF NOT EXISTS estimated_cost_usd NUMERIC(10,6),
  ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS ux_tool_invocations_invocation_id
  ON public.tool_invocations(invocation_id);

CREATE INDEX IF NOT EXISTS idx_tool_invocations_session_agent
  ON public.tool_invocations(session_id, agent_name);
