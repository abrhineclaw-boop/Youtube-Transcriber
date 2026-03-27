# YouTube Transcriber — Action Plan

**Project:** YouTube Video Transcriber & Analysis Tool
**Date:** March 18, 2026

---

## Project Summary

A self-hosted web application running on a Mac Mini (M4, 16GB RAM) that downloads YouTube audio, transcribes it locally using Whisper, stores transcripts in a SQLite database, and provides on-demand AI-powered analysis through a browser-based UI accessible over Tailscale from any device.

---

## Architecture Overview

- **Platform:** Python backend (Flask or FastAPI) + web frontend
- **Host:** Mac Mini (M4, 16GB RAM) — runs Whisper, web server, SQLite
- **Access:** Local web UI at a local port, reachable from PC via Tailscale
- **Transcription:** OpenAI Whisper (medium model, local)
- **Audio Download:** yt-dlp
- **Database:** SQLite (designed for future PostgreSQL migration)
- **AI Analysis:** TBD — abstracted behind a provider-agnostic wrapper so the decision can be deferred
- **Note:** OpenClaw also runs on this Mac Mini but is lightly used; RAM headroom is sufficient

---

## Data Model

### Tables (initial design)

- **transcripts** — video URL, title, channel, duration, raw transcript (JSON with timestamps), date added, profile_id
- **profiles** — name (e.g., "podcast", "tutorial", "lecture", "interview"), description, hints/expectations for structural analysis
- **channel_profiles** — channel name/ID → default profile mapping, learned over time from user selections
- **baseline_analysis** — transcript_id, structural outline (JSON with section titles + timestamps), overall summary
- **analysis_results** — transcript_id, analysis_type, result content (JSON), date run
- **profile_grades** — channel_profiles entry, auto-selected profile, user grade (for feedback loop on auto-detection)

Design the data access layer with a clean abstraction so the SQLite-to-PostgreSQL migration is a configuration change, not a rewrite.

---

## Core Workflow

1. User opens web UI from any device (via Tailscale)
2. Pastes a YouTube URL, selects a profile (or accepts auto-suggested profile if channel has history)
3. System downloads audio via yt-dlp, transcribes with Whisper medium, stores in SQLite
4. Baseline analysis runs automatically: reconstructs the content outline/structure with timestamps, generates overall summary
5. Transcript appears in the library

---

## Web UI

### Library View (main screen)
- List of all transcripts in the library (title, channel, date, duration)
- Indicators showing which additional analyses have been run on each transcript
- Input area to submit new YouTube URLs with profile selection

### Transcript Detail View
- Displays baseline info: title, overall summary, structural outline with timestamps
- Section of buttons for on-demand analysis (only run what you need, minimize API costs)
- Indicators for which analyses have already been completed

### Analysis View (separate from detail view)
- Opens in its own tab/window/panel — keeps the main view uncluttered
- Displays results of a specific analysis type for the selected transcript

### V1 UI Priority
- Functional and clean, not fancy
- Prioritize clarity and usability over aesthetics

---

## Profile System

- Profiles define what type of content the video is (podcast, tutorial, lecture, interview, etc.)
- Each profile carries hints that guide how the baseline structural analysis interprets the transcript
- User manually selects a profile when submitting a URL
- System stores channel → profile associations in the database
- Over time, system auto-suggests profiles for known channels
- User can grade the auto-selection, feeding back into the learning loop
- Profile list and behavior are extensible

---

## Analysis Types

### Baseline (runs automatically on every transcript)
- Reconstruct the creator's outline/structure from the transcript
- Identify sections with timestamps
- Generate one overall summary
- This structural scaffolding enables all further analysis to target specific sections

### On-Demand (user triggers via buttons)
- Summarization (per-section or custom)
- Topic extraction
- Sentiment/tone analysis
- Speaker identification (skip if single-speaker video)
- Action item extraction
- Quote/claim extraction
- Content vs. fluff mapping (identify where to start watching, where substance ends)
- Domain-specific extraction (configurable per profile)
- This list is extensible

---

## AI Integration

- Abstract all AI calls behind a provider-agnostic wrapper (e.g., `analyze(prompt, text, model_config)`)
- Defer the provider decision (Claude API, OpenAI, local via Ollama, etc.)
- Design prompts to work with the profile system — profile context gets injected into analysis prompts
- For long transcripts (over ~30 min), chunk at section boundaries identified by baseline analysis rather than arbitrary character limits

---

## Technical Dependencies

- Python 3.11+
- Flask or FastAPI
- yt-dlp
- openai-whisper (medium model)
- SQLite (with migration path to PostgreSQL)
- AI SDK (TBD)
- Frontend: HTML/CSS/JS (framework TBD — keep it simple for v1)

---

## V1 Scope

- [ ] yt-dlp audio download from YouTube URL
- [ ] Whisper medium transcription with timestamps
- [ ] SQLite database with migration-ready schema
- [ ] Profile system (manual selection, channel association storage)
- [ ] Baseline analysis pipeline (structure + summary)
- [ ] Web UI: URL input, library view, transcript detail view, analysis buttons
- [ ] At least 2-3 on-demand analysis types wired up
- [ ] AI provider abstraction layer
- [ ] Accessible over Tailscale

## Out of Scope for V1

- PostgreSQL migration (designed for, not implemented)
- Auto-detection/suggestion of profiles (channel associations stored but auto-suggest deferred)
- Profile grading feedback loop
- Polished/fun UI

---

## Fun UI Ideas (for later)

*Parking lot for ideas to make the interface enjoyable to use. Not a V1 concern.*

- (Add ideas here as they come up)

---

## Open Decisions

- Which AI provider to use for analysis
- Frontend framework (or vanilla JS)
- Flask vs. FastAPI
- Specific on-demand analysis types to wire up for v1
