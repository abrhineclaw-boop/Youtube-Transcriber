"""API routes for the YouTube Transcriber."""

import json
from fastapi import APIRouter, HTTPException, Request

from ..models.schemas import (
    SubmitURLRequest,
    SubmitURLResponse,
    SubmitBatchRequest,
    SubmitBatchResponse,
    RunAnalysisRequest,
    RunPackageRequest,
    SectionDeepDiveRequest,
    CrossAnalysisRequest,
    PlaylistImportRequest,
    PlaylistImportResponse,
    PlaylistPreviewRequest,
    PlaylistPreviewResponse,
)
from ..services.jobs import enqueue_job, cancel_job
from ..services.transcription import extract_playlist_urls
from ..services.analysis import (
    run_package_analysis,
    run_section_deep_dive,
    ANALYSIS_PACKAGES,
    ANALYSIS_TYPES,
    ANALYSIS_TYPE_META,
)
from ..services.cross_analysis import run_cross_analysis, regenerate_cross_analysis_concept_map
from ..ai.provider import get_ai_provider

router = APIRouter(prefix="/api")


def get_repo(request: Request):
    return request.app.state.repo


# --- Profiles ---
@router.get("/profiles")
async def list_profiles(request: Request):
    repo = get_repo(request)
    profiles = await repo.get_profiles()
    return profiles


@router.post("/profiles")
async def create_profile(request: Request):
    repo = get_repo(request)
    body = await request.json()
    profile_id = await repo.create_profile(
        name=body["name"],
        description=body.get("description", ""),
        analysis_hints=body.get("analysis_hints", ""),
    )
    return {"id": profile_id}


@router.delete("/profiles/{profile_id}")
async def delete_profile(request: Request, profile_id: int):
    repo = get_repo(request)
    profile = await repo.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    deleted = await repo.delete_profile(profile_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="Cannot delete profile that has transcripts")
    return {"message": "Profile deleted"}


# --- URL Duplicate Check ---
@router.post("/transcripts/check-urls")
async def check_urls(request: Request):
    """Check if any of the given URLs have already been transcribed."""
    repo = get_repo(request)
    body = await request.json()
    urls = body.get("video_urls", [])
    if not urls:
        return {"duplicates": {}}
    existing = await repo.get_transcripts_by_urls(urls)
    duplicates = {}
    for t in existing:
        url = t["video_url"]
        # Keep the most recent entry per URL (highest id)
        if url not in duplicates or t["id"] > duplicates[url]["id"]:
            duplicates[url] = {"id": t["id"], "title": t["title"], "status": t["status"]}
    return {"duplicates": duplicates}


# --- Transcripts ---
@router.post("/transcripts")
async def submit_url(request: Request, body: SubmitURLRequest):
    repo = get_repo(request)

    # Validate profile exists
    profile = await repo.get_profile(body.profile_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Invalid profile_id")

    transcript_id = await repo.create_transcript(
        video_url=body.video_url,
        profile_id=body.profile_id,
    )

    # Enqueue background job (processed sequentially)
    await enqueue_job(transcript_id, repo)

    return SubmitURLResponse(
        transcript_id=transcript_id,
        status="pending",
        message="Transcription job started",
    )


@router.post("/transcripts/batch")
async def submit_batch(request: Request, body: SubmitBatchRequest):
    repo = get_repo(request)

    if not body.video_urls:
        raise HTTPException(status_code=400, detail="No URLs provided")
    if len(body.video_urls) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 URLs per batch")

    profile = await repo.get_profile(body.profile_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Invalid profile_id")

    transcript_ids = []
    for url in body.video_urls:
        tid = await repo.create_transcript(video_url=url, profile_id=body.profile_id)
        await enqueue_job(tid, repo)
        transcript_ids.append(tid)

    return SubmitBatchResponse(
        transcript_ids=transcript_ids,
        message=f"{len(transcript_ids)} transcription jobs started",
    )


# --- Playlist Import ---
@router.post("/transcripts/preview-playlist")
async def preview_playlist(request: Request, body: PlaylistPreviewRequest):
    """Preview videos in a playlist/channel before importing."""
    repo = get_repo(request)
    try:
        result = await extract_playlist_urls(body.playlist_url, body.max_videos)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    urls = result["urls"]
    existing = await repo.get_transcripts_by_urls(urls)
    duplicates = {}
    for t in existing:
        url = t["video_url"]
        if url not in duplicates or t["id"] > duplicates[url]["id"]:
            duplicates[url] = {"id": t["id"], "title": t["title"], "status": t["status"]}

    return PlaylistPreviewResponse(
        playlist_title=result["playlist_title"],
        total_in_playlist=result["total_available"],
        video_count=len(urls),
        urls=urls,
        duplicates=duplicates,
    )


@router.post("/transcripts/import-playlist")
async def import_playlist(request: Request, body: PlaylistImportRequest):
    """Import all videos from a YouTube playlist or channel."""
    repo = get_repo(request)

    profile = await repo.get_profile(body.profile_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Invalid profile_id")

    try:
        result = await extract_playlist_urls(body.playlist_url, body.max_videos)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    urls = result["urls"]
    if not urls:
        raise HTTPException(status_code=400, detail="No videos found in playlist")

    # Check for duplicates — skip URLs that are already pending or ready
    existing = await repo.get_transcripts_by_urls(urls)
    skip_urls = set()
    for t in existing:
        if t["status"] in ("pending", "downloading", "transcribing", "analyzing", "ready"):
            skip_urls.add(t["video_url"])

    transcript_ids = []
    for url in urls:
        if url in skip_urls:
            continue
        tid = await repo.create_transcript(video_url=url, profile_id=body.profile_id)
        await enqueue_job(tid, repo)
        transcript_ids.append(tid)

    queued = len(transcript_ids)
    skipped = len(skip_urls)

    return PlaylistImportResponse(
        playlist_title=result["playlist_title"],
        total_in_playlist=result["total_available"],
        queued_count=queued,
        skipped_duplicates=skipped,
        transcript_ids=transcript_ids,
        message=f"Queued {queued} video(s) from '{result['playlist_title']}'"
               + (f" ({skipped} duplicate(s) skipped)" if skipped else ""),
    )


@router.get("/transcripts")
async def list_transcripts(request: Request, channel: str | None = None, profile_id: int | None = None, tag: str | None = None, watch_later: bool | None = None, limit: int | None = None):
    repo = get_repo(request)
    transcripts = await repo.get_all_transcripts(channel=channel, profile_id=profile_id, tag=tag, watch_later=watch_later, limit=limit)
    return transcripts


@router.get("/channels")
async def list_channels(request: Request):
    repo = get_repo(request)
    return await repo.get_channels()


@router.get("/transcripts/{transcript_id}")
async def get_transcript(request: Request, transcript_id: int):
    repo = get_repo(request)
    transcript = await repo.get_transcript(transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return transcript


@router.get("/transcripts/{transcript_id}/status")
async def get_transcript_status(request: Request, transcript_id: int):
    repo = get_repo(request)
    transcript = await repo.get_transcript(transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return {
        "transcript_id": transcript_id,
        "status": transcript["status"],
        "error_message": transcript.get("error_message"),
        "created_at": transcript.get("created_at"),
    }


# --- Baseline Analysis ---
@router.get("/transcripts/{transcript_id}/baseline")
async def get_baseline(request: Request, transcript_id: int):
    repo = get_repo(request)
    baseline = await repo.get_baseline_analysis(transcript_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline analysis not found")
    return baseline


# --- On-Demand Analysis ---
@router.get("/analysis-types")
async def list_analysis_types():
    """Legacy endpoint — returns flat analysis type list."""
    return {
        key: {"label": info["label"], "description": info.get("description", "")}
        for key, info in ANALYSIS_TYPES.items()
    }


@router.get("/analysis-packages")
async def list_analysis_packages():
    """Returns package definitions with their analysis types."""
    return {
        key: {
            "label": pkg["label"],
            "description": pkg["description"],
            "trigger": pkg["trigger"],
            "analysis_types": pkg["analysis_types"],
        }
        for key, pkg in ANALYSIS_PACKAGES.items()
    }


@router.post("/transcripts/{transcript_id}/analyze-package")
async def run_package(request: Request, transcript_id: int, body: RunPackageRequest):
    """Run an analysis package — one API call, multiple results."""
    repo = get_repo(request)

    transcript = await repo.get_transcript(transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    if transcript["status"] != "ready":
        raise HTTPException(status_code=400, detail="Transcript is not ready for analysis")

    ai = get_ai_provider()
    try:
        result = await run_package_analysis(transcript_id, body.package, repo, ai)
        return {
            "package": body.package,
            "analysis_types": list(result.get("analysis_types", {}).keys()),
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Package analysis failed: {str(e)[:200]}")


@router.post("/transcripts/{transcript_id}/section-deep-dive")
async def section_deep_dive(request: Request, transcript_id: int, body: SectionDeepDiveRequest):
    """Deep-dive analysis on a single section."""
    repo = get_repo(request)

    transcript = await repo.get_transcript(transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    if transcript["status"] != "ready":
        raise HTTPException(status_code=400, detail="Transcript is not ready for analysis")

    ai = get_ai_provider()
    try:
        result = await run_section_deep_dive(transcript_id, body.section_index, repo, ai)
        return result["result"]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Section deep-dive failed: {str(e)[:200]}")


# Legacy: individual analysis endpoint (still works, runs full package)
@router.post("/transcripts/{transcript_id}/analyze")
async def run_analysis(request: Request, transcript_id: int, body: RunAnalysisRequest):
    """Legacy — triggers the package containing this analysis type."""
    repo = get_repo(request)

    transcript = await repo.get_transcript(transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    if transcript["status"] != "ready":
        raise HTTPException(status_code=400, detail="Transcript is not ready for analysis")

    # Find which package contains this type
    meta = ANALYSIS_TYPE_META.get(body.analysis_type)
    if not meta or not meta.get("package"):
        raise HTTPException(status_code=400, detail=f"Unknown analysis type: {body.analysis_type}")

    ai = get_ai_provider()
    try:
        result = await run_package_analysis(transcript_id, meta["package"], repo, ai)
        # Return the specific type's result
        stored = await repo.get_analysis_result(transcript_id, body.analysis_type)
        if stored:
            return json.loads(stored["result_json"])
        return result.get("analysis_types", {}).get(body.analysis_type, {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)[:200]}")


@router.get("/transcripts/{transcript_id}/analysis/{analysis_type}")
async def get_analysis(request: Request, transcript_id: int, analysis_type: str):
    repo = get_repo(request)
    result = await repo.get_analysis_result(transcript_id, analysis_type)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis result not found")
    return result


@router.get("/transcripts/{transcript_id}/analyses")
async def get_all_analyses(request: Request, transcript_id: int):
    repo = get_repo(request)
    results = await repo.get_analysis_results_for_transcript(transcript_id)
    return results


# --- Tags ---
@router.get("/tags")
async def list_tags(request: Request):
    repo = get_repo(request)
    return await repo.get_all_tags()


@router.get("/transcripts/{transcript_id}/tags")
async def get_transcript_tags(request: Request, transcript_id: int):
    repo = get_repo(request)
    return await repo.get_tags_for_transcript(transcript_id)


@router.post("/transcripts/{transcript_id}/tags")
async def add_tag(request: Request, transcript_id: int):
    repo = get_repo(request)
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tag name required")
    tag = await repo.add_tag_to_transcript(transcript_id, name, source="user")
    return tag


@router.delete("/transcripts/{transcript_id}/tags/{tag_id}")
async def remove_tag(request: Request, transcript_id: int, tag_id: int):
    repo = get_repo(request)
    await repo.remove_tag_from_transcript(transcript_id, tag_id)
    return {"message": "Tag removed"}


@router.post("/transcripts/{transcript_id}/tags/{tag_id}/reject")
async def reject_tag(request: Request, transcript_id: int, tag_id: int):
    repo = get_repo(request)
    await repo.reject_auto_tag(transcript_id, tag_id)
    return {"message": "Tag rejected"}


@router.post("/transcripts/{transcript_id}/tags/{tag_id}/confirm")
async def confirm_tag(request: Request, transcript_id: int, tag_id: int):
    repo = get_repo(request)
    await repo.confirm_auto_tag(transcript_id, tag_id)
    return {"message": "Tag confirmed"}


# --- Cancel ---
@router.post("/transcripts/{transcript_id}/cancel")
async def cancel_transcript(request: Request, transcript_id: int):
    """Cancel a pending or in-progress transcript job."""
    repo = get_repo(request)
    transcript = await repo.get_transcript(transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    active_statuses = ["pending", "downloading", "transcribing", "analyzing"]
    if transcript["status"] not in active_statuses:
        raise HTTPException(status_code=400, detail=f"Cannot cancel transcript with status: {transcript['status']}")
    cancel_job(transcript_id)
    # For pending jobs that haven't started yet, update status immediately
    if transcript["status"] == "pending":
        await repo.update_transcript(transcript_id, status="cancelled", error_message="Cancelled by user")
    return {"message": "Cancellation requested"}


# --- Retry ---
@router.post("/transcripts/{transcript_id}/retry")
async def retry_transcript(request: Request, transcript_id: int):
    """Retry a failed or cancelled transcript job."""
    repo = get_repo(request)
    transcript = await repo.get_transcript(transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    retryable = ["error", "cancelled", "downloading", "transcribing", "analyzing"]
    if transcript["status"] not in retryable:
        raise HTTPException(status_code=400, detail=f"Cannot retry transcript with status: {transcript['status']}")
    # Reset transcript state
    await repo.update_transcript(
        transcript_id,
        status="pending",
        error_message=None,
        transcript_json="[]",
        processing_stats="{}",
    )
    # Clear previous baseline analysis
    db = await repo._get_db()
    await db.execute("DELETE FROM baseline_analysis WHERE transcript_id = ?", (transcript_id,))
    await db.commit()
    await enqueue_job(transcript_id, repo)
    return {"message": "Retrying transcript"}


@router.post("/transcripts/retry-errors")
async def retry_all_errors(request: Request):
    """Retry all transcripts in error state."""
    repo = get_repo(request)
    db = await repo._get_db()
    cursor = await db.execute("SELECT id FROM transcripts WHERE status = 'error'")
    rows = await cursor.fetchall()
    count = 0
    for row in rows:
        tid = row["id"]
        await repo.update_transcript(
            tid,
            status="pending",
            error_message=None,
            transcript_json="[]",
            processing_stats="{}",
        )
        await db.execute("DELETE FROM baseline_analysis WHERE transcript_id = ?", (tid,))
        await enqueue_job(tid, repo)
        count += 1
    await db.commit()
    return {"retried": count}


# --- Watch Later ---
@router.patch("/transcripts/{transcript_id}/watch-later")
async def toggle_watch_later(request: Request, transcript_id: int):
    repo = get_repo(request)
    transcript = await repo.get_transcript(transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    new_value = 0 if transcript.get("watch_later") else 1
    await repo.update_transcript(transcript_id, watch_later=new_value)
    return {"watch_later": new_value}


# --- Delete transcript ---
@router.delete("/transcripts/{transcript_id}")
async def delete_transcript(request: Request, transcript_id: int):
    repo = get_repo(request)
    transcript = await repo.get_transcript(transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    db = await repo._get_db()
    await db.execute("DELETE FROM transcript_tags WHERE transcript_id = ?", (transcript_id,))
    await db.execute("DELETE FROM analysis_results WHERE transcript_id = ?", (transcript_id,))
    await db.execute("DELETE FROM baseline_analysis WHERE transcript_id = ?", (transcript_id,))
    await db.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))
    await db.commit()
    return {"message": "Transcript deleted"}


# --- Cross-Analysis ---
@router.post("/cross-analysis")
async def create_cross_analysis(request: Request, body: CrossAnalysisRequest):
    """Run an analysis across multiple transcripts."""
    repo = get_repo(request)
    if len(body.transcript_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 transcripts required")

    ai = get_ai_provider()
    try:
        result = await run_cross_analysis(body.transcript_ids, body.instructions, repo, ai)
        return {"id": result["id"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cross-analysis failed: {str(e)[:200]}")


@router.get("/cross-analyses")
async def list_cross_analyses(request: Request, limit: int | None = None):
    """List all cross-analysis results."""
    repo = get_repo(request)
    return await repo.get_all_cross_analyses(limit=limit)


@router.post("/cross-analysis/{cross_analysis_id}/regenerate-concept-map")
async def regenerate_concept_map(request: Request, cross_analysis_id: int):
    """Regenerate just the concept map for an existing cross-analysis."""
    repo = get_repo(request)
    ai = get_ai_provider()
    try:
        result = await regenerate_cross_analysis_concept_map(cross_analysis_id, repo, ai)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Concept map regeneration failed: {str(e)[:200]}")


@router.get("/cross-analysis/{cross_analysis_id}")
async def get_cross_analysis(request: Request, cross_analysis_id: int):
    repo = get_repo(request)
    result = await repo.get_cross_analysis(cross_analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Cross-analysis not found")
    return result
