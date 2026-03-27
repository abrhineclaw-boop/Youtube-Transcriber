"""Cross-transcript analysis — analyze multiple transcripts together."""

import json
import logging
import re

from ..ai.base import BaseAIProvider, ModelConfig
from ..ai.prompts import cross_analysis_prompt, regenerate_concept_map_prompt
from ..repositories.base import BaseRepository

logger = logging.getLogger(__name__)


async def run_cross_analysis(
    transcript_ids: list[int],
    instructions: str,
    repo: BaseRepository,
    ai: BaseAIProvider,
) -> dict:
    """Run an analysis across multiple transcripts based on user instructions.

    Gathers executive briefings and baseline summaries for all selected
    transcripts, then sends them to the AI with the user's instructions.
    """
    if len(transcript_ids) < 2:
        raise ValueError("At least 2 transcripts required for cross-analysis")

    # Gather source material from each transcript
    sources = []
    for tid in transcript_ids:
        transcript = await repo.get_transcript(tid)
        if not transcript:
            raise ValueError(f"Transcript {tid} not found")
        if transcript["status"] != "ready":
            raise ValueError(f"Transcript {tid} is not ready")

        title = transcript["title"] or transcript["video_url"]
        channel = transcript["channel"] or "Unknown"

        # Get executive briefing
        briefing_result = await repo.get_analysis_result(tid, "executive_briefing")
        briefing = ""
        if briefing_result:
            parsed = json.loads(briefing_result["result_json"])
            if isinstance(parsed, list):
                briefing = "\n".join(f"- {b}" for b in parsed)
            elif isinstance(parsed, str):
                briefing = parsed

        # Get baseline summary
        baseline = await repo.get_baseline_analysis(tid)
        summary = baseline["summary"] if baseline else ""

        sources.append({
            "transcript_id": tid,
            "title": title,
            "channel": channel,
            "briefing": briefing,
            "summary": summary,
        })

    # Build the input text
    source_text = ""
    for i, s in enumerate(sources, 1):
        source_text += f"\n--- Source {i}: {s['title']} (by {s['channel']}) ---\n"
        if s["briefing"]:
            source_text += f"Executive Briefing:\n{s['briefing']}\n"
        if s["summary"]:
            source_text += f"Summary:\n{s['summary']}\n"

    prompt = cross_analysis_prompt(instructions)
    config = ModelConfig(
        model=ai.default_config.model,
        max_tokens=8192,
        temperature=0.3,
    )

    result = await ai.analyze(prompt, source_text, config)

    # Parse the JSON response
    if not result.text or not result.text.strip():
        raise ValueError("AI returned an empty response for cross-analysis")
    try:
        parsed = json.loads(result.text)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', result.text, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
        else:
            raise ValueError(f"Failed to parse cross-analysis response as JSON: {result.text[:200]}")

    # Save to database
    result_id = await repo.save_cross_analysis(
        analysis_type="custom",
        transcript_ids=transcript_ids,
        result_json=json.dumps({**parsed, "_instructions": instructions}),
    )

    return {
        "id": result_id,
        "analysis_type": "custom",
        "result": parsed,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
    }


async def regenerate_cross_analysis_concept_map(
    cross_analysis_id: int,
    repo: BaseRepository,
    ai: BaseAIProvider,
) -> dict:
    """Regenerate just the concept map for an existing cross-analysis.

    Uses the existing report content as input — no need to re-gather
    source transcripts.
    """
    existing = await repo.get_cross_analysis(cross_analysis_id)
    if not existing:
        raise ValueError(f"Cross-analysis {cross_analysis_id} not found")

    result_data = json.loads(existing["result_json"])

    # Build input from the existing report
    input_text = ""
    if result_data.get("report_title"):
        input_text += f"Report Title: {result_data['report_title']}\n\n"
    if result_data.get("summary"):
        input_text += f"Summary: {result_data['summary']}\n\n"
    for section in result_data.get("sections", []):
        input_text += f"--- {section.get('heading', 'Section')} ---\n{section.get('content', '')}\n\n"

    prompt = regenerate_concept_map_prompt()
    config = ModelConfig(
        model=ai.default_config.model,
        max_tokens=2048,
        temperature=0.5,
    )

    ai_result = await ai.analyze(prompt, input_text, config)

    if not ai_result.text or not ai_result.text.strip():
        raise ValueError("AI returned an empty response")

    try:
        concept_map = json.loads(ai_result.text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', ai_result.text, re.DOTALL)
        if match:
            concept_map = json.loads(match.group())
        else:
            raise ValueError("Failed to parse concept map response as JSON")

    # Update result_json in place
    result_data["concept_map"] = concept_map
    await repo.update_cross_analysis_result(
        cross_analysis_id, json.dumps(result_data)
    )

    return {
        "concept_map": concept_map,
        "input_tokens": ai_result.input_tokens,
        "output_tokens": ai_result.output_tokens,
    }
