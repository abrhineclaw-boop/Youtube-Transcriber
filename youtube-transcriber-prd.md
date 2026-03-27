# YouTube Transcriber — PRD

## Problem Statement

Watching long-form YouTube content (podcasts, tutorials, lectures, interviews) is time-consuming and inefficient. There's no easy way to get structured summaries, skip to the substantive parts, or extract specific insights without watching the entire video. Existing tools either require cloud-hosted transcription (privacy/cost concerns), lack structural analysis, or don't support on-demand targeted analysis.

Adam needs a self-hosted tool that transcribes YouTube videos locally, automatically reconstructs the content structure, and lets him run specific AI-powered analyses on demand — all accessible from any device over Tailscale.

## Solution

A self-hosted web application running on the Mac Mini (M4, 16GB) that:

- Downloads audio from any YouTube URL via yt-dlp
- Transcribes locally using Whisper (medium model) — no cloud transcription costs or data leaving the network
- Automatically generates a baseline structural analysis (outline with timestamps + summary) for every transcript
- Stores everything in SQLite with a clean abstraction layer designed for future PostgreSQL migration
- Provides a browser-based UI with a transcript library, detail views, and on-demand analysis buttons
- Uses the Claude API (via a provider-agnostic abstraction) for all AI-powered analysis
- Is accessible from any device on the Tailscale network — no app-level auth needed

When this is done, Adam can paste a YouTube URL, wait for transcription, and immediately see the video's structure and summary. He can then selectively run deeper analyses (section summaries, content-vs-fluff mapping, quote extraction) without watching the video or paying for analyses he doesn't need.

## User Stories

1. As the sole user, I want to paste a YouTube URL into the web UI and have the system download, transcribe, and store the transcript automatically, so that I don't need to manually handle any files.
2. As the sole user, I want to select a profile (podcast, tutorial, lecture, interview) when submitting a URL, so that the baseline analysis interprets the content structure appropriately for the content type.
3. As the sole user, I want the system to store channel-to-profile associations when I select a profile, so that the system can eventually auto-suggest profiles for channels I've transcribed before (auto-suggest is out of scope for V1, but the data should be captured now).
4. As the sole user, I want a baseline structural analysis to run automatically after transcription completes, so that every transcript in my library has an outline with timestamps and an overall summary without any extra action from me.
5. As the sole user, I want to see a library view listing all my transcripts with title, channel, date, duration, and indicators for which analyses have been run, so that I can quickly find and assess any transcript.
6. As the sole user, I want to open a transcript detail view showing the baseline summary, structural outline with timestamps, and buttons for on-demand analyses, so that I can decide what additional analysis to run.
7. As the sole user, I want to run per-section summarization on demand, so that I can get concise summaries of specific sections without reading the full transcript.
8. As the sole user, I want to run content-vs-fluff mapping on demand, so that I can identify where the substantive content starts and ends and skip filler.
9. As the sole user, I want to run quote/claim extraction on demand, so that I can pull out notable quotes and specific claims without searching through the transcript manually.
10. As the sole user, I want analysis results to open in a separate view (tab, window, or panel), so that the transcript detail view stays uncluttered and I can reference both simultaneously.
11. As the sole user, I want analysis results to be stored in the database after they're run, so that I don't pay for the same analysis twice and can revisit results later.
12. As the sole user, I want indicators on each transcript showing which on-demand analyses have already been completed, so that I know at a glance what's been run.
13. As the sole user, I want the system to chunk long transcripts (over ~30 minutes) at section boundaries identified by the baseline analysis rather than arbitrary character limits, so that AI analysis maintains coherent context.
14. As the sole user, I want to see clear error messages when yt-dlp fails (private video, region-locked, age-restricted, live stream, outdated yt-dlp), so that I understand why a download failed and can decide whether to retry.
15. As the sole user, I want yt-dlp to be easily updatable (e.g., `pip install --upgrade yt-dlp`), since YouTube regularly breaks older versions and this will be the most common real-world failure mode.
16. As the sole user, I want transcription to run asynchronously so the UI remains responsive while Whisper processes audio, so that I can browse my library or submit another URL while waiting.
17. As the sole user, I want the web UI to be accessible from any device on my Tailscale network without any additional authentication, since Tailscale provides sufficient network-level security for a single-user tool.
18. As the sole user, I want the system to create and manage new profiles, so that I can extend the profile list beyond the initial set as I encounter new content types.
19. As the sole user, I want the AI provider to be abstracted behind a generic interface, so that switching from Claude API to another provider (OpenAI, Ollama, etc.) is a configuration change, not a code rewrite.
20. As the sole user, I want the data access layer to be cleanly abstracted, so that migrating from SQLite to PostgreSQL in the future is a configuration change, not a rewrite.

## Implementation Decisions

### Framework & Platform

- **FastAPI** for the backend — async-native, which matters for long-running Whisper transcription jobs and concurrent AI API calls.
- **Python 3.11+** as the runtime.
- **Vanilla HTML/CSS/JS** for the V1 frontend — keep it simple, functional, and clean. No frontend framework.
- **Mac Mini (M4, 16GB)** as the host. OpenClaw also runs here but is lightly used; RAM headroom is sufficient for Whisper medium.

### Transcription

- **Whisper medium model** via the `openai-whisper` Python package, running locally on the Mac Mini.
- Audio downloaded by **yt-dlp**, stored temporarily, deleted after transcription.
- Transcript stored as JSON with timestamps in the `transcripts` table.
- Transcription runs asynchronously — the UI should poll or use SSE/WebSocket to update status.

### Database & Data Model

- **SQLite** for V1, with all database access going through a clean abstraction layer (repository pattern or similar) so that the PostgreSQL migration is a swap, not a rewrite.
- **Tables:**
  - `transcripts` — video URL, title, channel, duration, raw transcript (JSON with timestamps), date added, profile_id
  - `profiles` — name, description, structural analysis hints
  - `channel_profiles` — channel name/ID → default profile mapping
  - `baseline_analysis` — transcript_id → structural outline (JSON with section titles + timestamps), overall summary
  - `analysis_results` — transcript_id, analysis_type, result content (JSON), date run
  - `profile_grades` — channel_profile entry, auto-selected profile, user grade (table exists for V1 data capture, but the feedback loop is not wired up)

### AI Integration

- **Claude API** as the default provider for V1 (model: Claude Sonnet for cost efficiency on high-volume analysis).
- All AI calls go through a **provider-agnostic wrapper**: `analyze(prompt, text, model_config)` — the wrapper handles API auth, request formatting, and response parsing. Swapping providers means implementing a new adapter, not changing calling code.
- **Profile context injection**: the profile's hints/expectations are injected into analysis prompts so the AI interprets content structure appropriately for the content type.
- **Chunking strategy**: for transcripts over ~30 minutes, chunk at section boundaries from the baseline analysis rather than arbitrary character/token limits.

### V1 On-Demand Analysis Types

1. **Per-section summarization** — generates a concise summary for each section identified in the baseline structural outline.
2. **Content vs. fluff mapping** — identifies where substantive content starts and ends, highlights filler/intro/outro segments, and suggests optimal start/stop timestamps for watching.
3. **Quote/claim extraction** — pulls out notable quotes, specific claims, statistics, and attributable statements with timestamps.

### Error Handling

- **yt-dlp failures** are logged with the failure reason and displayed as a clear message in the UI. No automatic retry — the user decides whether to try again.
- The PRD recommends keeping yt-dlp easily updatable since YouTube regularly breaks older versions (this is the most common real-world failure).
- **Whisper failures** (corrupt audio, unsupported format) are logged and surfaced in the UI.
- **AI API failures** (rate limits, timeouts, auth errors) are logged and the user is shown a retry option on the analysis button.

### Security

- **Tailscale-only access** — no app-level authentication. The app binds to a local port accessible over the Tailscale network.

### UI Structure

- **Library View** (main screen): transcript list with metadata and analysis indicators, URL input with profile selector.
- **Transcript Detail View**: baseline summary, structural outline with timestamps, on-demand analysis buttons with completion indicators.
- **Analysis View**: opens separately (new tab/panel) to keep the detail view clean. Displays results for a specific analysis type on a specific transcript.

## Testing Decisions

- **Tests are skipped for V1.** This is a single-user tool being built for personal use and learning. The primary risk of skipping tests is that the future PostgreSQL migration will be harder to validate without data layer tests — this is accepted as a V2 concern.
- When tests are added later, priority should be: data access layer (to validate the migration abstraction), then AI provider abstraction (to validate provider swaps), then the download/transcription pipeline.

## Out of Scope

- PostgreSQL migration (schema is designed for it, but SQLite is the V1 database)
- Auto-detection/suggestion of profiles for known channels (channel associations are stored but auto-suggest logic is deferred)
- Profile grading feedback loop (the `profile_grades` table exists for data capture, but the learning loop is not wired up)
- Polished/aesthetically refined UI (V1 is functional and clean, not fancy)
- Multi-user support or authentication
- Automated tests
- Mobile-optimized UI (should work on mobile via responsive design, but not a design priority)
- Batch URL submission (one URL at a time for V1)

## Further Notes

### Deployment Notes

- The app runs alongside OpenClaw on the Mac Mini. Both are lightly used; RAM should be sufficient, but monitor memory during Whisper transcription of long videos (60+ min).
- yt-dlp should be installed in a way that makes `pip install --upgrade yt-dlp` trivial, since YouTube breakage is the most frequent maintenance task.

### Future Considerations

- The profile system and channel association data being captured in V1 sets up a natural V2 feature: auto-suggesting profiles for returning channels and using the grading feedback loop to improve suggestions over time.
- The provider-agnostic AI wrapper means the cost/quality tradeoff can be revisited at any time — swap to a cheaper model for bulk analysis, or to a local model via Ollama for zero-cost experimentation.
- The analysis type list is designed to be extensible. Adding a new analysis type should be: define the prompt template, register it in the system, and it appears as a button in the UI.
- The "Fun UI Ideas" parking lot from the action plan is preserved for later — V1 ships functional, V2 gets personality.

### Risks

- **Whisper medium model performance**: On M4 with 16GB RAM, medium should run well, but very long videos (2+ hours) may take significant wall-clock time. Monitor and consider offering a "fast" mode with the small model if this becomes painful.
- **yt-dlp breakage**: YouTube regularly changes its internals. Budget for periodic yt-dlp updates as routine maintenance.
- **Claude API costs**: On-demand analysis is designed to minimize costs (only run what you need), but high-volume use could add up. The provider abstraction allows switching to cheaper alternatives if needed.
