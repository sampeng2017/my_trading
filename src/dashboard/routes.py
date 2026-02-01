"""
Dashboard routes - server-side rendered pages.
"""
import os
from datetime import datetime, timedelta
from collections import Counter
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from src.api.auth import get_current_user
from src.api.dependencies import get_portfolio_accountant, get_strategy_planner

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
