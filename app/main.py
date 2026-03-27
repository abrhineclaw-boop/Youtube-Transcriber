"""YouTube Transcriber — FastAPI application."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .repositories.sqlite import SQLiteRepository
from .routers import api, pages
from .services.jobs import process_queue_worker, enqueue_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    repo = SQLiteRepository(settings.sqlite_path)
    await repo.initialize()
    app.state.repo = repo
    logger.info("Database initialized")

    # Recover transcripts stuck in active statuses from a previous crash
    db = await repo._get_db()
    stuck_statuses = ('downloading', 'transcribing', 'analyzing')
    cursor = await db.execute(
        "SELECT id FROM transcripts WHERE status IN (?, ?, ?)", stuck_statuses
    )
    stuck_rows = await cursor.fetchall()
    for row in stuck_rows:
        tid = row["id"]
        await repo.update_transcript(tid, status="pending", error_message=None)
        await db.execute("DELETE FROM baseline_analysis WHERE transcript_id = ?", (tid,))
    if stuck_rows:
        await db.commit()
        logger.info(f"Reset {len(stuck_rows)} stuck transcripts to pending")

    # Re-enqueue all pending transcripts (in-memory queue is empty on startup)
    cursor = await db.execute("SELECT id FROM transcripts WHERE status = 'pending' ORDER BY id")
    pending_rows = await cursor.fetchall()
    worker_task = asyncio.create_task(process_queue_worker())
    for row in pending_rows:
        await enqueue_job(row["id"], repo)
    if pending_rows:
        logger.info(f"Re-enqueued {len(pending_rows)} pending transcripts")
    logger.info("Job queue worker started")
    yield
    # Shutdown
    worker_task.cancel()
    await repo.close()
    logger.info("Database connection closed")


app = FastAPI(title="YouTube Transcriber", lifespan=lifespan)

# CORS — allows bookmarklet to call API from youtube.com
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.youtube.com", "https://youtube.com"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

# Mount static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers
app.include_router(api.router)
app.include_router(pages.router)
