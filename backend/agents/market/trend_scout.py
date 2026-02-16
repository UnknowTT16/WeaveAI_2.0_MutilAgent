# backend/agents/market/trend_scout.py
"""
趋势侦察员 Agent
专注于发现市场新兴趋势和机会窗口
"""

from typing import Optional, Callable

from core.config import (
    settings,
    AGENT_TREND_SCOUT,
    AGENT_MODEL_MAPPING,
    AGENT_WEBSEARCH_CONFIG,
    AGENT_THINKING_MODE,
)
from core.ark_client import ArkClientWrapper
from agents.base import BaseAgent, AgentContext


class TrendScoutAgent(BaseAgent):
    """
    趋势侦察员 Agent

    核心职责：
    - 识别新兴趋势（技术/消费/政策/竞争）
    - 评估趋势成熟度和时间窗口
    - 发现蓝海机会
    - 预警颠覆性变化

    使用模型：doubao-seed-2-0-pro-260215
    - 2.0旗舰多模态通用模型
    - 强联网搜索能力
    - 发散联想能力强
    """

    name = AGENT_TREND_SCOUT
    description = "趋势侦察员 - 发现市场新兴趋势和机会窗口"

    # 从配置获取模型和搜索设置
    model = AGENT_MODEL_MAPPING.get(AGENT_TREND_SCOUT, settings.default_model)
    use_websearch = AGENT_WEBSEARCH_CONFIG.get(AGENT_TREND_SCOUT, {}).get(
        "enabled", True
    )
    websearch_limit = AGENT_WEBSEARCH_CONFIG.get(AGENT_TREND_SCOUT, {}).get("limit", 20)

    def __init__(
        self,
        ark_client: Optional[ArkClientWrapper] = None,
        stream_writer: Optional[Callable[[dict], None]] = None,
    ):
        super().__init__(ark_client, stream_writer)
        # 获取 Thinking 模式
        self.thinking_mode = AGENT_THINKING_MODE.get(AGENT_TREND_SCOUT)

    def get_system_prompt(self, context: AgentContext) -> str:
        """获取系统提示词"""
        return """你是【趋势侦察员】，专注于发现市场新兴趋势和机会窗口。

## 核心职责
1. **识别新兴趋势**：发现正在形成或即将爆发的市场趋势
2. **评估成熟度**：判断趋势处于萌芽期、成长期还是成熟期
3. **发现蓝海机会**：找到尚未被充分开发的市场空间
4. **预警颠覆性变化**：识别可能颠覆现有格局的技术或模式

## 分析维度
- **技术趋势**：新技术、新工艺、新材料的发展和应用
- **消费趋势**：消费者偏好、行为模式、需求变化
- **政策趋势**：政府政策、行业法规、标准规范的变化
- **竞争趋势**：竞争格局、新进入者、跨界竞争

## 输出要求
1. 每个趋势必须标注：
   - 📊 可信度 (高/中/低)
   - ⏱️ 时间窗口 (预计多久形成主流)
   - 📎 数据来源 (具体的报告/新闻/数据)
2. 区分「已验证趋势」和「早期信号」
3. 给出趋势对目标行业的具体影响
4. 提供可操作的机会点建议

## 输出格式
使用 Markdown 格式，结构清晰，重点突出。每个趋势用独立章节描述。"""

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

        prompt = f"""## 分析任务
请围绕以下跨境选品/出海场景，进行趋势分析与机会识别：

### 用户画像
- **目标市场**：{target_market}
- **核心品类**：{supply_chain}
- **卖家类型**：{seller_type}
- **目标售价区间**：{price_range}

### 分析要求
1. 搜索并分析该市场/品类最新的趋势报告、行业研究、新闻与数据
2. 识别 3-6 个最值得关注的新兴趋势（含需求侧与供给侧）
3. 对每个趋势给出：驱动因素、发展阶段、时间窗口、机会点与风险
4. 明确哪些是「已验证趋势」，哪些是「早期信号」
5. 给出 2-4 条可执行建议（选品、定位、渠道、节奏）

### 特别注意
- 优先关注近 6 个月内出现的新动向
- 区分短期热点与长期趋势
- 标注信息来源，确保可验证性
- 如果发现潜在风险或颠覆性变化，务必预警"""

        # 如果是辩论模式，添加其他 Agent 的输出供参考
        if context.debate_round > 0 and context.other_agent_outputs:
            prompt += "\n\n### 参考信息\n"
            prompt += "以下是其他分析师的观点，请在分析时予以考虑：\n"
            for output in context.other_agent_outputs:
                if output.agent_name != self.name:
                    prompt += f"\n**{output.agent_name}**:\n{output.content[:500]}...\n"

        return prompt

    def post_process(self, content: str, context: AgentContext) -> str:
        """后处理：确保输出格式规范"""
        # 如果内容为空，返回默认消息
        if not content or not content.strip():
            return "## 趋势分析\n\n暂无足够数据进行趋势分析，请稍后重试。"

        # 确保有标题
        if not content.strip().startswith("#"):
            content = "## 趋势洞察报告\n\n" + content

        return content
