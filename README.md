# YouTube Transcriber

A self-hosted web app that downloads YouTube videos, transcribes them locally with Whisper, and analyzes transcripts with Claude AI.

## Features

- **Local transcription** — Whisper runs on your machine, no external transcription API
- **AI-powered analysis** — Automatic baseline analysis (outline, summary, tags) plus on-demand deep analysis packages
- **Content profiles** — Podcast, tutorial, lecture, interview — with custom analysis hints
- **Tag system** — Auto-generated and user-created tags with per-channel rejection tracking
- **Watch Later** — Bookmark transcripts for later viewing, filterable in the library
- **Library** — Browse and filter transcripts by channel, profile, tag, or watch-later status
- **Processing stats** — Word count, pacing score, info density, token usage, estimated cost
- **Batch submission** — Submit up to 20 URLs at once
- **Cross-analysis** — Analyze patterns across multiple transcripts

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.11+ |
| Transcription | OpenAI Whisper (local) |
| AI Analysis | Claude API (Anthropic) |
| Database | SQLite (async via aiosqlite) |
| Download | yt-dlp |
| Frontend | Vanilla HTML/CSS/JS, Jinja2 templates |

## Prerequisites

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) (required by Whisper)
- An [Anthropic API key](https://console.anthropic.com/)

## Setup

```bash
# Clone the repository
git clone <repo-url>
cd Youtube-Transcriber

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set your ANTHROPIC_API_KEY

# Run the server
python run.py
```

The app starts at **http://localhost:8765**.

## Configuration

All settings are loaded from `.env` via Pydantic Settings.

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Claude API key |
| `WHISPER_MODEL` | `medium` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` |
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Claude model for analysis |
| `AI_PROVIDER` | `claude` | AI provider (currently only `claude`) |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8765` | Server port |
| `TRANSCRIPTION_TIMEOUT_SECONDS` | `3600` | Timeout for Whisper transcription |
| `DOWNLOAD_TIMEOUT_SECONDS` | `600` | Timeout for yt-dlp download |

## Project Structure

```
app/
├── ai/                  # Claude API abstraction (provider pattern)
│   ├── base.py          # BaseAIProvider interface
│   ├── claude.py        # Claude implementation with prompt caching
│   ├── provider.py      # Provider factory
│   └── prompts.py       # Analysis prompt templates
├── models/
│   └── schemas.py       # Pydantic request/response models
├── repositories/        # Data access layer (repository pattern)
│   ├── base.py          # Abstract interface
│   └── sqlite.py        # SQLite implementation
├── routers/
│   ├── api.py           # REST API endpoints
│   └── pages.py         # HTML page routes
├── services/
│   ├── analysis.py      # Analysis packages and orchestration
│   ├── jobs.py          # Background job queue (sequential processing)
│   ├── cross_analysis.py# Multi-transcript cross-analysis
│   ├── transcription.py # yt-dlp download + Whisper transcription
│   └── whisper_worker.py# Subprocess worker for memory-efficient transcription
├── static/              # CSS and JS
├── templates/           # Jinja2 HTML templates
├── config.py            # Settings from .env
└── main.py              # FastAPI app initialization and lifespan
run.py                   # Entry point
requirements.txt
.env.example
```

## How It Works

1. **Submit** a YouTube URL through the web UI
2. **Download** — yt-dlp extracts audio as MP3
3. **Transcribe** — Whisper runs in a subprocess, producing timestamped segments
4. **Analyze** — Claude generates a baseline analysis (outline, summary, auto-tags)
5. **Browse** — View the transcript, run additional analysis packages, manage tags

Jobs process sequentially in a background queue. Whisper runs in a subprocess so its memory (torch + model weights) is fully reclaimed after each transcription.

## Analysis Packages

### Automatic (on every transcript)
- **Baseline** — Structural outline with timestamps, summary, auto-tags, executive briefing

### On-Demand
| Package | Analyses |
|---------|----------|
| **Full Scan** | Content vs. fluff, named entities, info density scoring |
| **Deep Extraction** | Section summaries, quote extraction, argument mapping, credibility flags |
| **Research Scan** | Question extraction, resource extraction, novelty scoring |
| **Section Deep-Dive** | Targeted deep analysis of a single section |

Results are cached in the database — rerunning a package returns the stored result.

## API Endpoints

All endpoints are prefixed with `/api`.

### Transcripts
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/transcripts` | Submit a URL for transcription |
| `POST` | `/transcripts/batch` | Submit up to 20 URLs |
| `GET` | `/transcripts` | List transcripts (filters: `channel`, `profile_id`, `tag`, `watch_later`, `limit`) |
| `GET` | `/transcripts/{id}` | Get transcript details |
| `GET` | `/transcripts/{id}/status` | Get processing status |
| `POST` | `/transcripts/check-urls` | Check for duplicate URLs before submission |
| `POST` | `/transcripts/{id}/cancel` | Cancel a pending or in-progress transcript |
| `POST` | `/transcripts/{id}/retry` | Retry a failed or cancelled transcript |
| `POST` | `/transcripts/retry-errors` | Bulk retry all errored transcripts |
| `DELETE` | `/transcripts/{id}` | Delete transcript and all related data |

### Analysis
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/transcripts/{id}/baseline` | Get baseline analysis |
| `POST` | `/transcripts/{id}/analyze-package` | Run an analysis package |
| `POST` | `/transcripts/{id}/section-deep-dive` | Deep-dive on a section |
| `GET` | `/transcripts/{id}/analysis/{type}` | Get a specific analysis result |
| `GET` | `/transcripts/{id}/analyses` | Get all analysis results |
| `GET` | `/analysis-packages` | List available packages |

### Tags
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/tags` | List all tags with usage counts |
| `GET` | `/transcripts/{id}/tags` | Get tags for a transcript |
| `POST` | `/transcripts/{id}/tags` | Add a tag |
| `DELETE` | `/transcripts/{id}/tags/{tag_id}` | Remove a tag |
| `POST` | `/transcripts/{id}/tags/{tag_id}/reject` | Reject an auto-tag |

### Cross-Analysis
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/cross-analysis` | Run cross-analysis on multiple transcripts |
| `GET` | `/cross-analysis/{id}` | Get cross-analysis result |

### Other
| Method | Path | Description |
|--------|------|-------------|
| `PATCH` | `/transcripts/{id}/watch-later` | Toggle watch-later flag |
| `GET` | `/channels` | List channels with transcript counts |
| `GET` | `/profiles` | List content profiles |
| `POST` | `/profiles` | Create a profile |
| `DELETE` | `/profiles/{id}` | Delete a profile |
