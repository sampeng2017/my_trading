from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from src.api.dependencies import verify_api_key

app = FastAPI(
    title="Trading System API",
    description="REST API for the AI-powered trading system",
    version="1.0.0"
)

# CORS 
# TODO: In production, replace ["*"] with specific frontend domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Cannot be True with allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health Check
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}

# Protected Routes
from src.api.routers import market, portfolio, agent

app.include_router(market.router, prefix="/market", tags=["Market"], dependencies=[Depends(verify_api_key)])
app.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"], dependencies=[Depends(verify_api_key)])
app.include_router(agent.router, prefix="/agent", tags=["Agent"], dependencies=[Depends(verify_api_key)])
