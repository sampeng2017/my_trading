"""
Trading System REST API
"""
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

# Load environment variables FIRST
load_dotenv()

from src.api.routers import market, portfolio, agent, auth, orchestrator
from src.api.dependencies import verify_api_key
from src.api.auth import init_oauth
from src.dashboard import routes as dashboard

app = FastAPI(
    title="Trading System API",
    description="Stock Trading Intelligence System API",
    version="1.0.0"
)

# Session middleware (MUST be added before routers)
session_secret = os.getenv("SESSION_SECRET")
if session_secret:
    app.add_middleware(SessionMiddleware, secret_key=session_secret)

# CORS middleware
# NOTE: allow_origins=['*'] with allow_credentials=True is invalid.
# We restrict to localhost for dev. In prod, use CORS_ORIGINS env var.
origins = os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OAuth
init_oauth()

# Mount static files for dashboard
static_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Health check (public)
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "1.0.0"}

# Auth routes (public - OAuth flow)
app.include_router(auth.router)

# Dashboard routes (public/OAuth protected - server-side rendering)
app.include_router(dashboard.router)

# API routes (API key protected)
app.include_router(
    portfolio.router,
    prefix="/portfolio",
    tags=["portfolio"],
    dependencies=[Depends(verify_api_key)]
)
app.include_router(
    market.router,
    prefix="/market",
    tags=["market"],
    dependencies=[Depends(verify_api_key)]
)
app.include_router(
    agent.router,
    prefix="/agent",
    tags=["agent"],
    dependencies=[Depends(verify_api_key)]
)
app.include_router(
    orchestrator.router,
    dependencies=[Depends(verify_api_key)]
)
