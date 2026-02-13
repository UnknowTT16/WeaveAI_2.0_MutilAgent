-- backend/database/migrations/003_update_views_and_functions.sql
-- WeaveAI 2.0 Phase 1: 读侧对齐（view + function），为逐步废弃旧列做准备

-- session_summary: 旧版本 view 的列名不同，直接 OR REPLACE 会失败；因此先 drop 再重建
DROP VIEW IF EXISTS public.session_summary;

-- 优先展示 profile 中的 v2 字段，旧列作为兜底
CREATE VIEW public.session_summary AS
SELECT
  s.id,
  COALESCE(s.profile->>'target_market', s.target_market) AS target_market,
  COALESCE(s.profile->>'supply_chain', s.supply_chain) AS supply_chain,
  COALESCE(s.profile->>'seller_type', s.seller_type) AS seller_type,
  s.status,
  s.phase,
  s.debate_rounds,
  s.current_debate_round,
  s.created_at,
  s.completed_at,
  COUNT(DISTINCT ar.id) AS agent_count,
  COUNT(DISTINCT de.id) AS debate_count,
  AVG(f.rating) AS avg_rating
FROM public.sessions s
LEFT JOIN public.agent_results ar ON s.id = ar.session_id
LEFT JOIN public.debate_exchanges de ON s.id = de.session_id
LEFT JOIN public.feedback f ON s.id = f.session_id
GROUP BY s.id;

-- get_session_full: 返回完整结构（含 debate_exchanges 的 followup_content/debate_type）
CREATE OR REPLACE FUNCTION public.get_session_full(p_session_id UUID)
RETURNS JSONB AS $$
DECLARE
  result JSONB;
BEGIN
  SELECT jsonb_build_object(
    'session', row_to_json(s),
    'agent_results', COALESCE(
      (
        SELECT jsonb_agg(row_to_json(ar) ORDER BY ar.created_at)
        FROM public.agent_results ar
        WHERE ar.session_id = p_session_id
      ),
      '[]'::jsonb
    ),
    'debate_exchanges', COALESCE(
      (
        SELECT jsonb_agg(row_to_json(de) ORDER BY de.round_number, de.created_at)
        FROM public.debate_exchanges de
        WHERE de.session_id = p_session_id
      ),
      '[]'::jsonb
    ),
    'feedback', (
      SELECT row_to_json(f)
      FROM public.feedback f
      WHERE f.session_id = p_session_id
      LIMIT 1
    )
  ) INTO result
  FROM public.sessions s
  WHERE s.id = p_session_id;

  RETURN result;
END;
$$ LANGUAGE plpgsql;
