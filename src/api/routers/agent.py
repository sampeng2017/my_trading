from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict
import threading
from datetime import datetime

from src.agents.strategy_planner import StrategyPlanner
from src.agents.trade_advisor import TradeAdvisor
from src.agents.recommendation_evaluator import RecommendationEvaluator
from src.data.db_connection import get_connection
from src.api.dependencies import (
    get_strategy_planner, get_trade_advisor,
    get_recommendation_evaluator, get_db_path
)

router = APIRouter()

# Input Models
class AskRequest(BaseModel):
    question: str

class EvaluateRequest(BaseModel):
    top_n: Optional[int] = None
    min_age_days: Optional[int] = None
    max_age_days: Optional[int] = None

class EvaluateResponse(BaseModel):
    job_id: int
    status: str
    message: str

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


def _run_evaluation_background(job_id: int, top_n, min_age_days, max_age_days):
    """Background task to run recommendation evaluation."""
    db_path = get_db_path()

    try:
        # Mark running
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orchestrator_runs SET status = 'running', started_at = ? WHERE id = ?",
                (datetime.now().isoformat(), job_id)
            )
            conn.commit()

        evaluator = get_recommendation_evaluator()
        result = evaluator.evaluate_recommendations(
            top_n=top_n,
            min_age_days=min_age_days,
            max_age_days=max_age_days
        )
        summary = result.get('summary', '')
        status = result.get('status', 'completed')

        # Mark completed/failed and save summary to logs
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orchestrator_runs SET status = ?, completed_at = ?, logs = ? WHERE id = ?",
                (status, datetime.now().isoformat(), summary, job_id)
            )
            conn.commit()

    except Exception as e:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orchestrator_runs SET status = 'failed', completed_at = ?, error_message = ? WHERE id = ?",
                (datetime.now().isoformat(), str(e), job_id)
            )
            conn.commit()


@router.post("/evaluate", response_model=EvaluateResponse)
async def run_evaluation(request: EvaluateRequest = EvaluateRequest()):
    """Trigger recommendation evaluation as a background job.

    Returns a job_id that can be polled via GET /orchestrator/status/{job_id}.
    """
    db_path = get_db_path()

    # Atomic check-and-insert with BEGIN IMMEDIATE
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            
            # Check for running jobs within the exclusive transaction
            cursor.execute(
                "SELECT COUNT(*) FROM orchestrator_runs WHERE mode = 'evaluate' AND status IN ('pending', 'running')"
            )
            if cursor.fetchone()[0] > 0:
                conn.rollback()
                raise HTTPException(status_code=409, detail="An evaluation is already in progress")
            
            # Insert immediately within same transaction
            cursor.execute(
                "INSERT INTO orchestrator_runs (mode, status, triggered_by) VALUES ('evaluate', 'pending', 'manual')"
            )
            conn.commit()
            job_id = cursor.lastrowid
        
        except sqlite3.IntegrityError as e:
            conn.rollback()
            # Detect CHECK constraint failure on mode (older DB schema)
            if "CHECK constraint failed" in str(e) and "mode" in str(e): # SQLite default message often includes column or constraint name
                 raise HTTPException(
                     status_code=400, 
                     detail="Database schema outdated. Please run scripts/migrate_v2.py to enable 'evaluate' mode."
                 )
            # Fallback for other integrity errors
            raise HTTPException(status_code=500, detail=f"Database integrity error: {str(e)}")

        except HTTPException:
            raise
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            error_msg = str(e).lower()
            if "locked" in error_msg or "busy" in error_msg:
                raise HTTPException(status_code=503, detail="Database busy, please retry")
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Run in background thread
    thread = threading.Thread(
        target=_run_evaluation_background,
        args=(job_id, request.top_n, request.min_age_days, request.max_age_days)
    )
    thread.daemon = True
    thread.start()

    return EvaluateResponse(
        job_id=job_id,
        status="pending",
        message="Evaluation started. Poll GET /orchestrator/status/{job_id} for progress."
    )


@router.get("/evaluations")
async def get_evaluations(symbol: Optional[str] = None, limit: int = 20,
                          evaluator: RecommendationEvaluator = Depends(get_recommendation_evaluator)):
    """Get recent recommendation evaluation results."""
    try:
        return evaluator.get_recent_evaluations(symbol, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
