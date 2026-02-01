"""
Dashboard routes - server-side rendered pages.
"""
import os
import tempfile
from datetime import datetime, timedelta
from collections import Counter
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from src.api.auth import get_current_user
from src.api.dependencies import get_portfolio_accountant, get_strategy_planner, get_trade_advisor

router = APIRouter(tags=["dashboard"])

# Templates directory
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)


def format_timestamp(iso_timestamp: str) -> str:
    """Convert ISO timestamp to readable format: 'Jan 30, 1:50 PM'"""
    if not iso_timestamp:
        return 'N/A'
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
        return dt.strftime('%b %d, %I:%M %p')
    except:
        return iso_timestamp[:16].replace('T', ' ')


@router.get("/")
async def dashboard_home(request: Request):
    """Dashboard home page."""
    user = await get_current_user(request)
    error = request.query_params.get('error')

    portfolio = None
    holdings = []
    try:
        pa = get_portfolio_accountant()
        portfolio = pa.get_portfolio_summary()
        holdings = pa.get_current_holdings()
    except Exception:
        pass

    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "error": error,
        "portfolio": portfolio,
        "holdings": holdings[:5] if holdings else [],
    })


@router.get("/portfolio")
async def portfolio_page(request: Request):
    """Full portfolio view."""
    user = await get_current_user(request)

    portfolio = None
    holdings = []
    try:
        pa = get_portfolio_accountant()
        portfolio = pa.get_portfolio_summary()
        holdings = pa.get_current_holdings()
    except Exception:
        pass

    return templates.TemplateResponse("portfolio.html", {
        "request": request,
        "user": user,
        "portfolio": portfolio,
        "holdings": holdings,
    })


@router.get("/recommendations")
async def recommendations_page(request: Request, days: int = 7):
    """Trade recommendations view with date filter and analytics."""
    user = await get_current_user(request)

    recommendations = []
    analytics = {
        'total': 0,
        'by_action': {'BUY': 0, 'SELL': 0, 'HOLD': 0},
        'top_symbols': [],
    }

    try:
        sp = get_strategy_planner()
        raw_recommendations = sp.get_recent_recommendations(limit=100)

        # Filter by days
        if days > 0:
            cutoff = datetime.now() - timedelta(days=days)
            cutoff_str = cutoff.isoformat()
            raw_recommendations = [
                r for r in raw_recommendations
                if r.get('timestamp', '') >= cutoff_str
            ]

        # Format timestamps
        for r in raw_recommendations:
            r['formatted_time'] = format_timestamp(r.get('timestamp'))

        recommendations = raw_recommendations

        # Calculate analytics
        analytics['total'] = len(recommendations)

        for r in recommendations:
            action = r.get('action', 'HOLD').upper()
            if action in analytics['by_action']:
                analytics['by_action'][action] += 1

        symbol_counts = Counter(r.get('symbol') for r in recommendations)
        analytics['top_symbols'] = symbol_counts.most_common(5)

    except Exception:
        pass

    return templates.TemplateResponse("recommendations.html", {
        "request": request,
        "user": user,
        "recommendations": recommendations,
        "selected_days": days,
        "analytics": analytics,
    })


# ========================
# Chat Interface
# ========================

@router.get("/chat")
async def chat_page(request: Request):
    """Chat interface page."""
    user = await get_current_user(request)
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "user": user,
    })


@router.post("/api/chat")
async def chat_api(request: Request):
    """Direct call to trade advisor for chat."""
    user = await get_current_user(request)

    if not user:
        return JSONResponse({"error": "Login required"}, status_code=401)

    try:
        body = await request.json()
        question = body.get("question", "")

        if not question:
            return JSONResponse({"error": "Question is required"}, status_code=400)

        ta = get_trade_advisor()
        result = ta.ask(question)
        return JSONResponse(result)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ========================
# Orchestrator Controls
# ========================

# Import orchestrator functions directly to avoid HTTP calls
from src.api.routers import orchestrator as orch_module
from fastapi import HTTPException


@router.post("/api/orchestrator/run")
async def trigger_run(request: Request):
    """Trigger orchestrator run from dashboard."""
    user = await get_current_user(request)
    if not user:
        return JSONResponse({"error": "Login required"}, status_code=401)

    try:
        body = await request.json()
        mode = body.get("mode", "market")

        # Call orchestrator directly using its RunRequest model
        result = await orch_module.run_orchestrator(orch_module.RunRequest(mode=mode), _="direct")
        return JSONResponse(result.model_dump())
    except HTTPException as e:
        # Preserve the original status code and use 'detail' for consistency
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/orchestrator/status/{job_id}")
async def get_status(request: Request, job_id: int):
    """Get orchestrator run status."""
    user = await get_current_user(request)
    if not user:
        return JSONResponse({"error": "Login required"}, status_code=401)

    try:
        result = await orch_module.get_run_status(job_id, _="direct")
        return JSONResponse(result)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/orchestrator/current")
async def get_current(request: Request):
    """Check if orchestrator is running."""
    user = await get_current_user(request)
    if not user:
        return JSONResponse({"error": "Login required"}, status_code=401)

    try:
        result = await orch_module.get_current_run(_="direct")
        return JSONResponse(result)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/orchestrator/recommended-mode")
async def get_recommended_mode(request: Request):
    """Get recommended mode based on current market time."""
    user = await get_current_user(request)
    if not user:
        return JSONResponse({"error": "Login required"}, status_code=401)

    try:
        result = await orch_module.get_recommended_mode_endpoint(_="direct")
        return JSONResponse(result)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/portfolio/import")
async def import_portfolio(request: Request, file: UploadFile = File(...)):
    """Import a Fidelity CSV portfolio export."""
    user = await get_current_user(request)
    if not user:
        return JSONResponse({"error": "Login required"}, status_code=401)

    # Validate filename extension
    if not file.filename.endswith('.csv'):
        return JSONResponse({"error": "File must be a CSV"}, status_code=400)

    # Validate MIME type (browsers may send various types for CSV)
    allowed_types = {'text/csv', 'application/csv', 'text/plain', 'application/vnd.ms-excel'}
    if file.content_type and file.content_type not in allowed_types:
        return JSONResponse({"error": f"Invalid file type: {file.content_type}"}, status_code=400)

    tmp_path = None
    try:
        # Stream with size limit (1MB max) - abort early if exceeded
        max_size = 1 * 1024 * 1024  # 1MB
        chunk_size = 64 * 1024  # 64KB chunks
        total_size = 0
        chunks = []

        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_size:
                return JSONResponse({"error": "File too large (max 1MB)"}, status_code=400)
            chunks.append(chunk)

        content = b''.join(chunks)

        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # Import using PortfolioAccountant
        pa = get_portfolio_accountant()
        snapshot_id = pa.import_fidelity_csv(tmp_path)

        if snapshot_id:
            return JSONResponse({
                "success": True,
                "snapshot_id": snapshot_id,
                "message": "Portfolio imported successfully"
            })
        else:
            return JSONResponse({"error": "Import failed - no data parsed"}, status_code=400)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        # Always clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


