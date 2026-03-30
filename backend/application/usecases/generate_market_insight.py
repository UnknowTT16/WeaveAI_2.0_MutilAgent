"""同步市场洞察用例。"""

from application.services.market_insight_service import generate_market_insight_payload
from schemas.v2.requests import MarketInsightRequest
from schemas.v2.responses import MarketInsightResponse


async def generate_market_insight(
    request: MarketInsightRequest,
) -> MarketInsightResponse:
    return await generate_market_insight_payload(request)
