# backend/agents/market/regulation_checker.py
"""
法规检查员 Agent
专注于合规风险审查和政策解读
"""

from typing import Optional, Callable

from core.config import (
    settings,
    AGENT_REGULATION_CHECKER,
    AGENT_MODEL_MAPPING,
    AGENT_WEBSEARCH_CONFIG,
    AGENT_THINKING_MODE,
)
from core.ark_client import ArkClientWrapper
from agents.base import BaseAgent, AgentContext


class RegulationCheckerAgent(BaseAgent):
    """
    法规检查员 Agent

    核心职责：
    - 识别适用的法规要求
    - 评估合规成本
    - 预警政策变化
    - 提供合规路径

    使用模型：kimi-k2-thinking-251104
    - 长文档阅读能力强
    - 支持 Thinking 模式，适合复杂法规分析
    - 细节把控能力强
    """

    name = AGENT_REGULATION_CHECKER
    description = "法规检查员 - 合规风险审查和政策解读"

    # 从配置获取模型和搜索设置
    model = AGENT_MODEL_MAPPING.get(AGENT_REGULATION_CHECKER, settings.default_model)
    use_websearch = AGENT_WEBSEARCH_CONFIG.get(AGENT_REGULATION_CHECKER, {}).get(
        "enabled", True
    )
    websearch_limit = AGENT_WEBSEARCH_CONFIG.get(AGENT_REGULATION_CHECKER, {}).get(
        "limit", 15
    )

    def __init__(
        self,
        ark_client: Optional[ArkClientWrapper] = None,
        stream_writer: Optional[Callable[[dict], None]] = None,
    ):
        super().__init__(ark_client, stream_writer)
        self.thinking_mode = AGENT_THINKING_MODE.get(AGENT_REGULATION_CHECKER)

    def get_system_prompt(self, context: AgentContext) -> str:
        """获取系统提示词"""
        return """你是【法规检查员】，专注于合规风险审查和政策解读。

## 核心职责
1. **识别法规要求**：梳理适用的法律法规、行业标准、监管要求
2. **评估合规成本**：分析达到合规所需的时间、资金、资源投入
3. **预警政策变化**：跟踪政策动向，预判未来监管趋势
4. **提供合规路径**：给出切实可行的合规方案和时间表

## 审查范围
1. **行业准入**：资质证照、许可审批、市场准入条件
2. **产品合规**：产品标准、质量认证、标签标识、安全要求
3. **跨境合规**：进出口政策、海外市场准入、国际标准
4. **数据合规**：个人信息保护、数据出境、网络安全

## 输出要求
1. 必须引用具体法规条款：
   - 📜 法规名称和条款号
   - 📅 生效日期和过渡期
   - 🔗 官方文件链接（如有）
2. 区分「强制性要求」和「建议性标准」
3. 评估违规后果的严重程度
4. 给出合规优先级排序和时间规划

## 风险等级标识
- 🔴 高风险：必须立即处理，违规后果严重
- 🟡 中风险：需要关注，限期整改
- 🟢 低风险：建议遵循，有改进空间

## 输出格式
使用 Markdown 格式，按法规类别和风险等级组织内容。"""

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
请针对以下业务场景，进行全面的法规合规审查：

### 用户画像
- **目标市场**：{target_market}
- **核心品类**：{supply_chain}
- **卖家类型**：{seller_type}
- **目标售价区间**：{price_range}

### 分析要求
1. 梳理该业务涉及的主要法规框架
2. 识别核心合规要求（市场准入、产品标准/认证、标签与说明、税费与关务等）
3. 评估各项合规要求的紧迫性和成本
4. 关注近期政策变化和未来趋势
5. 给出合规路线图和优先级建议

### 重点关注
- 最新发布或即将生效的法规（近 12 个月）
- 行业监管趋严的领域
- 可能影响商业模式的政策变化
 - 进口/跨境业务的特殊合规要求（如适用）

### 输出期望
- 按风险等级排序
- 给出可执行的合规建议
- 预估合规所需的资源投入"""

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
            return "## 法规合规审查\n\n暂无足够数据进行法规审查，请稍后重试。"

        if not content.strip().startswith("#"):
            content = "## 法规合规审查报告\n\n" + content

        return content
