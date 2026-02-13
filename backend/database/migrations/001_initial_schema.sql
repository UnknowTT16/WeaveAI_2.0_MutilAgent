-- backend/database/migrations/001_initial_schema.sql
-- WeaveAI 2.0 初始数据表结构
-- 执行方式: 在 Supabase SQL Editor 中运行

-- ============================================
-- 1. 会话表 (sessions)
-- ============================================
CREATE TABLE IF NOT EXISTS public.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- 用户画像
    industry TEXT NOT NULL,
    company_name TEXT,
    company_size TEXT,
    target_market TEXT,
    analysis_focus TEXT[] DEFAULT '{}',
    custom_requirements TEXT,
    
    -- 工作流配置
    debate_rounds INTEGER DEFAULT 2,
    model_name TEXT DEFAULT 'doubao-seed-1-6-250615',
    
    -- 状态
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    phase TEXT DEFAULT 'init' CHECK (phase IN ('init', 'gather', 'debate', 'synthesize', 'complete', 'error')),
    current_debate_round INTEGER DEFAULT 0,
    
    -- 最终输出
    synthesized_report TEXT,
    
    -- 错误信息
    error_message TEXT,
    
    -- 时间戳
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_sessions_status ON public.sessions(status);
CREATE INDEX idx_sessions_created_at ON public.sessions(created_at DESC);

-- 更新触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_sessions_updated_at
    BEFORE UPDATE ON public.sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================
-- 2. Agent 执行结果表 (agent_results)
-- ============================================
CREATE TABLE IF NOT EXISTS public.agent_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    
    -- Agent 信息
    agent_name TEXT NOT NULL,
    
    -- 输出内容
    content TEXT,
    thinking TEXT,
    sources TEXT[] DEFAULT '{}',
    
    -- 元数据
    confidence DECIMAL(3, 2) DEFAULT 1.0,
    duration_ms INTEGER,
    
    -- 状态
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    error_message TEXT,
    
    -- 时间戳
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- 索引
CREATE INDEX idx_agent_results_session ON public.agent_results(session_id);
CREATE INDEX idx_agent_results_agent ON public.agent_results(agent_name);


-- ============================================
-- 3. 辩论交换表 (debate_exchanges)
-- ============================================
CREATE TABLE IF NOT EXISTS public.debate_exchanges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    
    -- 辩论轮次
    round_number INTEGER NOT NULL,
    
    -- 参与者
    challenger TEXT NOT NULL,
    responder TEXT NOT NULL,
    
    -- 内容
    challenge_content TEXT,
    response_content TEXT,
    
    -- 是否修正观点
    revised BOOLEAN DEFAULT FALSE,
    
    -- 时间戳
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_debate_exchanges_session ON public.debate_exchanges(session_id);
CREATE INDEX idx_debate_exchanges_round ON public.debate_exchanges(round_number);


-- ============================================
-- 4. 工作流事件日志表 (workflow_events)
-- ============================================
CREATE TABLE IF NOT EXISTS public.workflow_events (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    
    -- 事件类型
    event_type TEXT NOT NULL,
    
    -- 关联实体
    agent_name TEXT,
    tool_name TEXT,
    node_id TEXT,
    
    -- 事件数据
    payload JSONB DEFAULT '{}',
    
    -- 时间戳
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_workflow_events_session ON public.workflow_events(session_id);
CREATE INDEX idx_workflow_events_type ON public.workflow_events(event_type);
CREATE INDEX idx_workflow_events_created ON public.workflow_events(created_at);


-- ============================================
-- 5. 用户反馈表 (feedback)
-- ============================================
CREATE TABLE IF NOT EXISTS public.feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    
    -- 评分 (1-5)
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    
    -- 反馈内容
    comment TEXT,
    
    -- 细分评价
    accuracy_rating INTEGER CHECK (accuracy_rating >= 1 AND accuracy_rating <= 5),
    completeness_rating INTEGER CHECK (completeness_rating >= 1 AND completeness_rating <= 5),
    usefulness_rating INTEGER CHECK (usefulness_rating >= 1 AND usefulness_rating <= 5),
    
    -- 时间戳
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_feedback_session ON public.feedback(session_id);


-- ============================================
-- 6. RLS (Row Level Security) 策略
-- ============================================
-- 注意: 生产环境需要启用 RLS 并配置适当策略
-- 当前开发阶段暂时关闭

ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.debate_exchanges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workflow_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feedback ENABLE ROW LEVEL SECURITY;

-- 开发阶段：允许所有操作
CREATE POLICY "Allow all for development" ON public.sessions FOR ALL USING (true);
CREATE POLICY "Allow all for development" ON public.agent_results FOR ALL USING (true);
CREATE POLICY "Allow all for development" ON public.debate_exchanges FOR ALL USING (true);
CREATE POLICY "Allow all for development" ON public.workflow_events FOR ALL USING (true);
CREATE POLICY "Allow all for development" ON public.feedback FOR ALL USING (true);


-- ============================================
-- 7. 视图：会话摘要
-- ============================================
CREATE OR REPLACE VIEW public.session_summary AS
SELECT 
    s.id,
    s.industry,
    s.company_name,
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


-- ============================================
-- 8. 函数：获取会话完整数据
-- ============================================
CREATE OR REPLACE FUNCTION public.get_session_full(p_session_id UUID)
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'session', row_to_json(s),
        'agent_results', COALESCE(
            (SELECT jsonb_agg(row_to_json(ar)) FROM public.agent_results ar WHERE ar.session_id = p_session_id),
            '[]'::jsonb
        ),
        'debate_exchanges', COALESCE(
            (SELECT jsonb_agg(row_to_json(de) ORDER BY de.round_number) FROM public.debate_exchanges de WHERE de.session_id = p_session_id),
            '[]'::jsonb
        ),
        'feedback', (SELECT row_to_json(f) FROM public.feedback f WHERE f.session_id = p_session_id LIMIT 1)
    ) INTO result
    FROM public.sessions s
    WHERE s.id = p_session_id;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- 注释
-- ============================================
COMMENT ON TABLE public.sessions IS '分析会话表，存储用户输入和工作流状态';
COMMENT ON TABLE public.agent_results IS 'Agent 执行结果表，存储每个 Agent 的输出';
COMMENT ON TABLE public.debate_exchanges IS '辩论交换表，存储 Agent 之间的质疑与回应';
COMMENT ON TABLE public.workflow_events IS '工作流事件日志表，用于调试和追踪';
COMMENT ON TABLE public.feedback IS '用户反馈表';
