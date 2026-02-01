"""
Orchestrator API - trigger and monitor trading system runs.
"""
import os
import threading
from datetime import datetime
import pytz
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from src.data.db_connection import get_connection
from src.api.dependencies import verify_api_key

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class RunRequest(BaseModel):
    mode: str = "market"  # premarket, market, postmarket, review


class RunResponse(BaseModel):
    job_id: int
    mode: str
    status: str
    started_at: str


def _get_db_path():
    return os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'agent.db')



def _get_running_job_id() -> int | None:
    """Get the ID of any currently running job from database."""
    with get_connection(_get_db_path()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM orchestrator_runs WHERE status IN ('pending', 'running') ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
    return row[0] if row else None


def _append_log(job_id: int, message: str):
    """Append a log message to the job's log."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_line = f"[{timestamp}] {message}\n"
    with get_connection(_get_db_path()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orchestrator_runs SET logs = COALESCE(logs, '') || ? WHERE id = ?",
            (log_line, job_id)
        )
        conn.commit()


def get_recommended_mode() -> dict:
    """Get recommended mode based on current market time (Pacific Time)."""
    try:
        import pandas_market_calendars as mcal
        market_calendar = True
    except ImportError:
        market_calendar = False
    
    pacific = pytz.timezone('America/Los_Angeles')
    now = datetime.now(pacific)
    current_time = now.time()
    today = now.date()
    
    # Check if market is open today
    market_open = True
    if market_calendar:
        nyse = mcal.get_calendar('NYSE')
        schedule = nyse.schedule(start_date=today, end_date=today)
        market_open = len(schedule) > 0
    else:
        market_open = today.weekday() < 5  # Weekday check
    
    if not market_open:
        return {
            "recommended": None,
            "reason": "Market closed today (weekend or holiday)",
            "allow_run": False
        }
    
    # Market hours: 6:30 AM - 1:00 PM Pacific
    from datetime import time
    premarket_end = time(6, 30)
    market_close = time(13, 0)
    postmarket_end = time(21, 0)
    
    if current_time < premarket_end:
        return {
            "recommended": "premarket",
            "reason": f"Before market open ({now.strftime('%I:%M %p')} PT)",
            "allow_run": True
        }
    elif current_time < market_close:
        return {
            "recommended": "market",
            "reason": f"Market hours ({now.strftime('%I:%M %p')} PT)",
            "allow_run": True
        }
    elif current_time < postmarket_end:
        return {
            "recommended": "postmarket",
            "reason": f"After market close ({now.strftime('%I:%M %p')} PT)",
            "allow_run": True
        }
    else:
        return {
            "recommended": "postmarket",
            "reason": f"Evening ({now.strftime('%I:%M %p')} PT) - postmarket if not done",
            "allow_run": True
        }


def _run_orchestrator(job_id: int, mode: str):
    """Background task to run the orchestrator."""
    import sys

    # Ensure src/ is in path for main_orchestrator's relative imports
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    src_path = os.path.join(project_root, 'src')
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from src.main_orchestrator import TradingOrchestrator

    try:
        _append_log(job_id, f"Starting {mode} run...")
        
        # Update status to running
        with get_connection(_get_db_path()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orchestrator_runs SET status = 'running', started_at = ? WHERE id = ?",
                (datetime.now().isoformat(), job_id)
            )
            conn.commit()
        
        _append_log(job_id, "Initializing orchestrator...")

        # Run orchestrator
        orchestrator = TradingOrchestrator()
        
        _append_log(job_id, "Running orchestrator pipeline...")
        orchestrator.run(mode=mode)
        
        _append_log(job_id, "✓ Run completed successfully!")

        # Update status to completed
        with get_connection(_get_db_path()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orchestrator_runs SET status = 'completed', completed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), job_id)
            )
            conn.commit()

    except Exception as e:
        _append_log(job_id, f"✗ Error: {str(e)}")
        # Update status to failed
        with get_connection(_get_db_path()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orchestrator_runs SET status = 'failed', completed_at = ?, error_message = ? WHERE id = ?",
                (datetime.now().isoformat(), str(e), job_id)
            )
            conn.commit()


@router.post("/run", response_model=RunResponse)
async def run_orchestrator(request: RunRequest, _: str = Depends(verify_api_key)):
    """Trigger an orchestrator run."""
    valid_modes = ["premarket", "market", "postmarket", "review"]
    if request.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of: {valid_modes}")

    # Atomic check-and-insert with BEGIN IMMEDIATE to prevent race condition
    # BEGIN IMMEDIATE acquires a reserved lock immediately, blocking other writers
    with get_connection(_get_db_path()) as conn:
        cursor = conn.cursor()
        
        try:
            cursor.execute("BEGIN IMMEDIATE")
            
            # Check for running jobs within the exclusive transaction
            cursor.execute(
                "SELECT COUNT(*) FROM orchestrator_runs WHERE status IN ('pending', 'running')"
            )
            if cursor.fetchone()[0] > 0:
                conn.rollback()
                raise HTTPException(status_code=409, detail="An orchestrator run is already in progress")
            
            # Insert immediately within same transaction
            cursor.execute(
                "INSERT INTO orchestrator_runs (mode, status, triggered_by) VALUES (?, 'pending', 'manual')",
                (request.mode,)
            )
            conn.commit()
            job_id = cursor.lastrowid
        except HTTPException:
            raise
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            # Handle database lock errors with a clear response
            error_msg = str(e).lower()
            if "locked" in error_msg or "busy" in error_msg:
                raise HTTPException(status_code=503, detail="Database busy, please retry")
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Start background thread
    thread = threading.Thread(target=_run_orchestrator, args=(job_id, request.mode))
    thread.daemon = True
    thread.start()

    return RunResponse(
        job_id=job_id,
        mode=request.mode,
        status="pending",
        started_at=datetime.now().isoformat()
    )


@router.get("/status/{job_id}")
async def get_run_status(job_id: int, _: str = Depends(verify_api_key)):
    """Get status of an orchestrator run including logs."""
    with get_connection(_get_db_path()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, mode, status, started_at, completed_at, error_message, logs FROM orchestrator_runs WHERE id = ?",
            (job_id,)
        )
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": row[0],
        "mode": row[1],
        "status": row[2],
        "started_at": row[3],
        "completed_at": row[4],
        "error_message": row[5],
        "logs": row[6] or ""
    }


@router.get("/history")
async def get_run_history(limit: int = 10, _: str = Depends(verify_api_key)):
    """Get recent orchestrator runs."""
    with get_connection(_get_db_path()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, mode, status, started_at, completed_at, error_message, triggered_by
               FROM orchestrator_runs
               ORDER BY id DESC
               LIMIT ?""",
            (limit,)
        )
        rows = cursor.fetchall()

    return [
        {
            "job_id": row[0],
            "mode": row[1],
            "status": row[2],
            "started_at": row[3],
            "completed_at": row[4],
            "error_message": row[5],
            "triggered_by": row[6]
        }
        for row in rows
    ]


@router.get("/current")
async def get_current_run(_: str = Depends(verify_api_key)):
    """Check if any orchestrator run is currently in progress (multi-worker safe)."""
    job_id = _get_running_job_id()
    if job_id:
        return {"running": True, "job_id": job_id}
    return {"running": False, "job_id": None}


@router.get("/recommended-mode")
async def get_recommended_mode_endpoint(_: str = Depends(verify_api_key)):
    """Get recommended mode based on current market time."""
    return get_recommended_mode()
