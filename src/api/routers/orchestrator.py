"""
Orchestrator API - trigger and monitor trading system runs.
"""
import os
import threading
from datetime import datetime
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


def _run_orchestrator(job_id: int, mode: str):
    """Background task to run the orchestrator."""
    from src.main_orchestrator import TradingOrchestrator

    try:
        # Update status to running
        with get_connection(_get_db_path()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orchestrator_runs SET status = 'running', started_at = ? WHERE id = ?",
                (datetime.now().isoformat(), job_id)
            )
            conn.commit()

        # Run orchestrator
        orchestrator = TradingOrchestrator()
        orchestrator.run(mode=mode)

        # Update status to completed
        with get_connection(_get_db_path()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orchestrator_runs SET status = 'completed', completed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), job_id)
            )
            conn.commit()

    except Exception as e:
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
    """Get status of an orchestrator run."""
    with get_connection(_get_db_path()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, mode, status, started_at, completed_at, error_message FROM orchestrator_runs WHERE id = ?",
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
        "error_message": row[5]
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
