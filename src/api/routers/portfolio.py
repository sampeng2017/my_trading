from fastapi import APIRouter, HTTPException, Depends
from src.agents.portfolio_accountant import PortfolioAccountant
from src.api.dependencies import get_portfolio_accountant

router = APIRouter()

@router.get("/summary")
async def get_summary(portfolio_accountant: PortfolioAccountant = Depends(get_portfolio_accountant)):
    """Get portfolio summary (equity, cash)."""
    try:
        return portfolio_accountant.get_portfolio_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/holdings")
async def get_holdings(portfolio_accountant: PortfolioAccountant = Depends(get_portfolio_accountant)):
    """Get current holdings."""
    try:
        return portfolio_accountant.get_current_holdings()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
