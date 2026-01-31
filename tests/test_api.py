import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.dependencies import verify_api_key
from src.api.dependencies import get_market_analyst, get_portfolio_accountant, get_strategy_planner, get_trade_advisor
from unittest.mock import MagicMock
import os

# Unified fixture to manage overrides and env vars
@pytest.fixture(autouse=True)
def setup_api_env():
    # 1. Set environment variable to ensure no 500s
    os.environ["API_KEY"] = "test-secret-key"
    
    # 2. Reset overrides
    app.dependency_overrides = {}
    
    # 3. Set default auth override
    app.dependency_overrides[verify_api_key] = lambda: "valid-key"
    
    yield
    
    # Teardown
    app.dependency_overrides = {}
    os.environ.pop("API_KEY", None)

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}

def test_auth_missing_key():
    # Explicitly remove auth override to test security
    del app.dependency_overrides[verify_api_key]
    
    response = client.get("/portfolio/summary")
    assert response.status_code == 401
    assert response.json() == {"detail": "Missing API Key"}

def test_get_market_price():
    mock_analyst = MagicMock()
    app.dependency_overrides[get_market_analyst] = lambda: mock_analyst
    
    # Success
    mock_analyst.get_latest_price.return_value = 150.0
    response = client.get("/market/price/AAPL")
    assert response.status_code == 200
    assert response.json() == {"symbol": "AAPL", "price": 150.0}
    
    # Not Found
    mock_analyst.get_latest_price.return_value = None
    response = client.get("/market/price/UNKNOWN")
    assert response.status_code == 404

def test_get_portfolio_summary():
    mock_portfolio = MagicMock()
    app.dependency_overrides[get_portfolio_accountant] = lambda: mock_portfolio
    
    mock_data = {
        "equity": 50000.0,
        "cash": 1000.0,
        "last_updated": "2024-01-01T12:00:00"
    }
    mock_portfolio.get_portfolio_summary.return_value = mock_data
    
    response = client.get("/portfolio/summary")
    assert response.status_code == 200
    assert response.json() == mock_data

def test_ask_agent():
    mock_advisor = MagicMock()
    app.dependency_overrides[get_trade_advisor] = lambda: mock_advisor
    
    mock_response = {
        "recommendation": "HOLD",
        "confidence": 0.8,
        "analysis": ["Good fundamentals"],
        "reasoning": "Hold for now",
        "symbol": "AAPL",
        "action": "HOLD"
    }
    mock_advisor.ask.return_value = mock_response
    
    payload = {"question": "Should I sell AAPL?"}
    response = client.post("/agent/ask", json=payload)
    assert response.status_code == 200
    assert response.json() == mock_response

def test_get_recommendations():
    mock_planner = MagicMock()
    app.dependency_overrides[get_strategy_planner] = lambda: mock_planner
    
    mock_data = [{"symbol": "AAPL", "action": "BUY"}]
    mock_planner.get_recent_recommendations.return_value = mock_data
    
    response = client.get("/agent/recommendations")
    assert response.status_code == 200
    assert response.json() == mock_data
