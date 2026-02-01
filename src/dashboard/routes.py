"""
Dashboard routes - server-side rendered pages.
"""
import os
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from src.api.auth import get_current_user
from src.api.dependencies import get_portfolio_accountant, get_strategy_planner

router = APIRouter(tags=["dashboard"])

# Templates directory
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)


@router.get("/")
async def dashboard_home(request: Request):
    """Dashboard home page."""
    user = await get_current_user(request)
    error = request.query_params.get('error')

    # Get portfolio data (server-side, no API key needed)
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
        "holdings": holdings[:5] if holdings else [],  # Top 5 holdings
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
async def recommendations_page(request: Request):
    """Trade recommendations view."""
    user = await get_current_user(request)

    # Get recent recommendations
    recommendations = []
    try:
        sp = get_strategy_planner()
        recommendations = sp.get_recent_recommendations(limit=20)
    except Exception:
        pass

    return templates.TemplateResponse("recommendations.html", {
        "request": request,
        "user": user,
        "recommendations": recommendations,
    })
