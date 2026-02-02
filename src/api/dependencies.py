from fastapi import Header, HTTPException, status
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    api_key = os.getenv("API_KEY")
    
    if not api_key:
        # Fail safe if server is misconfigured
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server Authorization Misconfigured",
        )
        
    if x_api_key is None:
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key",
        )

    if x_api_key != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
    return x_api_key
# Agent Dependencies
def get_db_path():
    db_path = os.path.join(os.getcwd(), 'data', 'agent.db')
    if os.getenv("DB_MODE") == "turso":
        pass
    return db_path

def get_config():
    from src.utils.config import Config
    return Config()

def get_market_analyst():
    from src.agents.market_analyst import MarketAnalyst
    config = get_config()
    db_path = get_db_path()
    return MarketAnalyst(db_path, config.get_agent_config('market_analyst'))

def get_portfolio_accountant():
    from src.agents.portfolio_accountant import PortfolioAccountant
    db_path = get_db_path()
    return PortfolioAccountant(db_path)

def get_strategy_planner():
    from src.agents.strategy_planner import StrategyPlanner
    config = get_config().config
    db_path = get_db_path()
    gemini_key = os.getenv("GEMINI_API_KEY")
    return StrategyPlanner(db_path, gemini_key, config)

def get_trade_advisor():
    from src.agents.trade_advisor import TradeAdvisor
    from src.agents.market_analyst import MarketAnalyst
    
    config_obj = get_config()
    config = config_obj.config
    db_path = get_db_path()
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    # Initialize Market Analyst for on-demand data fetching
    # Extract config for Market Analyst and pass keys directly if needed
    ma_config = config_obj.get_agent_config('market_analyst') or {}
    
    # Get keys from env (preferred) or config
    alpaca_key = os.getenv("ALPACA_API_KEY") or ma_config.get('api_key')
    alpaca_secret = os.getenv("ALPACA_SECRET_KEY") or ma_config.get('api_secret')
    
    market_analyst = MarketAnalyst(db_path, alpaca_key, alpaca_secret, ma_config)
    
    return TradeAdvisor(db_path, gemini_key, config, market_analyst)
