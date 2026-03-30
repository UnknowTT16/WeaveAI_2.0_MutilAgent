# backend/domain/agents/market/social_sentinel.py
"""
社媒哨兵 Agent
专注于舆情监测和消费者洞察
"""

from typing import Optional, Callable

from core.config import (
    settings,
    AGENT_SOCIAL_SENTINEL,
    AGENT_MODEL_MAPPING,
    AGENT_WEBSEARCH_CONFIG,
    AGENT_THINKING_MODE,
)
from infrastructure.llm.ark_client import ArkClientWrapper
from domain.agents.base import BaseAgent, AgentContext


class SocialSentinelAgent(BaseAgent):
    """
    社媒哨兵 Agent

    核心职责：
    - 捕捉舆论热点
    - 分析口碑评价
    - 识别 KOL 分布
    - 预警舆论风险

    使用模型：doubao-seed-2-0-pro-260215
    - 2.0旗舰多模态通用模型
    - 中文语感强 + 情感理解能力强
    - 适合社交媒体内容分析
    """

    name = AGENT_SOCIAL_SENTINEL
    description = "社媒哨兵 - 舆情监测和消费者洞察"

    # 从配置获取模型和搜索设置
    model = AGENT_MODEL_MAPPING.get(AGENT_SOCIAL_SENTINEL, settings.default_model)
    use_websearch = AGENT_WEBSEARCH_CONFIG.get(AGENT_SOCIAL_SENTINEL, {}).get(
        "enabled", True
    )
    websearch_limit = AGENT_WEBSEARCH_CONFIG.get(AGENT_SOCIAL_SENTINEL, {}).get(
        "limit", 20
    )

    def __init__(
        self,
        ark_client: Optional[ArkClientWrapper] = None,
        stream_writer: Optional[Callable[[dict], None]] = None,
    ):
        super().__init__(ark_client, stream_writer)
        self.thinking_mode = AGENT_THINKING_MODE.get(AGENT_SOCIAL_SENTINEL)

    def get_system_prompt(self, context: AgentContext) -> str:
        """获取系统提示词"""
        return """你是【社媒哨兵】，专注于舆情监测和消费者洞察。

## 核心职责
1. **捕捉舆论热点**：监测社交媒体、论坛、资讯平台的热门话题
2. **分析口碑评价**：解读用户评价、吐槽、推荐的深层含义
3. **识别 KOL 分布**：梳理行业意见领袖和传播节点
4. **预警舆论风险**：发现负面舆情苗头，评估传播风险

## 监测维度
1. **舆情热度**：话题讨论量、传播速度、情感倾向
2. **消费者痛点**：用户抱怨、需求缺口、改进建议
3. **口碑分析**：好评原因、差评原因、推荐动机
4. **传播生态**：主要传播渠道、KOL 影响力、用户画像

## 输出要求
1. 每条舆情/洞察必须标注：
   - 📍 来源平台（微博/小红书/抖音/知乎/贴吧等）
   - 📅 时间范围
   - 📊 情感倾向（正面/中性/负面）
   - 🔥 热度指标（如适用）
2. 区分「真实用户声音」和「营销/水军内容」
3. 提取有代表性的原始评论/观点
4. 给出可操作的营销/公关建议

## 情感标识
- 😊 正面：好评、推荐、赞扬
- 😐 中性：客观描述、提问、讨论
- 😠 负面：吐槽、投诉、批评

## 输出格式
使用 Markdown 格式，按话题/维度组织内容，穿插真实用户评论作为佐证。"""

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

        brand_name = profile.get("brand_name", "")
        target_audience = profile.get("target_audience", "未指定")
        competitors = profile.get("known_competitors", [])

        brand_text = f"- **品牌名称**：{brand_name}\n" if brand_name else ""
        competitors_text = "、".join(competitors) if competitors else "（请你自行识别）"

        prompt = f"""## 分析任务
请针对以下业务场景，进行全面的舆情分析和消费者洞察：

### 用户画像
- **目标市场**：{target_market}
- **核心品类**：{supply_chain}
- **卖家类型**：{seller_type}
- **目标售价区间**：{price_range}
{brand_text}- **目标用户**：{target_audience}
- **主要竞品**：{competitors_text}

### 分析要求
1. 在目标市场的主流平台上，搜索与该品类相关的近期讨论热点（优先近 6 个月）
2. 分析消费者的核心诉求、痛点与购买阻力
3. 收集有代表性的用户评价（正面与负面），并解释其背后的真实需求
4. 识别行业 KOL/媒体/社区节点，给出可能的传播切入点
5. 发现潜在的舆论风险点（合规、质量、售后、宣传口径等）
6. 给出可落地的营销与公关建议（可按渠道拆解）

### 重点关注平台
请根据“目标市场”选择最相关的 3-6 个平台（含社媒、论坛、内容站点与电商评论）。
输出时务必标注具体平台与时间范围。

### 输出期望
- 提供真实的用户声音样本（可引用原话）
- 区分核心需求与边缘需求
- 给出可执行的营销洞察与风险预案"""

        # 辩论模式
        if context.debate_round > 0 and context.other_agent_outputs:
            prompt += "\n\n### 参考信息\n"
            for output in context.other_agent_outputs:
                if output.agent_name != self.name:
                    prompt += f"\n**{output.agent_name}**:\n{output.content[:500]}...\n"

        return prompt

    def post_process(self, content: str, context: AgentContext) -> str:
        """后处理"""
        if not content or not content.strip():
            return "## 舆情分析\n\n暂无足够数据进行舆情分析，请稍后重试。"

        if not content.strip().startswith("#"):
            content = "## 社媒舆情洞察报告\n\n" + content

        return content
