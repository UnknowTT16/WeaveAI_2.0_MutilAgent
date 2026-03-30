# backend/domain/agents/market/synthesizer.py
"""
综合分析师 Agent
负责整合多位专家的分析并形成最终报告
"""

from typing import Optional, Callable, List

from core.config import (
    settings,
    AGENT_SYNTHESIZER,
    AGENT_MODEL_MAPPING,
    AGENT_WEBSEARCH_CONFIG,
    AGENT_THINKING_MODE,
)
from infrastructure.llm.ark_client import ArkClientWrapper
from domain.agents.base import BaseAgent, AgentContext, AgentOutput


class SynthesizerAgent(BaseAgent):
    """
    综合分析师 Agent

    核心职责：
    - 整合四个维度的分析结果
    - 识别分析之间的关联和矛盾
    - 形成一致的综合建议
    - 标注共识和分歧

    使用模型：kimi-k2-thinking-251104
    - 超长上下文
    - 不丢失细节
    - 支持 Thinking 模式进行深度整合
    """

    name = AGENT_SYNTHESIZER
    description = "综合分析师 - 整合多维分析，形成最终报告"

    # 综合器不需要联网搜索
    model = AGENT_MODEL_MAPPING.get(AGENT_SYNTHESIZER, settings.default_model)
    use_websearch = False
    websearch_limit = 0

    def __init__(
        self,
        ark_client: Optional[ArkClientWrapper] = None,
        stream_writer: Optional[Callable[[dict], None]] = None,
    ):
        super().__init__(ark_client, stream_writer)
        self.thinking_mode = AGENT_THINKING_MODE.get(AGENT_SYNTHESIZER)

    def get_system_prompt(self, context: AgentContext) -> str:
        """获取系统提示词"""
        return """你是【综合分析师】，负责整合多位专家的分析并形成最终报告。

## 核心职责
1. **整合四个维度**：趋势洞察、竞争分析、法规审查、舆情监测
2. **识别关联和矛盾**：发现不同维度之间的相互影响和潜在冲突
3. **形成一致建议**：基于全面分析给出综合判断
4. **标注共识和分歧**：明确各分析师一致同意和存在分歧的地方

## 报告结构

### 1. 执行摘要 (Executive Summary)
- 核心结论（3-5 条）
- 关键发现
- 首要建议

### 2. 机会分析 (Opportunities)
- 市场机会（结合趋势和竞争分析）
- 差异化空间
- 进入时机评估
- 资源需求预估

### 3. 风险提示 (Risks)
- 竞争风险
- 合规风险
- 舆论风险
- 其他风险

### 4. 行动建议 (Recommendations)
- 短期行动（0-3个月）
- 中期规划（3-12个月）
- 长期战略（1年以上）
- 优先级排序

### 5. 附录
- 数据来源汇总
- 分析师观点对比
- 存在的分歧和不确定性

## 输出要求
1. 确保报告逻辑连贯、结论有据
2. 交叉验证不同分析师的观点
3. 对矛盾观点给出判断和理由
4. 所有建议必须可操作、可衡量
5. 使用专业但易懂的语言

## 质量标准
- ✅ 完整性：覆盖所有关键维度
- ✅ 一致性：结论与论据相符
- ✅ 可操作性：建议具体可执行
- ✅ 平衡性：机会与风险并重"""

    def get_user_prompt(self, context: AgentContext) -> str:
        """获取用户提示词"""
        profile = context.profile

        target_market = profile.get("target_market", "未指定市场")
        supply_chain = profile.get("supply_chain", "未指定品类")
        seller_type = profile.get("seller_type", "未指定卖家类型")
        min_price = profile.get("min_price", None)
        max_price = profile.get("max_price", None)
        price_range = (
            f"${min_price}-${max_price}"
            if (min_price is not None and max_price is not None)
            else "未指定"
        )

        prompt = f"""## 综合分析任务

请基于以下各专家的分析报告，形成一份综合的市场洞察报告。

### 业务背景
- **目标市场**：{target_market}
- **核心品类**：{supply_chain}
- **卖家类型**：{seller_type}
- **目标售价区间**：{price_range}

### 各专家分析报告
"""

        # 添加各 Agent 的输出
        for output in context.other_agent_outputs:
            agent_display_names = {
                "trend_scout": "趋势侦察员",
                "competitor_analyst": "竞争分析师",
                "regulation_checker": "法规检查员",
                "social_sentinel": "社媒哨兵",
            }
            display_name = agent_display_names.get(output.agent_name, output.agent_name)

            prompt += f"\n---\n\n### 📊 {display_name} ({output.agent_name})\n\n"
            prompt += output.content
            prompt += "\n"

        # 添加辩论记录（如果有）
        debate_history = context.shared_memory.get("debate_history", [])
        if debate_history:
            prompt += "\n---\n\n### 🗣️ 辩论记录\n\n"
            for exchange in debate_history:
                prompt += (
                    f"**{exchange.get('challenger')} → {exchange.get('responder')}**\n"
                )
                prompt += (
                    f"质疑：{(exchange.get('challenge_content') or '')[:200]}...\n"
                )
                prompt += f"回应：{(exchange.get('response_content') or '')[:200]}...\n"
                if exchange.get("followup_content"):
                    prompt += f"追问/确认：{(exchange.get('followup_content') or '')[:200]}...\n"
                if exchange.get("revised") is True:
                    prompt += "（对方表示已修订观点）\n"
                prompt += "\n"

        prompt += """
---

### 综合要求
1. 整合以上所有分析，形成统一的市场洞察报告
2. 识别不同分析之间的关联（如趋势与竞争的交叉点）
3. 指出存在的矛盾或分歧，并给出你的判断
4. 确保报告结构完整、逻辑清晰
5. 给出可操作的具体建议
"""

        return prompt

    def post_process(self, content: str, context: AgentContext) -> str:
        """后处理"""
        if not content or not content.strip():
            return "# 市场洞察综合报告\n\n报告生成失败，请稍后重试。"

        # 确保有一级标题
        if not content.strip().startswith("# "):
            content = "# 市场洞察综合报告\n\n" + content

        return content
