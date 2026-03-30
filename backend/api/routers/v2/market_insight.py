"""v2 市场洞察 API 路由。"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse
from sse_starlette.sse import EventSourceResponse

from application.services.market_insight_service import get_health_payload
from application.usecases.export_html_report import export_html_report
from application.usecases.export_roadshow_zip import export_roadshow_zip
from application.usecases.generate_market_insight import generate_market_insight
from application.usecases.get_workflow_status import get_workflow_status
from application.usecases.list_sessions import list_sessions
from application.usecases.stream_market_insight import stream_market_insight
from core.exceptions import ConflictError, ResourceNotFoundError, ServiceUnavailableError
from schemas.v2.requests import MarketInsightRequest
from schemas.v2.responses import MarketInsightResponse

router = APIRouter(prefix="/market-insight", tags=["Market Insight v2"])


@router.post("/stream")
async def stream_market_insight_route(
    http_request: Request,
    request: MarketInsightRequest,
):
    event_generator = await stream_market_insight(
        request,
        is_disconnected=http_request.is_disconnected,
    )
    return EventSourceResponse(
        event_generator,
        ping=15,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate", response_model=MarketInsightResponse)
async def generate_market_insight_route(request: MarketInsightRequest):
    try:
        return await generate_market_insight(request)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"系统错误: {str(exc)}") from exc


@router.get("/status/{session_id}")
async def get_workflow_status_route(session_id: str):
    return await get_workflow_status(session_id)


@router.get("/sessions")
async def list_history_sessions_route(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
):
    return await list_sessions(limit=limit, offset=offset, status=status)


@router.get("/report/{session_id}.html")
async def get_html_report_route(session_id: str, download: bool = False):
    try:
        report_path = await export_html_report(session_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    if download:
        return FileResponse(
            path=report_path,
            media_type="text/html",
            filename=f"weaveai-report-{session_id}.html",
        )

    return HTMLResponse(content=report_path.read_text(encoding="utf-8"))


@router.get("/export/{session_id}.zip")
async def export_roadshow_package_route(session_id: str):
    try:
        zip_path = await export_roadshow_zip(session_id)
    except ServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=exc.message) from exc
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"weaveai-roadshow-{session_id}.zip",
    )


@router.get("/health")
async def health_check_route():
    return get_health_payload()
