# backend/agents/debate/challenger.py
"""
红队审查官 Agent
对分析报告进行批判性审查和质疑
"""

from typing import Optional, Callable, Literal

from core.config import (
    settings, 
    AGENT_DEBATE_CHALLENGER,
    AGENT_MODEL_MAPPING,
    AGENT_WEBSEARCH_CONFIG,
    AGENT_THINKING_MODE,
)
from core.ark_client import ArkClientWrapper
from agents.base import BaseAgent, AgentContext, AgentOutput


class ChallengerAgent(BaseAgent):
    """
    红队审查官 Agent
    
    核心职责：
    - 对分析报告进行批判性审查
    - 质疑数据可靠性和逻辑严密性
    - 检测覆盖完整性和潜在偏见
    - 提出改进建议
    
    使用模型：deepseek-v3-2-251201
    - 批判性思维能力强
    - 逻辑反驳能力强
    - 适合结构化质疑
    """
    
    name = AGENT_DEBATE_CHALLENGER
    description = "红队审查官 - 批判性审查和质疑"
    
    # 辩论质疑不需要联网搜索
    model = AGENT_MODEL_MAPPING.get(AGENT_DEBATE_CHALLENGER, settings.default_model)
    use_websearch = False
    websearch_limit = 0
    
    def __init__(
        self,
        ark_client: Optional[ArkClientWrapper] = None,
        stream_writer: Optional[Callable[[dict], None]] = None,
        challenge_mode: Literal["peer", "redteam"] = "redteam"
    ):
        """
        初始化红队审查官
        
        Args:
            ark_client: Ark 客户端
            stream_writer: 流式写入器
            challenge_mode: 质疑模式
                - "peer": 同行评审 (Worker 之间互相质疑)
                - "redteam": 红队审查 (DeepSeek 审查所有 Worker)
        """
        super().__init__(ark_client, stream_writer)
        self.thinking_mode = AGENT_THINKING_MODE.get(AGENT_DEBATE_CHALLENGER)
        self.challenge_mode = challenge_mode
        
        # 动态设置的目标 Agent
        self._target_agent: Optional[str] = None
        self._target_content: Optional[str] = None
        self._challenger_agent: Optional[str] = None
    
    def set_challenge_context(
        self,
        target_agent: str,
        target_content: str,
        challenger_agent: Optional[str] = None
    ):
        """
        设置质疑上下文
        
        Args:
            target_agent: 被质疑的 Agent 名称
            target_content: 被质疑的内容
            challenger_agent: 质疑方 Agent 名称 (peer 模式下使用)
        """
        self._target_agent = target_agent
        self._target_content = target_content
        self._challenger_agent = challenger_agent
    
    def get_system_prompt(self, context: AgentContext) -> str:
        """获取系统提示词"""
        if self.challenge_mode == "peer":
            return self._get_peer_system_prompt()
        else:
            return self._get_redteam_system_prompt()
    
    def _get_peer_system_prompt(self) -> str:
        """同行评审系统提示词"""
        return """你是一位【同行评审员】，正在对另一位分析师的报告进行专业审查。

## 审查原则
1. **建设性批评**：指出问题的同时给出改进建议
2. **专业视角**：从你的专业领域出发进行审查
3. **互补验证**：检查分析是否与你的发现相互印证或矛盾
4. **逻辑严谨**：关注论证过程的严密性

## 质疑维度
1. **数据可靠性**：数据来源是否可靠？是否有更新数据？样本是否具有代表性？
2. **逻辑严密性**：推理过程是否严密？是否存在逻辑跳跃？结论是否合理推导？
3. **覆盖完整性**：是否遗漏重要维度？是否考虑了边缘情况？
4. **偏见检测**：是否存在确认偏误？是否过度依赖单一来源？

## 输出格式
针对每个质疑点：
```
### 🔍 质疑点 X：[简短标题]

**原始观点**：[引用对方观点]

**质疑理由**：[为什么这个观点可能有问题]

**补充建议**：[建议如何改进或补充]
```

## 注意事项
- 保持专业和尊重的态度
- 优先关注高影响力的问题
- 给出 2-4 个最关键的质疑点
- 如果认同某些观点，也可以表示支持"""

    def _get_redteam_system_prompt(self) -> str:
        """红队审查系统提示词"""
        return """你是【红队审查官】，职责是对分析报告进行严格的批判性审查。

## 核心职责
作为"魔鬼代言人"，你的任务是：
1. 找出分析中的漏洞和弱点
2. 质疑未经充分验证的假设
3. 挑战过于乐观或悲观的结论
4. 识别可能被忽视的风险

## 质疑框架

### 1. 数据可靠性审查
- 数据来源的权威性和时效性
- 样本的代表性和覆盖范围
- 是否存在数据造假或误导的可能

### 2. 逻辑严密性审查
- 论证链条是否完整
- 因果关系是否成立
- 是否存在逻辑谬误（滑坡谬误、稻草人谬误等）

### 3. 覆盖完整性审查
- 是否遗漏关键变量
- 是否考虑了极端情况
- 是否有盲点或死角

### 4. 偏见检测
- 确认偏误：只看到支持结论的证据
- 幸存者偏差：只分析成功案例
- 锚定效应：过度依赖初始信息

## 输出格式
```markdown
## 🔴 红队审查报告

### 审查对象
[被审查的 Agent 和报告摘要]

### 关键质疑

#### 质疑 1：[标题]
- **原始观点**：[引用]
- **质疑点**：[具体问题]
- **风险等级**：高/中/低
- **建议**：[如何改进]

...

### 总体评价
[整体可靠性评估和优先改进建议]
```

## 质疑原则
- 🎯 精准：针对具体观点，避免泛泛而谈
- 📊 有据：基于逻辑和事实进行质疑
- 🔨 有力：指出真正的问题，不是吹毛求疵
- 💡 建设：每个质疑都要有改进建议"""

    def get_user_prompt(self, context: AgentContext) -> str:
        """获取用户提示词"""
        target_agent = self._target_agent or "未知分析师"
        target_content = self._target_content or "无内容"
        
        agent_display_names = {
            "trend_scout": "趋势侦察员",
            "competitor_analyst": "竞争分析师", 
            "regulation_checker": "法规检查员",
            "social_sentinel": "社媒哨兵",
        }
        
        target_display = agent_display_names.get(target_agent, target_agent)
        
        if self.challenge_mode == "peer":
            challenger_display = agent_display_names.get(
                self._challenger_agent, self._challenger_agent or "同行评审员"
            )
            
            prompt = f"""## 同行评审任务

你是 **{challenger_display}**，现在需要对 **{target_display}** 的分析报告进行专业审查。

### 被审查报告

{target_content}

### 审查要求
1. 从你的专业视角出发，审查这份报告
2. 找出 2-4 个最值得关注的问题
3. 指出可能与你的分析存在矛盾的地方
4. 给出具体的改进建议

请开始审查并提出你的质疑："""
        
        else:  # redteam mode
            prompt = f"""## 红队审查任务

请对以下 **{target_display}** 的分析报告进行严格的批判性审查。

### 被审查报告

{target_content}

### 审查要求
1. 从数据可靠性、逻辑严密性、覆盖完整性、偏见检测四个维度进行审查
2. 找出 3-5 个最关键的问题
3. 对每个问题评估风险等级
4. 给出具体的改进建议

请开始红队审查："""
        
        return prompt
    
    def post_process(self, content: str, context: AgentContext) -> str:
        """后处理"""
        if not content or not content.strip():
            return "## 审查报告\n\n暂无法完成审查，请稍后重试。"
        
        return content


class ResponderMixin:
    """
    回应质疑的 Mixin
    
    为 Worker Agent 添加回应质疑的能力
    """
    
    def get_response_prompt(self, challenge_content: str, context: AgentContext) -> str:
        """
        生成回应质疑的提示词
        
        Args:
            challenge_content: 质疑内容
            context: Agent 上下文
        """
        return f"""## 回应质疑

你收到了以下质疑，请认真回应：

### 质疑内容
{challenge_content}

### 回应要求
1. **承认问题**：如果质疑有道理，坦诚承认并说明如何改进
2. **澄清误解**：如果质疑存在误解，礼貌地澄清
3. **补充论据**：如果有额外证据支持你的观点，请补充
4. **修正结论**：如果需要修改结论，明确说明修改内容

### 回应格式
```markdown
## 📝 回应报告

### 对于 [质疑点 X]
**回应**：[你的回应]
**修订**：[如有修改，说明具体修改内容]

...

### 修订总结
[总结哪些观点被修正，哪些被坚持]
```

请开始回应："""
    
    def get_followup_prompt(
        self, 
        original_challenge: str, 
        response_content: str, 
        context: AgentContext
    ) -> str:
        """
        生成二次追问/确认的提示词
        
        Args:
            original_challenge: 原始质疑
            response_content: 对方的回应
            context: Agent 上下文
        """
        return f"""## 二次确认

你之前提出了质疑，对方已经回应。请评估回应是否充分。

### 你的原始质疑
{original_challenge}

### 对方的回应
{response_content}

### 确认要求
1. 如果回应充分，表示接受并结束讨论
2. 如果回应不充分，提出追问（限 1-2 个点）
3. 如果发现新问题，简要指出

### 回应格式
```markdown
## ✅ 确认/追问

### 对于 [质疑点]
**评估**：接受 / 部分接受 / 需要追问
**理由**：[简要说明]
[如需追问，补充追问内容]

### 结论
[是否结束讨论，还是需要进一步澄清]
```

请进行确认："""
