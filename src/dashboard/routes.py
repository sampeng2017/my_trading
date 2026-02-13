"""
Dashboard routes - server-side rendered pages.
"""
import os
import tempfile
from datetime import datetime, timedelta
from collections import Counter
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
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
    
    if not user:
        return RedirectResponse(url="/auth/login")

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
    if not user:
        return RedirectResponse(url="/auth/login")

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
    if not user:
        return RedirectResponse(url="/auth/login")

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
    if not user:
        return RedirectResponse(url="/auth/login")
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
from src.api.routers import agent as agent_module
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
        max_extra_recs = body.get("max_extra_recs")

        # Call orchestrator directly using its RunRequest model
        result = await orch_module.run_orchestrator(
            orch_module.RunRequest(mode=mode, max_extra_recs=max_extra_recs), _="direct"
        )
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


# ========================
# Evaluations
# ========================

@router.get("/evaluations")
async def evaluations_page(request: Request, score: str = "", symbol: str = ""):
    """Recommendation evaluations view with analytics and filters."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login")

    evaluations = []
    all_symbols = []
    analytics = {
        'total': 0,
        'score_distribution': {'excellent': 0, 'good': 0, 'neutral': 0, 'poor': 0, 'bad': 0},
        'hit_rate': 0,
        'avg_price_change': 0,
        'target_hit_count': 0,
        'stop_hit_count': 0,
    }

    try:
        from src.api.dependencies import get_recommendation_evaluator
        evaluator = get_recommendation_evaluator()

        # Fetch all for analytics and symbol list
        all_evaluations = evaluator.get_recent_evaluations(limit=100)
        all_symbols = sorted(set(e.get('symbol', '') for e in all_evaluations))

        # Apply filters
        filtered = all_evaluations
        if symbol:
            filtered = [e for e in filtered if e.get('symbol') == symbol.upper()]
        if score:
            filtered = [e for e in filtered if e.get('score') == score]

        # Format timestamps
        for e in filtered:
            e['formatted_rec_date'] = format_timestamp(e.get('recommendation_date'))
            e['formatted_eval_date'] = format_timestamp(e.get('evaluation_date'))

        evaluations = filtered

        # Calculate analytics on filtered set
        analytics['total'] = len(evaluations)
        for e in evaluations:
            s = e.get('score', 'neutral')
            if s in analytics['score_distribution']:
                analytics['score_distribution'][s] += 1
            if e.get('target_hit'):
                analytics['target_hit_count'] += 1
            if e.get('stop_loss_hit'):
                analytics['stop_hit_count'] += 1

        if analytics['total'] > 0:
            total_pct = sum(e.get('price_change_pct', 0) for e in evaluations)
            analytics['avg_price_change'] = round(total_pct / analytics['total'], 2)

            correct = sum(
                1 for e in evaluations
                if (e.get('original_action') == 'BUY' and (e.get('price_change_pct') or 0) > 0)
                or (e.get('original_action') == 'SELL' and (e.get('price_change_pct') or 0) < 0)
            )
            analytics['hit_rate'] = round(correct / analytics['total'] * 100, 1)

    except Exception:
        pass

    return templates.TemplateResponse("evaluations.html", {
        "request": request,
        "user": user,
        "evaluations": evaluations,
        "analytics": analytics,
        "selected_score": score,
        "selected_symbol": symbol,
        "all_symbols": all_symbols,
    })


@router.post("/api/agent/evaluate")
async def trigger_evaluation(request: Request):
    """Trigger recommendation evaluation from dashboard."""
    user = await get_current_user(request)
    if not user:
        return JSONResponse({"error": "Login required"}, status_code=401)

    try:
        result = await agent_module.run_evaluation(agent_module.EvaluateRequest())
        return JSONResponse(result.model_dump())
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
