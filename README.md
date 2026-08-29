# video_moving — YouTube → Bilibili Auto-Repost

[**中文**](README.zh-CN.md) | **English**

> **Research project** — this is an academic/research project for **agent web-adaptation** (LLM agents operating web UIs). It is **not** intended for commercial redistribution of copyrighted content.

Fully-automatic pipeline to repost YouTube videos/playlists to Bilibili: **download → transcode → localize metadata → upload (private)**. Supports scheduled monitoring and dedup by YouTube URL.

> Uploads default to **private (仅自己可见)** — verify on your phone/web before making public, to avoid publishing broken content.

## ⚠️ Disclaimer

- This is a **research/educational project** for **agent web-adaptation** (how LLM agents interact with web UIs).
- All downloaded content (audio/video/cover) **belongs to the original creators**. This tool only automates the repost workflow.
- **侵删 (remove on request)**: if any content infringes your copyright, contact us and it will be removed immediately.
- **Do not** use this to commercially redistribute copyrighted content. Use only for your own study/research or content you have rights to.
- You are responsible for complying with YouTube/Bilibili terms of service and applicable copyright law.

## 📰 Updates

- **2026-08-29**: pipeline established — download → transcode → localize → biliup upload (private + repost), dedup by YouTube URL, quality-first, scheduled monitoring
- **2026-08-29**: refactor — generated data into `data/`, cookies into `config/`, debug artifacts into `test/`, unused code into `legacy/`; project self-bootstraps
- **2026-08-29**: test suite added (pytest, 59 cases)

## ✨ Features

- ✅ **Fully-automatic pipeline**: download → transcode → localize → upload, one command
- ✅ **Dedup by YouTube URL**: keyed on `video_id` (stable URL part), title changes don't matter
- ✅ **Quality-first**: yt-dlp smart format strings, grab best quality+audio, then transcode to Bilibili-compatible H.264+AAC
- ✅ **Private upload**: biliup uploads as private, verify then publish
- ✅ **Repost-compliant**: auto `--copyright 2` + source (original YouTube link)
- ✅ **Scheduled monitoring**: auto-discover and repost new videos (cron, unattended)
- ✅ **Extensible**: modular design, add visualizer / multi-platform etc.

## 🚀 Quick Start

### 1. Environment

```bash
# Python deps
pip install -r requirements.txt

# System deps
pip install yt-dlp biliup        # download + upload
brew install ffmpeg              # transcode (macOS)
```

### 2. Bilibili login (first time only)

Put Bilibili cookies at `config/cookies.json` (biliup format, sensitive, gitignored), or run:

```bash
./run.sh --login
```

### 3. Configure monitor targets

Edit `config/monitors.yaml`:

```yaml
monitors:
  - name: "Naruto Music Playlist"
    url: "https://music.youtube.com/playlist?list=PLdJQK0KLodKg"
    limit: 10
    exclude: ["#short", " Shorts"]
```

### 4. Dry-run (see new videos only)

```bash
./run.sh --dry-run
```

### 5. Run fully automatic

```bash
# Monitor + auto-upload (private)
./run.sh --upload --auto
```

## 📖 Command Reference

| Purpose | Command |
|---------|---------|
| Bilibili login (first) | `./run.sh --login` |
| Dry-run (see new videos) | `./run.sh --dry-run` |
| Monitor + confirm upload | `./run.sh --upload` |
| Monitor + auto-upload | `./run.sh --upload --auto` |
| Process only, no upload | `./run.sh` |
| Single video | `./run.sh --once <URL>` |
| Single video + upload | `./run.sh --once <URL> --upload --auto` |

## 🔄 Workflow

```
Monitor target (config/monitors.yaml)
        │
        ▼
   yt-dlp fetch video list
        │
        ▼
  compare config/processed.json ── processed → skip
        │ new video
        ▼
  download → transcode(H.264+AAC) → localize metadata
        │
        ▼
  [confirm / --auto] → biliup upload (private + repost)
        │
        ▼
  record to processed.json (BV + source_url)
```

## 📁 Directory Structure

```
video_moving/
├── run.sh                       # one-click script
├── pyproject.toml               # package + deps
├── requirements.txt             # Python deps
├── config/
│   ├── monitors.yaml            # monitor targets ← edit this
│   ├── monitors.yaml.example    # config template
│   ├── cookies.json             # Bilibili login (sensitive, gitignored)
│   └── processed.json           # processed records (auto, gitignored)
├── src/
│   ├── config.py                # global config
│   ├── models.py                # shared data models (UploadTask/Result)
│   ├── downloader.py            # yt-dlp download
│   ├── transcoder.py            # ffmpeg transcode
│   ├── metadata_localizer.py    # metadata localization
│   ├── biliup_uploader.py       # Bilibili upload (biliup CLI)
│   ├── pipeline.py              # main orchestrator (single video)
│   ├── monitor.py               # channel monitor
│   └── cookie_extractor.py      # YouTube cookies extraction
├── data/                        # generated data (gitignored, auto-created)
│   ├── downloads/               # raw downloads (one folder per video)
│   ├── output/                  # processed output
│   └── logs/                    # logs
├── test/                        # test/debug artifacts (gitignored)
└── legacy/                      # unused code (local only, gitignored)
```

> **Convention**: `data/`, `test/`, `legacy/` are all gitignored. The project is **self-bootstrapping**: first run auto-creates `data/` (downloads/output/logs/archive/failed). Move unused code to `legacy/`, debug/test artifacts to `test/` — never delete.

## 🧪 Testing

```bash
pip install pytest
pytest
```

Covers: data models, config, downloader (ID extraction / filename sanitize / quality presets), transcoder (compatibility / command build), metadata localization, biliup upload (BV parse / command build / task load), monitor dedup logic.

## 🧩 Extension: Visualizer (cover + spectrum)

Optional, use `muvid` to render "audio + cover" into a dynamic spectrum video, avoiding duplication with the original:

```bash
pip install -e ".[visualizer]"
```

```python
from muvid.visualize import render_audio_video
render_audio_video("song.wav", image="cover.png", visual="spectrum")
```

## ⚙️ Config Override

Optionally create `config/settings.json` to override defaults:

```json
{
  "download": { "max_retries": 5, "rate_limit": "10M" },
  "transcode": { "video_crf": 20, "audio_bitrate": "256k" }
}
```

## 🛠 Troubleshooting

- **Not logged in**: `./run.sh --login`
- **Download fails**: YouTube sometimes rate-limits, retry; ensure Chrome is running (cookies extraction)
- **Upload fails**: check `config/cookies.json` is valid; check title/desc for special chars
- **Monitor finds no new videos**: check `monitors.yaml` URL; `processed.json` records processed videos, delete an entry to reprocess

## 📄 License

[MIT](LICENSE)
