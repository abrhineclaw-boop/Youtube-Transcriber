# YouTube Transcriber — Analysis Packages

**Project:** YouTube Video Transcriber & Analysis Tool
**Date:** March 19, 2026
**Companion to:** youtube-transcriber-prd.md, youtube-transcriber-action-plan.md

---

## Overview

This document defines the analysis package architecture for the YouTube Transcriber. Rather than running each analysis type as an independent API call (each paying full input token cost for the transcript), analyses are grouped into packages that share a single input payload. This reduces API costs by 60–80% compared to standalone calls.

---

## Cost Model

### Pricing Basis

All cost estimates use Claude Sonnet 4.6 as the default V1 provider.

- **Input tokens:** $3.00 per million tokens
- **Output tokens:** $15.00 per million tokens
- **Prompt caching:** Cache writes cost 1.25x base input; cache hits cost 0.1x base input (90% discount), with a 5-minute TTL

### Reference Transcript

Cost estimates throughout this document are based on a ~60-minute transcript, which produces approximately 18,000 input tokens. Shorter videos cost proportionally less. Videos over 30 minutes use section-boundary chunking from the baseline analysis rather than arbitrary splits.

### Why Packages Save Money

Each standalone API call pays the full input cost (~$0.054 for an 18K-token transcript). When analyses are bundled into a single call, the input is sent once and the prompt instructs the model to produce structured output for all analyses in the package. The marginal cost of adding an analysis to an existing package is only its output tokens.

| Scenario | Input cost | Output cost | Total |
|----------|-----------|-------------|-------|
| 5 analyses run separately | $0.054 × 5 = $0.270 | ~$0.120 | ~$0.390 |
| 5 analyses bundled in 1 call | $0.054 × 1 = $0.054 | ~$0.120 | ~$0.174 |

Savings scale with the number of analyses per package.

### Prompt Caching Opportunity

When multiple packages are run on the same transcript in sequence (e.g., Package A auto-runs, then the user triggers Package B), the transcript portion of the input is identical. With prompt caching enabled, Package B's input cost drops from $0.054 to ~$0.0054 (90% cache hit discount) if triggered within 5 minutes of Package A. Design the API wrapper to structure prompts with the transcript as a cacheable prefix and the analysis instructions as the variable suffix.

---

## Analysis Types — Complete Inventory

Each analysis type is listed with its input scope, estimated output size, standalone cost, and marginal cost when bundled with other full-transcript analyses.

### Full-Transcript Analyses

These all require the complete transcript as input (~18K tokens for a 60-min video).

| Analysis Type | Est. Output | Standalone Cost | Marginal if Bundled | Notes |
|--------------|-------------|----------------|-------------------|-------|
| Baseline (structure + summary) | ~2K tokens | $0.084 | $0.030 | Reconstructs creator's outline with section titles + timestamps, generates overall summary. Foundation for all other analysis. |
| Per-section summarization | ~3K tokens | $0.099 | $0.045 | Concise summary for each section identified in baseline. Heavier output. |
| Content vs. fluff mapping | ~1.5K tokens | $0.077 | $0.023 | Identifies where substance starts/ends, flags filler/intro/outro, suggests optimal watch timestamps. |
| Named entity extraction | ~1K tokens | $0.069 | $0.015 | People, companies, places, products, technologies mentioned. Structured list with first-mention timestamps. |
| Info density scoring | ~1K tokens | $0.069 | $0.015 | Scores each section by value-per-minute. Helps prioritize what to watch or read. |
| Executive briefing | ~0.5K tokens | $0.062 | $0.008 | One-paragraph "what you need to know." Cheapest output of any analysis. |
| Quote / claim extraction | ~2.5K tokens | $0.092 | $0.038 | Notable quotes, specific claims, statistics, attributable statements with timestamps. |
| Argument mapping | ~3K tokens | $0.099 | $0.045 | What claims are made, what evidence supports them, logical structure. Heavier output. |
| Credibility flags | ~1.5K tokens | $0.077 | $0.023 | Unsupported claims, hedging language, contradictions, missing citations. |
| Novelty scoring | ~1.5K tokens | $0.077 | $0.023 | Is this saying something new vs. rehashing common knowledge? Useful for filtering signal from noise. |
| Question extraction | ~1K tokens | $0.069 | $0.015 | Questions asked during the video. Useful for interviews, Q&As, and educational content. |
| Resource / reference extraction | ~0.8K tokens | $0.066 | $0.012 | URLs, book titles, tools, papers, and other resources mentioned. |

### Section-Level Analyses

These operate on a single section (~4K tokens average) rather than the full transcript.

| Analysis Type | Est. Output | Standalone Cost | Notes |
|--------------|-------------|----------------|-------|
| Section deep-dive | ~1.5K tokens | $0.035 | Detailed analysis of one specific section. Triggered from the transcript detail view. |

---

## Package Definitions

### Package A: Full Scan

**Trigger:** Runs automatically on every new transcript after transcription completes.
**Input:** Full transcript (~18K tokens)
**Purpose:** Get the structural foundation and a quick assessment of every video without manual intervention.

**Included analyses:**
1. Baseline (structure + summary)
2. Content vs. fluff mapping
3. Named entity extraction
4. Info density scoring
5. Executive briefing

**Cost per run:**
- Bundled: ~$0.145 (one input + five outputs totaling ~6K tokens)
- If run separately: ~$0.361
- Savings: ~60%

**Output format:** Single structured JSON response with keys for each analysis type. The baseline section data becomes the scaffold referenced by all other analyses and packages.

**Design note:** This package defines the "zero-click value" of the system. After transcription, every video in the library immediately has a structural outline, a summary, a fluff map, entity list, density scores, and a briefing — before the user does anything.

---

### Package B: Deep Extraction

**Trigger:** On-demand, triggered by the user from the transcript detail view.
**Input:** Full transcript (~18K tokens)
**Purpose:** For videos worth digging into. Extracts claims, evidence, and detailed section content.

**Included analyses:**
1. Per-section summarization
2. Quote / claim extraction
3. Argument mapping
4. Credibility flags

**Cost per run:**
- Bundled: ~$0.205 (one input + four outputs totaling ~10K tokens)
- If run separately: ~$0.367
- Savings: ~44%

**Output format:** Structured JSON. Per-section summarization is keyed to the section IDs from the Package A baseline. Quote/claim extraction includes timestamps. Argument mapping references specific claims and their supporting evidence. Credibility flags cross-reference claims from the extraction.

**Design note:** This is the heaviest package on output tokens because argument mapping and section summaries produce substantial text. It's also the most valuable for substantive content where you want to understand the reasoning, not just the topics.

---

### Package C: Research Scan

**Trigger:** On-demand, triggered by the user from the transcript detail view.
**Input:** Full transcript (~18K tokens)
**Purpose:** For tutorials, educational content, and research-oriented videos. Extracts actionable references and evaluates novelty.

**Included analyses:**
1. Question extraction
2. Resource / reference extraction
3. Novelty scoring

**Cost per run:**
- Bundled: ~$0.104 (one input + three outputs totaling ~3.3K tokens)
- If run separately: ~$0.212
- Savings: ~51%

**Output format:** Structured JSON. Questions listed with timestamps and speaker context. Resources structured as a typed list (book, URL, tool, paper, person) with context for why they were mentioned. Novelty scoring evaluates each major topic against common knowledge baseline.

**Design note:** This is the cheapest on-demand package. Particularly useful for content where you want to quickly extract "what should I look up after watching this?"

---

### Section Deep-Dive (Standalone)

**Trigger:** On-demand, from a specific section in the transcript detail view.
**Input:** Single section (~4K tokens)
**Purpose:** Go deeper on one section without re-analyzing the whole transcript.

**Cost per run:** ~$0.035

**Design note:** This is not bundled because it operates on a different input scope. It's the cheapest possible analysis call. The UI should make it easy to trigger from any section in the baseline outline.

---

## Package Architecture — Implementation Guidance

### Prompt Structure

Each package should structure its API call as:

1. **System prompt** — role, output format instructions, profile context
2. **Transcript text** — the full transcript with timestamps (cacheable prefix)
3. **Analysis instructions** — the specific analyses to run in this package (variable suffix)

This structure enables prompt caching: the system prompt + transcript stay identical across packages, so Package B benefits from Package A's cached input if run within 5 minutes.

### Output Format

All packages return structured JSON with a top-level key for each analysis type:

```json
{
  "baseline": { "sections": [...], "summary": "..." },
  "content_fluff_map": { "segments": [...] },
  "entities": [...],
  "density_scores": { "sections": [...] },
  "executive_briefing": "..."
}
```

The API wrapper should parse this into individual `analysis_results` rows in the database, one per analysis type, so the UI can display and reference them independently even though they were produced in a single call.

### Adding New Analyses

To add a new analysis type:

1. Define the analysis: name, description, estimated output size, required input scope (full transcript or section-level)
2. Assign it to an existing package based on input scope and thematic fit, or create a new package if it represents a distinct use case
3. Add the analysis instructions to the package's prompt template
4. Add a corresponding key to the expected JSON output schema
5. Register the analysis type in the database so the UI displays the trigger button and completion indicator

The marginal cost of adding an analysis to an existing full-transcript package is only the additional output tokens. Adding a 1K-token output analysis to Package A costs ~$0.015 marginal — essentially free relative to the input cost already being paid.

### Cost Controls

- **On-demand packages (B, C) only run when the user triggers them.** This is the primary cost control — don't analyze what you don't need.
- **Package A runs automatically** but is designed to be cheap (~$0.145 per transcript). Budget for this as the per-video cost of using the system.
- **Section deep-dives** are very cheap ($0.035) and can be used freely without cost concern.
- **Prompt caching** reduces sequential package costs by ~90% on the input portion. Running Package B immediately after Package A on the same transcript drops Package B's input cost from $0.054 to ~$0.005.

### Future Package Ideas (Parking Lot)

- **Package D: Comparison** — cross-transcript analysis comparing topics, claims, or perspectives across multiple videos by the same or different creators. Different input scope (multiple transcripts), so this would be a new package category.
- **Package E: Domain-specific** — profile-driven extraction (e.g., real estate terms, financial data, regulatory mentions). Could be a modifier that adds domain-specific extraction to any existing package based on the video's profile.
- **Generative outputs** — newsletter drafts, thread/post summaries, study notes. These could be bundled or standalone depending on output size.

---

## Summary of Costs

For a single 60-minute transcript with all packages run:

| Package | Cost |
|---------|------|
| A: Full scan (automatic) | ~$0.145 |
| B: Deep extraction (on-demand) | ~$0.205 |
| C: Research scan (on-demand) | ~$0.104 |
| Section deep-dive (one section) | ~$0.035 |
| **Total (all packages)** | **~$0.489** |
| **With prompt caching (B + C after A)** | **~$0.39** |

For context: analyzing 10 videos per week with all packages costs roughly $3–5/month. Package A alone on 10 videos/week is about $1.50/month.
