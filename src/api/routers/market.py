from fastapi import APIRouter, HTTPException, Depends
from src.agents.market_analyst import MarketAnalyst
from src.api.dependencies import get_market_analyst

router = APIRouter()

@router.get("/price/{symbol}")
async def get_price(symbol: str, market_analyst: MarketAnalyst = Depends(get_market_analyst)):
    try:
        price = market_analyst.get_latest_price(symbol.upper())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if price is None:
        raise HTTPException(status_code=404, detail=f"Price not found for {symbol}")
    return {"symbol": symbol.upper(), "price": price}
