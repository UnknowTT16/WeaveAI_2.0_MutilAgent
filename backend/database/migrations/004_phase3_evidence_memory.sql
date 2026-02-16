-- backend/database/migrations/004_phase3_evidence_memory.sql
-- WeaveAI 2.0 Phase 3: 证据包与轻量记忆快照

-- sessions 增加证据链与记忆快照字段
ALTER TABLE public.sessions
  ADD COLUMN IF NOT EXISTS evidence_pack JSONB,
  ADD COLUMN IF NOT EXISTS memory_snapshot JSONB,
  ADD COLUMN IF NOT EXISTS evidence_generated_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS memory_snapshot_generated_at TIMESTAMPTZ;

-- 便于后续按“是否已生成”快速筛选（Phase 3 回放/验收场景）
CREATE INDEX IF NOT EXISTS idx_sessions_evidence_generated_at
  ON public.sessions(evidence_generated_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_sessions_memory_snapshot_generated_at
  ON public.sessions(memory_snapshot_generated_at DESC NULLS LAST);

