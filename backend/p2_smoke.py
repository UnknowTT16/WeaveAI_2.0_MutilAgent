"""Phase 2 本地冒烟验证脚本。"""

import sys
import types

# 为离线环境注入最小 Ark 依赖桩，避免导入失败。
fake_ark_module = types.ModuleType("volcenginesdkarkruntime")


class Ark:  # noqa: D401
    """占位 Ark 类，仅用于通过导入阶段。"""


fake_ark_module.Ark = Ark
sys.modules.setdefault("volcenginesdkarkruntime", fake_ark_module)

from core.ark_client import StreamEvent, StreamEventType
from core.graph_engine import create_market_insight_engine


class FakeArkClient:
    """用于离线验证的假客户端。"""

    def __init__(self, name: str, always_fail: bool = False):
        self.name = name
        self.always_fail = always_fail

    def create_response_stream_v2(self, **kwargs):
        if self.always_fail:
            raise RuntimeError(f"{self.name} hard failure")
        yield StreamEvent(type=StreamEventType.OUTPUT_DELTA, content=f"{self.name}-ok")


class FakeAgent:
    """用于替代真实 Agent 的最小实现。"""

    def __init__(self, name: str, always_fail: bool = False):
        self.name = name
        self.model = "fake-model"
        self.use_websearch = False
        self.websearch_limit = 0
        self.thinking_mode = None
        self.ark_client = FakeArkClient(name=name, always_fail=always_fail)

    def get_system_prompt(self, context):
        return "system"

    def get_user_prompt(self, context):
        return "user"

    def post_process(self, content, context):
        return content


def validate_round_routing() -> None:
    """验证 debate_rounds=0/1/2 的路由与交换条数。"""
    for rounds in (0, 1, 2):
        engine = create_market_insight_engine(
            agent_factory=None,
            debate_rounds=rounds,
            enable_followup=True,
            use_checkpointer=False,
        )
        result = engine.invoke(
            {
                "user_profile": {
                    "target_market": "Germany",
                    "supply_chain": "Consumer Electronics",
                },
                "debate_rounds": rounds,
            }
        )
        print(
            f"rounds={rounds}, debate_exchanges={len(result.get('debate_exchanges', []))}"
        )


def validate_retry_degrade_partial() -> None:
    """验证 degrade_mode=partial 在失败场景的可恢复性。"""
    cache: dict[str, FakeAgent] = {}

    def factory(agent_name: str) -> FakeAgent:
        if agent_name not in cache:
            cache[agent_name] = FakeAgent(
                name=agent_name,
                always_fail=agent_name == "trend_scout",
            )
        return cache[agent_name]

    engine = create_market_insight_engine(
        agent_factory=factory,
        debate_rounds=0,
        enable_followup=False,
        retry_max_attempts=2,
        retry_backoff_ms=0,
        degrade_mode="partial",
        use_checkpointer=False,
    )

    events = list(
        engine.stream(
            {
                "user_profile": {
                    "target_market": "Germany",
                    "supply_chain": "Consumer Electronics",
                },
                "debate_rounds": 0,
                "retry_max_attempts": 2,
                "retry_backoff_ms": 0,
                "degrade_mode": "partial",
            }
        )
    )

    retry_count = sum(1 for event in events if event.get("event") == "retry")
    has_agent_error = any(
        event.get("event") == "agent_error" and event.get("agent") == "trend_scout"
        for event in events
    )
    has_orchestrator_end = any(
        event.get("event") == "orchestrator_end" for event in events
    )
    print(
        "partial "
        f"retry_count={retry_count} "
        f"has_agent_error={has_agent_error} "
        f"has_orchestrator_end={has_orchestrator_end}"
    )


def validate_retry_degrade_fail() -> None:
    """验证 degrade_mode=fail 在失败场景会终止流程。"""
    cache: dict[str, FakeAgent] = {}

    def factory(agent_name: str) -> FakeAgent:
        if agent_name not in cache:
            cache[agent_name] = FakeAgent(
                name=agent_name,
                always_fail=agent_name == "trend_scout",
            )
        return cache[agent_name]

    engine = create_market_insight_engine(
        agent_factory=factory,
        debate_rounds=0,
        enable_followup=False,
        retry_max_attempts=2,
        retry_backoff_ms=0,
        degrade_mode="fail",
        use_checkpointer=False,
    )

    events = list(
        engine.stream(
            {
                "user_profile": {
                    "target_market": "Germany",
                    "supply_chain": "Consumer Electronics",
                },
                "debate_rounds": 0,
                "retry_max_attempts": 2,
                "retry_backoff_ms": 0,
                "degrade_mode": "fail",
            }
        )
    )

    retry_count = sum(1 for event in events if event.get("event") == "retry")
    has_error = any(event.get("event") == "error" for event in events)
    has_orchestrator_end = any(
        event.get("event") == "orchestrator_end" for event in events
    )
    print(
        "fail "
        f"retry_count={retry_count} "
        f"has_error={has_error} "
        f"has_orchestrator_end={has_orchestrator_end}"
    )


if __name__ == "__main__":
    validate_round_routing()
    validate_retry_degrade_partial()
    validate_retry_degrade_fail()
