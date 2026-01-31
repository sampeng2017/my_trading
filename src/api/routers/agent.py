from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict
from src.agents.strategy_planner import StrategyPlanner
from src.agents.trade_advisor import TradeAdvisor
from src.api.dependencies import get_strategy_planner, get_trade_advisor

router = APIRouter()

# Input Models
class AskRequest(BaseModel):
    question: str

@router.post("/ask")
async def ask_advisor(request: AskRequest, 
                     trade_advisor: TradeAdvisor = Depends(get_trade_advisor)):
    """Ask the Trade Advisor a natural language question."""
    try:
        response = trade_advisor.ask(request.question)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recommendations")
async def get_recommendations(symbol: Optional[str] = None, limit: int = 10,
                            strategy_planner: StrategyPlanner = Depends(get_strategy_planner)):
    """Get recent strategy recommendations."""
    try:
        return strategy_planner.get_recent_recommendations(symbol, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
