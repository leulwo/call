"""ExamPaper Refine - Process Router."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import ExamPaper, ProcessingStatusResponse
from pipeline.orchestrator import process_paper

router = APIRouter()


async def _reprocess_background(paper_id: str):
    """Run the pipeline in a background task."""
    from app.database import async_session
    async with async_session() as db:
        await process_paper(db, paper_id)


@router.get("/papers/{paper_id}/status", response_model=ProcessingStatusResponse)
async def get_processing_status(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Get the current processing status and logs for a paper."""
    stmt = (
        select(ExamPaper)
        .where(ExamPaper.id == paper_id)
        .options(selectinload(ExamPaper.processing_logs))
    )
    result = await db.execute(stmt)
    paper = result.scalars().first()
    
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    # Sort logs by start time
    logs = sorted(paper.processing_logs, key=lambda log: log.started_at or log.id)
    
    # Determine current stage (the last running stage)
    current_stage = None
    for log in reversed(logs):
        if log.status == "running":
            current_stage = log.stage
            break
            
    return ProcessingStatusResponse(
        id=paper.id,
        status=paper.status,
        stages=logs,
        current_stage=current_stage,
    )


@router.post("/papers/{paper_id}/reprocess")
async def reprocess_paper(
    paper_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Manually trigger reprocessing of an existing paper."""
    paper = await db.get(ExamPaper, paper_id)
    
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    if paper.status.value in ("processing", "preprocessing", "extracting", "analyzing", "rewriting", "rendering"):
        raise HTTPException(status_code=400, detail="Paper is already processing")
        
    # Start processing pipeline in background
    background_tasks.add_task(_reprocess_background, paper.id)
    
    return {"message": "Reprocessing started", "paper_id": paper_id}
