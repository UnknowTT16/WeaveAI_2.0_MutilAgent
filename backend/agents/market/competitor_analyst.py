# backend/agents/market/competitor_analyst.py
"""
竞争分析师 Agent
专注于竞争格局分析和竞品研究
"""

from typing import Optional, Callable

from core.config import (
    settings,
    AGENT_COMPETITOR_ANALYST,
    AGENT_MODEL_MAPPING,
    AGENT_WEBSEARCH_CONFIG,
    AGENT_THINKING_MODE,
)
from core.ark_client import ArkClientWrapper
from agents.base import BaseAgent, AgentContext


class CompetitorAnalystAgent(BaseAgent):
    """
    竞争分析师 Agent

    核心职责：
    - 绘制竞争格局图谱
    - 剖析竞品策略和优劣势
    - 识别差异化机会
    - 评估进入壁垒

    使用模型：deepseek-v3-2-251201
    - 逻辑推理能力强
    - 结构化分析能力强
    - 适合对比分析和策略推演
    """

    name = AGENT_COMPETITOR_ANALYST
    description = "竞争分析师 - 竞争格局分析和竞品研究"

    # 从配置获取模型和搜索设置
    model = AGENT_MODEL_MAPPING.get(AGENT_COMPETITOR_ANALYST, settings.default_model)
    use_websearch = AGENT_WEBSEARCH_CONFIG.get(AGENT_COMPETITOR_ANALYST, {}).get(
        "enabled", True
    )
    websearch_limit = AGENT_WEBSEARCH_CONFIG.get(AGENT_COMPETITOR_ANALYST, {}).get(
        "limit", 15
    )

    def __init__(
        self,
        ark_client: Optional[ArkClientWrapper] = None,
        stream_writer: Optional[Callable[[dict], None]] = None,
    ):
        super().__init__(ark_client, stream_writer)
        self.thinking_mode = AGENT_THINKING_MODE.get(AGENT_COMPETITOR_ANALYST)

    def get_system_prompt(self, context: AgentContext) -> str:
        """获取系统提示词"""
        return """你是【竞争分析师】，专注于竞争格局分析和竞品研究。

## 核心职责
1. **绘制竞争格局**：梳理市场主要玩家、市场份额、竞争态势
2. **剖析竞品策略**：分析竞争对手的产品策略、定价策略、营销策略
3. **识别差异化机会**：找到竞品的薄弱点和市场空白
4. **评估进入壁垒**：分析技术壁垒、资金壁垒、品牌壁垒、渠道壁垒

## 分析框架
1. **竞品矩阵**：按关键维度对比主要竞品
2. **SWOT 分析**：优势、劣势、机会、威胁
3. **竞争策略分析**：成本领先、差异化、聚焦策略
4. **动态跟踪**：竞品最新动向、融资、产品发布、战略调整

## 输出要求
1. 使用表格进行结构化对比
2. 每个竞品分析必须包含：
   - 🏢 公司背景（规模、融资、核心团队）
   - 📦 产品矩阵（主要产品线、定价）
   - 💪 核心优势（技术、渠道、品牌）
   - ⚠️ 主要劣势（弱点、缺陷）
   - 📈 近期动态（最新消息、战略动向）
3. 给出避开强敌和弯道超车的具体建议

## 输出格式
使用 Markdown 格式，善用表格、列表进行结构化呈现。"""

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

        competitors = profile.get("known_competitors", [])
        competitors_text = (
            "、".join(competitors) if competitors else "（请你自行识别 Top 竞品）"
        )

        prompt = f"""## 分析任务
请针对以下业务场景，进行全面的竞争分析：

### 用户画像
- **目标市场**：{target_market}
- **核心品类**：{supply_chain}
- **卖家类型**：{seller_type}
- **目标售价区间**：{price_range}
- **已知竞品**：{competitors_text}

### 分析要求
1. 识别该领域的 Top 5-10 竞争对手（含直接竞争和间接竞争）
2. 构建竞品对比矩阵，从产品、价格、渠道、技术等维度对比
3. 对每个主要竞品进行 SWOT 分析
4. 分析竞争格局的演变趋势
5. 识别市场空白和差异化机会
6. 给出竞争策略建议

### 重点关注
- 竞品的最新动向（近 3-6 个月）
- 竞品的融资情况和资金实力
- 竞品的技术壁垒和专利布局
- 潜在的新进入者和跨界竞争者"""

        # 辩论模式下添加其他 Agent 输出
        if context.debate_round > 0 and context.other_agent_outputs:
            prompt += "\n\n### 参考信息\n"
            for output in context.other_agent_outputs:
                if output.agent_name != self.name:
                    prompt += f"\n**{output.agent_name}**:\n{output.content[:500]}...\n"

        return prompt

    def post_process(self, content: str, context: AgentContext) -> str:
        """后处理"""
        if not content or not content.strip():
            return "## 竞争分析\n\n暂无足够数据进行竞争分析，请稍后重试。"

        if not content.strip().startswith("#"):
            content = "## 竞争格局分析报告\n\n" + content

        return content
