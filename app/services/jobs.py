"""Background job processing for transcription and analysis."""

import asyncio
import json
import logging
import os
import time

from ..ai.provider import get_ai_provider
from ..config import settings
from ..repositories.base import BaseRepository
from .transcription import download_audio, transcribe_audio, cleanup_audio
from .analysis import run_baseline_analysis

logger = logging.getLogger(__name__)

# Pricing per million tokens (USD)
MODEL_PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
}
DEFAULT_PRICING = {"input": 3.0, "output": 15.0}


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
    return round(
        (input_tokens * pricing["input"] / 1_000_000)
        + (output_tokens * pricing["output"] / 1_000_000),
        6,
    )

# --- Sequential Job Queue ---
_job_queue: asyncio.Queue | None = None
_cancelled_ids: set[int] = set()
_active_process: asyncio.subprocess.Process | None = None
_active_job_id: int | None = None
_SENTINEL = object()


def get_job_queue() -> asyncio.Queue:
    global _job_queue
    if _job_queue is None:
        _job_queue = asyncio.Queue()
    return _job_queue


async def enqueue_job(transcript_id: int, repo: BaseRepository) -> None:
    """Add a transcript job to the sequential processing queue."""
    queue = get_job_queue()
    await queue.put((transcript_id, repo))


def set_active_process(process: asyncio.subprocess.Process | None, job_id: int | None = _SENTINEL) -> None:
    """Track the currently running subprocess so cancellation can kill it.

    When called from transcription functions (process only), preserves the existing job_id.
    When called from job pipeline, sets both process and job_id.
    """
    global _active_process, _active_job_id
    _active_process = process
    if job_id is not _SENTINEL:
        _active_job_id = job_id


def cancel_job(transcript_id: int) -> None:
    """Mark a transcript job for cancellation and kill its active subprocess."""
    _cancelled_ids.add(transcript_id)
    if _active_job_id == transcript_id and _active_process is not None:
        try:
            _active_process.kill()
            logger.info(f"[{transcript_id}] Killed active subprocess (PID {_active_process.pid})")
        except ProcessLookupError:
            pass
    logger.info(f"[{transcript_id}] Marked for cancellation")


def is_cancelled(transcript_id: int) -> bool:
    return transcript_id in _cancelled_ids


class JobCancelledError(Exception):
    pass


async def process_queue_worker() -> None:
    """Worker that processes transcript jobs one at a time."""
    queue = get_job_queue()
    while True:
        transcript_id, repo = await queue.get()
        try:
            if is_cancelled(transcript_id):
                logger.info(f"[{transcript_id}] Skipping cancelled job")
                _cancelled_ids.discard(transcript_id)
            else:
                await process_transcript_job(transcript_id, repo)
        except Exception:
            logger.exception(f"[{transcript_id}] Unhandled error in worker")
        finally:
            queue.task_done()


async def process_transcript_job(transcript_id: int, repo: BaseRepository) -> None:
    """Full pipeline: download → transcribe → baseline analysis.

    Updates transcript status at each stage so the UI can show progress.
    Collects processing stats throughout the pipeline.
    """
    audio_path = None
    stats = {}
    job_start = time.time()
    current_stage = "init"

    set_active_process(None, transcript_id)
    try:
        transcript = await repo.get_transcript(transcript_id)
        if not transcript:
            logger.error(f"Transcript {transcript_id} not found")
            return

        video_url = transcript["video_url"]

        def _check_cancelled():
            if is_cancelled(transcript_id):
                _cancelled_ids.discard(transcript_id)
                raise JobCancelledError(f"Job {transcript_id} was cancelled")

        _check_cancelled()

        # Step 1: Download
        current_stage = "downloading"
        await repo.update_transcript(transcript_id, status="downloading")
        logger.info(f"[{transcript_id}] Downloading: {video_url}")
        dl_start = time.time()
        download_info = await download_audio(video_url)
        stats["download_time_seconds"] = round(time.time() - dl_start, 2)
        audio_path = download_info["audio_path"]

        # Capture audio file size
        if os.path.exists(audio_path):
            stats["audio_file_size_bytes"] = os.path.getsize(audio_path)

        await repo.update_transcript(
            transcript_id,
            title=download_info["title"],
            channel=download_info["channel"],
            duration_seconds=download_info["duration"],
            upload_date=download_info.get("upload_date", ""),
            status="transcribing",
        )

        # Store channel → profile association
        channel = download_info["channel"]
        if channel and channel != "Unknown Channel":
            await repo.set_channel_profile(channel, transcript["profile_id"])

        _check_cancelled()

        # Step 2: Transcribe
        current_stage = "transcribing"
        logger.info(f"[{transcript_id}] Transcribing with Whisper...")
        tx_start = time.time()
        segments = await transcribe_audio(audio_path)
        stats["transcription_time_seconds"] = round(time.time() - tx_start, 2)
        stats["whisper_model"] = settings.whisper_model
        stats["segment_count"] = len(segments)

        # Word count and WPM
        total_words = sum(len(s["text"].split()) for s in segments)
        stats["total_word_count"] = total_words
        duration_minutes = download_info["duration"] / 60 if download_info["duration"] else 0
        if duration_minutes > 0:
            stats["avg_words_per_minute"] = round(total_words / duration_minutes, 1)

        await repo.update_transcript(
            transcript_id,
            transcript_json=json.dumps(segments),
            status="analyzing",
        )

        # Clean up audio file immediately after transcription
        cleanup_audio(audio_path)
        audio_path = None

        _check_cancelled()

        # Step 3: Baseline analysis
        current_stage = "analyzing"
        logger.info(f"[{transcript_id}] Running baseline analysis...")
        an_start = time.time()
        ai = get_ai_provider()
        baseline_result = await run_baseline_analysis(transcript_id, repo, ai)
        stats["analysis_time_seconds"] = round(time.time() - an_start, 2)
        stats["claude_model"] = settings.claude_model

        # Save auto-generated tags (filter rejected, boost confirmed for this channel)
        auto_tags = baseline_result.get("tags", [])
        if auto_tags and channel and channel != "Unknown Channel":
            rejected = await repo.get_rejected_tags_for_channel(channel)
            confirmed = await repo.get_confirmed_tags_for_channel(channel)
            auto_tags = [t for t in auto_tags if t.lower() not in rejected]
            # Prepend confirmed tags that the AI also suggested (prioritize them)
            confirmed_lower = {c.lower() for c in confirmed}
            boosted = [t for t in auto_tags if t.lower() in confirmed_lower]
            rest = [t for t in auto_tags if t.lower() not in confirmed_lower]
            auto_tags = boosted + rest
        for tag_name in auto_tags[:5]:
            await repo.add_tag_to_transcript(transcript_id, tag_name, source="auto")

        # Auto-computed quality scores
        if segments and total_words > 0:
            import statistics
            # Info density: unique words / total words (vocabulary richness)
            words = [w.lower() for s in segments for w in s["text"].split()]
            unique_ratio = len(set(words)) / len(words) if words else 0
            stats["info_density_score"] = round(unique_ratio * 100, 1)

            # Pacing: consistency of speech rate across segments
            seg_wpm = []
            for s in segments:
                dur = s["end"] - s["start"]
                if dur > 0:
                    seg_wpm.append(len(s["text"].split()) / (dur / 60))
            if len(seg_wpm) > 1:
                mean_wpm = statistics.mean(seg_wpm)
                std_wpm = statistics.stdev(seg_wpm)
                cv = std_wpm / mean_wpm if mean_wpm > 0 else 1
                stats["pacing_score"] = round(max(0, 100 - cv * 100), 1)
            else:
                stats["pacing_score"] = 50.0

            # Segment consistency: how evenly content is distributed
            seg_durations = [s["end"] - s["start"] for s in segments if s["end"] - s["start"] > 0]
            if len(seg_durations) > 1:
                mean_dur = statistics.mean(seg_durations)
                std_dur = statistics.stdev(seg_durations)
                cv_dur = std_dur / mean_dur if mean_dur > 0 else 1
                stats["segment_consistency_score"] = round(max(0, 100 - cv_dur * 100), 1)

        # Token usage and cost
        stats["baseline_input_tokens"] = baseline_result.get("input_tokens", 0)
        stats["baseline_output_tokens"] = baseline_result.get("output_tokens", 0)
        stats["estimated_cost_usd"] = estimate_cost(
            stats["baseline_input_tokens"],
            stats["baseline_output_tokens"],
            settings.claude_model,
        )

        stats["total_processing_time_seconds"] = round(time.time() - job_start, 2)

        await repo.update_transcript(
            transcript_id,
            status="ready",
            processing_stats=json.dumps(stats),
        )
        logger.info(f"[{transcript_id}] Complete! ({stats['total_processing_time_seconds']}s)")

    except JobCancelledError:
        logger.info(f"[{transcript_id}] Job cancelled at stage: {current_stage}")
        stats["total_processing_time_seconds"] = round(time.time() - job_start, 2)
        await repo.update_transcript(
            transcript_id,
            status="cancelled",
            error_message="Cancelled by user",
            processing_stats=json.dumps(stats),
        )
        if audio_path:
            cleanup_audio(audio_path)
    except Exception as e:
        logger.error(f"[{transcript_id}] Job failed: {e}", exc_info=True)
        stats["error_stage"] = current_stage
        stats["total_processing_time_seconds"] = round(time.time() - job_start, 2)
        await repo.update_transcript(
            transcript_id,
            status="error",
            error_message=str(e)[:500],
            processing_stats=json.dumps(stats),
        )
        if audio_path:
            cleanup_audio(audio_path)
    finally:
        set_active_process(None, None)
