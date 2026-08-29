---
name: bilimove
description: Automate reposting YouTube videos/playlists to Bilibili with bilimove — download (yt-dlp), transcode (ffmpeg H.264+AAC), localize metadata to Chinese, and upload via biliup (private + repost). Use this skill to set up, run, monitor, dedup, or extend the pipeline. Read AGENT.md at the project root for the full manual.
---

# bilimove — YouTube → Bilibili Auto-Repost

Fully-automatic pipeline: **download → transcode → localize → upload (private + repost)**. Dedup by YouTube `video_id`. Uploads default to private (仅自己可见) so the user verifies on their phone before publishing.

## Setup (first time)

```bash
cd <project_root>
source .venv/bin/activate
./run.sh --login        # Bilibili QR login (one-time, auto-saves cookies)
```

- Bilibili cookies auto-saved to `config/cookies.json` (gitignored).
- YouTube cookies auto-extracted from Chrome (`--cookies-from-browser chrome`).
- Configure monitor channels in root `channels.txt` (one URL per line). If empty, first run prompts interactively.

## Core operations

| Task | Command |
|------|---------|
| Monitor (process only) | `./run.sh` |
| Monitor + upload (confirm each) | `./run.sh --upload` |
| Monitor + auto-upload | `./run.sh --upload --auto` |
| Dry-run (list new videos) | `./run.sh --dry-run` |
| Single video | `./run.sh --once <URL>` |
| Single + upload | `./run.sh --once <URL> --upload --auto` |
| Batch (file, one URL per line) | `python -m src.pipeline --batch <file>` |

## Critical rules

1. **Repost requires source**: upload uses `--copyright 2` + `--source <original YouTube URL>`. Missing source → error `code 21021`.
2. **Preserve newlines in description**: pass `--desc` verbatim, never flatten to one line.
3. **Cover must be PNG**: biliup rejects `.webp`; the uploader auto-converts to `.png`.
4. **Dedup**: `should_process()` checks `video_id in config/processed.json`. To reprocess, delete that entry.
5. **Quality-first**: download with `bestvideo+bestaudio/best` fallback chain, then transcode to Bilibili-compatible H.264+AAC.
6. **Private upload**: `--is-only-self 1`. User verifies on phone before making public.
7. **Never delete files**: move unused code to `legacy/`, debug artifacts to `test/`, generated data to `data/` (all gitignored).

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Download 403 / "Requested format is not available" | old yt-dlp | use `.venv/bin/yt-dlp` (2026.08.19) |
| Upload `code 21021` | repost missing source | ensure `--source` non-empty |
| Upload `RuntimeError: Unknown Error` | webp cover | convert to png (uploader handles) |
| Empty draft box | browser automation unreliable | use biliup (this project switched) |
| Monitor finds nothing | empty channels.txt / bad URL | check channels.txt; processed.json records done |

## Extension

Modular: `src/downloader.py`, `src/transcoder.py`, `src/metadata_localizer.py`, `src/biliup_uploader.py`, `src/pipeline.py`, `src/monitor.py`. Add a module and wire it into `pipeline.py`. Optional visualizer: `pip install -e ".[visualizer]"` (muvid, cover + dynamic spectrum).
