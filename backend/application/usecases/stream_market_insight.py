"""流式市场洞察用例。"""

from collections.abc import AsyncIterator, Awaitable, Callable

from application.services.market_insight_service import stream_market_insight_events
from schemas.v2.requests import MarketInsightRequest


async def stream_market_insight(
    request: MarketInsightRequest,
    *,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[dict[str, str]]:
    return stream_market_insight_events(request, is_disconnected=is_disconnected)
