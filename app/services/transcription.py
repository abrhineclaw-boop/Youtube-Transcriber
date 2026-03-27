"""Download audio via yt-dlp and transcribe with Whisper."""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

from ..config import settings

logger = logging.getLogger(__name__)


async def download_audio(video_url: str) -> dict:
    """Download audio from YouTube URL using yt-dlp.

    Returns dict with: title, channel, duration, audio_path
    Raises RuntimeError with descriptive message on failure.
    """
    temp_dir = Path(settings.temp_audio_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(temp_dir / "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "--output", output_template,
        "--print-json",
        "--no-playlist",
        "--no-warnings",
        video_url,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    from .jobs import set_active_process
    set_active_process(process)
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=settings.download_timeout_seconds
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(
            f"Download timed out after {settings.download_timeout_seconds}s. "
            "Try a shorter video or increase DOWNLOAD_TIMEOUT_SECONDS."
        )
    finally:
        set_active_process(None)

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        # Provide clear error messages for common failures
        if "Private video" in error_msg:
            raise RuntimeError("This video is private and cannot be accessed.")
        elif "age" in error_msg.lower():
            raise RuntimeError("This video is age-restricted. yt-dlp may need authentication to access it.")
        elif "region" in error_msg.lower() or "geo" in error_msg.lower():
            raise RuntimeError("This video is region-locked and not available from this location.")
        elif "live" in error_msg.lower():
            raise RuntimeError("Live streams are not supported. Please wait until the stream ends and try again.")
        elif "HTTP Error 429" in error_msg:
            raise RuntimeError("YouTube is rate-limiting requests. Please wait a few minutes and try again.")
        elif "Unable to extract" in error_msg or "is not a valid URL" in error_msg:
            raise RuntimeError(f"Could not process this URL. It may be invalid or yt-dlp may need updating (pip install --upgrade yt-dlp). Error: {error_msg[:200]}")
        else:
            raise RuntimeError(f"Download failed: {error_msg[:300]}")

    info = json.loads(stdout.decode().strip().split("\n")[-1])
    video_id = info.get("id", "unknown")
    audio_path = str(temp_dir / f"{video_id}.mp3")

    if not os.path.exists(audio_path):
        # yt-dlp might have used a different extension
        for ext in ["mp3", "m4a", "webm", "opus"]:
            candidate = str(temp_dir / f"{video_id}.{ext}")
            if os.path.exists(candidate):
                audio_path = candidate
                break
        else:
            raise RuntimeError("Audio file was not created. Download may have failed silently.")

    return {
        "title": info.get("title", "Unknown Title"),
        "channel": info.get("channel", info.get("uploader", "Unknown Channel")),
        "duration": info.get("duration", 0),
        "upload_date": info.get("upload_date", ""),
        "audio_path": audio_path,
    }


async def extract_playlist_urls(playlist_url: str, max_videos: int = 50) -> dict:
    """Extract video URLs from a YouTube playlist or channel using yt-dlp.

    Returns dict with: playlist_title, urls, total_available
    Raises RuntimeError with descriptive message on failure.
    """
    max_videos = min(max_videos, 200)

    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "-j",
        "--no-warnings",
        playlist_url,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=120
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("Playlist extraction timed out after 120s. The playlist may be very large.")

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        if "Private" in error_msg:
            raise RuntimeError("This playlist is private and cannot be accessed.")
        elif "HTTP Error 429" in error_msg:
            raise RuntimeError("YouTube is rate-limiting requests. Please wait a few minutes and try again.")
        elif "Unable to extract" in error_msg or "is not a valid URL" in error_msg:
            raise RuntimeError(f"Could not process this URL. It may not be a valid playlist or channel. Error: {error_msg[:200]}")
        else:
            raise RuntimeError(f"Playlist extraction failed: {error_msg[:300]}")

    stdout_text = stdout.decode().strip()
    if not stdout_text:
        raise RuntimeError("No videos found in this playlist or channel.")

    entries = []
    playlist_title = ""
    for line in stdout_text.split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not playlist_title:
            playlist_title = entry.get("playlist_title", entry.get("title", ""))
        video_id = entry.get("id")
        if video_id:
            entries.append(video_id)

    if not entries:
        raise RuntimeError("No valid video entries found in playlist.")

    urls = [f"https://www.youtube.com/watch?v={vid}" for vid in entries[:max_videos]]

    return {
        "playlist_title": playlist_title or "Unknown Playlist",
        "urls": urls,
        "total_available": len(entries),
    }


async def transcribe_audio(audio_path: str) -> list[dict]:
    """Transcribe audio file using Whisper. Returns list of segments with timestamps.

    Runs Whisper in a subprocess so that torch/whisper memory is fully
    reclaimed by the OS when transcription completes.
    """
    import sys

    worker = Path(__file__).parent / "whisper_worker.py"
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(worker), audio_path, settings.whisper_model,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    from .jobs import set_active_process
    set_active_process(process)
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=settings.transcription_timeout_seconds
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(
            f"Transcription timed out after {settings.transcription_timeout_seconds}s. "
            "Try a shorter video, a smaller Whisper model, or increase TRANSCRIPTION_TIMEOUT_SECONDS."
        )
    finally:
        set_active_process(None)

    stderr_text = stderr.decode().strip()
    if stderr_text:
        log_level = logging.ERROR if process.returncode != 0 else logging.DEBUG
        logger.log(log_level, f"Whisper stderr: {stderr_text[:1000]}")

    if process.returncode != 0:
        raise RuntimeError(f"Whisper transcription failed: {stderr_text[:500]}")

    stdout_text = stdout.decode().strip()
    if not stdout_text:
        raise RuntimeError(f"Whisper produced no output. stderr: {stderr_text[:500]}")

    try:
        segments = json.loads(stdout_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Whisper output is not valid JSON: {e}. "
            f"stdout starts with: {stdout_text[:200]!r}"
        )
    return segments


def cleanup_audio(audio_path: str) -> None:
    """Delete temporary audio file."""
    try:
        if os.path.exists(audio_path):
            os.remove(audio_path)
    except OSError as e:
        logger.warning(f"Failed to clean up audio file {audio_path}: {e}")


def format_transcript_text(segments: list[dict]) -> str:
    """Convert transcript segments into readable text with timestamps."""
    lines = []
    for seg in segments:
        minutes = int(seg["start"] // 60)
        seconds = int(seg["start"] % 60)
        lines.append(f"[{minutes:02d}:{seconds:02d}] {seg['text']}")
    return "\n".join(lines)
