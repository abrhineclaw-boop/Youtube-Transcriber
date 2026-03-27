"""Analysis service — runs packaged and individual analyses.

Analyses are grouped into packages that share a single API call,
reducing costs by 60-80% compared to standalone calls.
"""

import json
import logging
import re
from typing import Optional

from ..ai.base import BaseAIProvider, ModelConfig
from ..ai.prompts import (
    package_a_prompt,
    package_b_prompt,
    package_c_prompt,
    section_deep_dive_prompt,
    baseline_prompt,
)
from ..repositories.base import BaseRepository
from .transcription import format_transcript_text

logger = logging.getLogger(__name__)


# --- Package Definitions ---

ANALYSIS_PACKAGES = {
    "package_a": {
        "label": "Full Scan",
        "description": "Structural analysis, fluff mapping, entities, density scores, and executive briefing",
        "trigger": "automatic",
        "analysis_types": ["content_vs_fluff", "named_entities", "info_density", "executive_briefing"],
        "prompt_fn": package_a_prompt,
        "max_tokens": 8192,
    },
    "package_b": {
        "label": "Deep Extraction",
        "description": "Section summaries, quotes, argument mapping, and credibility analysis",
        "trigger": "on_demand",
        "analysis_types": ["section_summaries", "quote_extraction", "argument_mapping", "credibility_flags"],
        "prompt_fn": package_b_prompt,
        "max_tokens": 16384,
    },
    "package_c": {
        "label": "Research Scan",
        "description": "Questions, resources, and novelty scoring",
        "trigger": "on_demand",
        "analysis_types": ["question_extraction", "resource_extraction", "novelty_scoring"],
        "prompt_fn": package_c_prompt,
        "max_tokens": 8192,
    },
}

# Flat metadata for all analysis types (for UI display)
ANALYSIS_TYPE_META = {
    "content_vs_fluff": {"label": "Content vs. Fluff", "package": "package_a"},
    "named_entities": {"label": "Named Entities", "package": "package_a"},
    "info_density": {"label": "Info Density", "package": "package_a"},
    "executive_briefing": {"label": "Executive Briefing", "package": "package_a"},
    "section_summaries": {"label": "Section Summaries", "package": "package_b"},
    "quote_extraction": {"label": "Quote Extraction", "package": "package_b"},
    "argument_mapping": {"label": "Argument Mapping", "package": "package_b"},
    "credibility_flags": {"label": "Credibility Flags", "package": "package_b"},
    "question_extraction": {"label": "Questions", "package": "package_c"},
    "resource_extraction": {"label": "Resources", "package": "package_c"},
    "novelty_scoring": {"label": "Novelty", "package": "package_c"},
    "concept_map": {"label": "Concept Map", "package": "package_a"},
    "section_deep_dive": {"label": "Section Deep-Dive", "package": None},
}

# Keep legacy ANALYSIS_TYPES for backward compatibility with existing API
ANALYSIS_TYPES = {
    key: {"label": meta["label"], "description": f"Part of {ANALYSIS_PACKAGES[meta['package']]['label']}" if meta["package"] else "Standalone"}
    for key, meta in ANALYSIS_TYPE_META.items()
}


def _parse_json_response(text: str) -> dict:
    """Parse JSON from AI response with fallback regex extraction."""
    if not text or not text.strip():
        raise ValueError("AI returned an empty response — the model may have been rate-limited or the request was too large")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        logger.error(f"AI returned non-JSON response: {text[:500]}")
        raise ValueError(f"AI returned invalid JSON: {text[:200]}")


def _chunk_transcript_by_sections(
    transcript_text: str,
    outline: list[dict],
    segments: list[dict],
    max_duration_seconds: int = 1800,
) -> list[str]:
    """Chunk a long transcript at section boundaries."""
    if not outline:
        return [transcript_text]

    total_duration = segments[-1]["end"] if segments else 0
    if total_duration <= max_duration_seconds:
        return [transcript_text]

    chunks = []
    current_chunk_lines = []
    current_chunk_duration = 0

    for i, section in enumerate(outline):
        section_start = section.get("start_time", 0)
        section_end = section.get("end_time", total_duration)
        section_duration = section_end - section_start

        section_lines = []
        for seg in segments:
            if seg["start"] >= section_start and seg["start"] < section_end:
                minutes = int(seg["start"] // 60)
                seconds = int(seg["start"] % 60)
                section_lines.append(f"[{minutes:02d}:{seconds:02d}] {seg['text']}")

        if current_chunk_duration + section_duration > max_duration_seconds and current_chunk_lines:
            chunks.append("\n".join(current_chunk_lines))
            current_chunk_lines = []
            current_chunk_duration = 0

        current_chunk_lines.append(f"\n--- SECTION: {section.get('title', f'Section {i+1}')} ---\n")
        current_chunk_lines.extend(section_lines)
        current_chunk_duration += section_duration

    if current_chunk_lines:
        chunks.append("\n".join(current_chunk_lines))

    return chunks if chunks else [transcript_text]


def _chunk_by_time(segments: list[dict], max_duration_seconds: int = 1800) -> list[str]:
    """Simple time-based chunking for when no outline exists (Package A)."""
    if not segments:
        return [""]

    total_duration = segments[-1]["end"] if segments else 0
    if total_duration <= max_duration_seconds:
        return [format_transcript_text(segments)]

    chunks = []
    current_lines = []
    chunk_start = 0

    for seg in segments:
        if seg["start"] - chunk_start >= max_duration_seconds and current_lines:
            chunks.append("\n".join(current_lines))
            current_lines = []
            chunk_start = seg["start"]

        minutes = int(seg["start"] // 60)
        seconds = int(seg["start"] % 60)
        current_lines.append(f"[{minutes:02d}:{seconds:02d}] {seg['text']}")

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks


# --- Package Analysis ---

async def run_package_analysis(
    transcript_id: int,
    package_name: str,
    repo: BaseRepository,
    ai: BaseAIProvider,
) -> dict:
    """Run a bundled analysis package — one API call, multiple result rows.

    Returns dict with: analysis_types (dict of results), tags (list, Package A only),
    input_tokens, output_tokens.
    """
    if package_name not in ANALYSIS_PACKAGES:
        raise ValueError(f"Unknown package: {package_name}")

    package = ANALYSIS_PACKAGES[package_name]

    # Check if all types in this package are already completed
    existing_types = []
    for atype in package["analysis_types"]:
        existing = await repo.get_analysis_result(transcript_id, atype)
        if existing:
            existing_types.append(atype)

    if len(existing_types) == len(package["analysis_types"]):
        # For package_a, also check baseline
        if package_name == "package_a":
            baseline = await repo.get_baseline_analysis(transcript_id)
            if baseline:
                return {"analysis_types": {}, "tags": [], "input_tokens": 0, "output_tokens": 0}
        else:
            return {"analysis_types": {}, "input_tokens": 0, "output_tokens": 0}

    transcript = await repo.get_transcript(transcript_id)
    if not transcript:
        raise ValueError(f"Transcript {transcript_id} not found")

    profile = await repo.get_profile(transcript["profile_id"])
    profile_name = profile["name"] if profile else "general"
    profile_hints = profile["analysis_hints"] if profile else ""

    segments = json.loads(transcript["transcript_json"])
    text = format_transcript_text(segments)

    system_prompt = f"You are an expert content analyst specializing in {profile_name} content. {profile_hints}"
    analysis_instructions = package["prompt_fn"](profile_name, profile_hints)
    config = ModelConfig(
        model=ai.default_config.model,
        max_tokens=package["max_tokens"],
        temperature=0.3,
    )

    # Chunking
    if package_name == "package_a":
        chunks = _chunk_by_time(segments)
    else:
        baseline = await repo.get_baseline_analysis(transcript_id)
        outline = json.loads(baseline["outline_json"]) if baseline else []
        chunks = _chunk_transcript_by_sections(text, outline, segments)

    total_input = 0
    total_output = 0

    if len(chunks) == 1:
        ai_result = await ai.analyze_package(system_prompt, chunks[0], analysis_instructions, config)
        total_input = ai_result.input_tokens
        total_output = ai_result.output_tokens
        result = _parse_json_response(ai_result.text)
    else:
        # Multi-chunk: process each, merge
        all_results = []
        for i, chunk in enumerate(chunks):
            chunk_instructions = f"{analysis_instructions}\n\n(This is chunk {i+1} of {len(chunks)} from a long transcript)"
            ai_result = await ai.analyze_package(system_prompt, chunk, chunk_instructions, config)
            total_input += ai_result.input_tokens
            total_output += ai_result.output_tokens
            all_results.append(_parse_json_response(ai_result.text))
        result = _merge_package_results(package_name, all_results)

    # Save individual analysis results
    saved_types = {}
    for atype in package["analysis_types"]:
        if atype in result:
            await repo.save_analysis_result(
                transcript_id=transcript_id,
                analysis_type=atype,
                result_json=json.dumps(result[atype]),
            )
            saved_types[atype] = result[atype]

    # Package A: also save baseline and concept map
    tags = []
    if package_name == "package_a" and "baseline" in result:
        baseline_data = result["baseline"]
        outline = baseline_data.get("outline", [])
        summary = baseline_data.get("summary", "")
        tags = baseline_data.get("tags", [])

        await repo.save_baseline_analysis(
            transcript_id=transcript_id,
            outline_json=json.dumps(outline),
            summary=summary,
        )

        # Save concept map as a separate analysis result
        if "concept_map" in result:
            await repo.save_analysis_result(
                transcript_id=transcript_id,
                analysis_type="concept_map",
                result_json=json.dumps(result["concept_map"]),
            )

    ret = {
        "analysis_types": saved_types,
        "input_tokens": total_input,
        "output_tokens": total_output,
    }
    if package_name == "package_a":
        ret["tags"] = tags
    return ret


def _merge_package_results(package_name: str, results: list[dict]) -> dict:
    """Merge multi-chunk results for a package."""
    if not results:
        return {}

    merged = {}
    # Merge baseline (Package A only)
    if package_name == "package_a":
        all_outlines = []
        for r in results:
            b = r.get("baseline", {})
            all_outlines.extend(b.get("outline", []))
        merged["baseline"] = {
            "outline": all_outlines,
            "summary": results[-1].get("baseline", {}).get("summary", ""),
            "tags": results[-1].get("baseline", {}).get("tags", []),
        }
        # Use the last chunk's concept map (holistic view)
        for r in reversed(results):
            if "concept_map" in r:
                merged["concept_map"] = r["concept_map"]
                break

    # Merge list-type results by concatenating
    list_keys = {
        "content_vs_fluff": lambda r: {"segments": _concat_key(results, "content_vs_fluff", "segments"),
                                        **{k: results[-1].get("content_vs_fluff", {}).get(k) for k in
                                           ["optimal_start", "optimal_end", "substance_percentage", "filler_percentage", "summary"]}},
        "named_entities": lambda r: _concat_top_level(results, "named_entities"),
        "info_density": lambda r: _concat_top_level(results, "info_density"),
        "executive_briefing": lambda r: _concat_top_level(results, "executive_briefing"),
        "section_summaries": lambda r: _concat_key(results, "section_summaries", "section_summaries", wrap_key="section_summaries"),
        "quote_extraction": lambda r: {
            "extractions": _concat_key(results, "quote_extraction", "extractions"),
            "summary": results[-1].get("quote_extraction", {}).get("summary", ""),
        },
        "argument_mapping": lambda r: {
            "arguments": _concat_key(results, "argument_mapping", "arguments"),
            "summary": results[-1].get("argument_mapping", {}).get("summary", ""),
        },
        "credibility_flags": lambda r: {
            "flags": _concat_key(results, "credibility_flags", "flags"),
            "summary": results[-1].get("credibility_flags", {}).get("summary", ""),
        },
        "question_extraction": lambda r: {
            "questions": _concat_key(results, "question_extraction", "questions"),
        },
        "resource_extraction": lambda r: {
            "resources": _concat_key(results, "resource_extraction", "resources"),
        },
        "novelty_scoring": lambda r: {
            "topics": _concat_key(results, "novelty_scoring", "topics"),
            "overall_score": results[-1].get("novelty_scoring", {}).get("overall_score", 0),
            "summary": results[-1].get("novelty_scoring", {}).get("summary", ""),
        },
    }

    for key, merge_fn in list_keys.items():
        if any(key in r for r in results):
            merged[key] = merge_fn(results)

    return merged


def _concat_key(results: list[dict], outer_key: str, inner_key: str, wrap_key: str | None = None) -> list:
    """Concatenate a nested list across chunk results."""
    items = []
    for r in results:
        outer = r.get(outer_key, {})
        if isinstance(outer, dict):
            items.extend(outer.get(inner_key, []))
        elif isinstance(outer, list):
            items.extend(outer)
    if wrap_key:
        return {wrap_key: items}
    return items


def _concat_top_level(results: list[dict], key: str) -> list:
    """Concatenate a top-level list across chunk results."""
    items = []
    for r in results:
        val = r.get(key, [])
        if isinstance(val, list):
            items.extend(val)
    return items


# --- Section Deep-Dive ---

async def run_section_deep_dive(
    transcript_id: int,
    section_index: int,
    repo: BaseRepository,
    ai: BaseAIProvider,
) -> dict:
    """Deep-dive analysis on a single section."""
    analysis_type = f"section_deep_dive_{section_index}"

    # Check cache
    existing = await repo.get_analysis_result(transcript_id, analysis_type)
    if existing:
        return {"result": json.loads(existing["result_json"]), "input_tokens": 0, "output_tokens": 0}

    transcript = await repo.get_transcript(transcript_id)
    if not transcript:
        raise ValueError(f"Transcript {transcript_id} not found")

    baseline = await repo.get_baseline_analysis(transcript_id)
    if not baseline:
        raise ValueError("Baseline analysis required for section deep-dive")

    outline = json.loads(baseline["outline_json"])
    if section_index < 0 or section_index >= len(outline):
        raise ValueError(f"Section index {section_index} out of range (0-{len(outline)-1})")

    section = outline[section_index]
    section_title = section.get("title", f"Section {section_index + 1}")

    # Extract section text
    segments = json.loads(transcript["transcript_json"])
    section_segments = [
        s for s in segments
        if s["start"] >= section.get("start_time", 0) and s["start"] < section.get("end_time", float("inf"))
    ]
    section_text = format_transcript_text(section_segments)

    profile = await repo.get_profile(transcript["profile_id"])
    profile_name = profile["name"] if profile else "general"
    profile_hints = profile["analysis_hints"] if profile else ""

    prompt = section_deep_dive_prompt(profile_name, profile_hints, section_title)
    ai_result = await ai.analyze(prompt, section_text)
    result = _parse_json_response(ai_result.text)

    await repo.save_analysis_result(
        transcript_id=transcript_id,
        analysis_type=analysis_type,
        result_json=json.dumps(result),
    )

    return {
        "result": result,
        "input_tokens": ai_result.input_tokens,
        "output_tokens": ai_result.output_tokens,
    }


# --- Legacy compatibility ---

async def run_baseline_analysis(
    transcript_id: int,
    repo: BaseRepository,
    ai: BaseAIProvider,
) -> dict:
    """Legacy wrapper — runs Package A and returns baseline-compatible result."""
    result = await run_package_analysis(transcript_id, "package_a", repo, ai)
    return {
        "outline": [],  # saved directly by run_package_analysis
        "summary": "",
        "tags": result.get("tags", []),
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
    }
