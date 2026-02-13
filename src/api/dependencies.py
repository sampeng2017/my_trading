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
    from src.utils.config import get_db_path as config_get_db_path
    return config_get_db_path()

def get_config():
    from src.utils.config import Config
    return Config()

def get_market_analyst():
    from src.agents.market_analyst import MarketAnalyst
    config_obj = get_config()
    db_path = get_db_path()
    ma_config = config_obj.get_agent_config('market_analyst') or {}
    api_keys = config_obj.config.get('api_keys', {})
    # Get keys from env (preferred) or config.yaml api_keys section
    alpaca_key = os.getenv("ALPACA_API_KEY") or api_keys.get('alpaca_api_key')
    alpaca_secret = os.getenv("ALPACA_SECRET_KEY") or api_keys.get('alpaca_secret_key')
    return MarketAnalyst(db_path, alpaca_key, alpaca_secret, ma_config)

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
    api_keys = config.get('api_keys', {})

    # Initialize Market Analyst for on-demand data fetching
    ma_config = config_obj.get_agent_config('market_analyst') or {}

    # Get keys from env (preferred) or config.yaml api_keys section
    alpaca_key = os.getenv("ALPACA_API_KEY") or api_keys.get('alpaca_api_key')
    alpaca_secret = os.getenv("ALPACA_SECRET_KEY") or api_keys.get('alpaca_secret_key')

    market_analyst = MarketAnalyst(db_path, alpaca_key, alpaca_secret, ma_config)

    return TradeAdvisor(db_path, gemini_key, config, market_analyst)

def get_recommendation_evaluator():
    from src.agents.recommendation_evaluator import RecommendationEvaluator
    config = get_config().config
    db_path = get_db_path()
    gemini_key = os.getenv("GEMINI_API_KEY")
    return RecommendationEvaluator(db_path, gemini_key, config)
