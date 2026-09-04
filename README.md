# YouTube → Bilibili Auto-Repost

[**中文**](README.zh-CN.md) | **English**

> **Research project** — this is an academic/research project for **agent web-adaptation** (LLM agents operating web UIs). It is **not** intended for commercial redistribution of copyrighted content.

Fully-automatic pipeline to repost YouTube videos/playlists to Bilibili: **download → transcode → localize metadata → upload (private)**. Supports scheduled monitoring and dedup by YouTube URL.

It **bypasses YouTube's anti-scraping** (player-client fallback, Chrome cookies, JS-challenge solver) and **uploads via Bilibili's official API** (biliup), with **private upload + phone verification** for safe publishing. See [How It Works](#-how-it-works) for the technical details.

> 🤖 **For AI agents**: read [`AGENT.md`](AGENT.md) (agent manual) or load the [`skill/bilimove`](skill/bilimove/SKILL.md) skill — no need to read code/docs.

## 📰 Updates

- **2026-09-03**: single `config.yaml` at root — title/description/credit templates + numbers/tags/download/transcode, foolproof customization via placeholders
- **2026-09-03**: manual video add — `./run.sh --add` interactive URL input (bypasses dedup, user-specified video is always re-uploaded)
- **2026-09-03**: failed-video auto-retry — videos that failed (download/upload) are automatically retried on restart/next round
- **2026-08-29**: heartbeat mode (sync every minute, auto download+upload) + local privacy channels (`channels_local.txt`, gitignored)
- **2026-08-29**: AGENT.md + skill — agent manual and loadable skill so AI agents can use the project without reading code/docs
- **2026-08-29**: channels.txt — configure monitor channels at project root (one URL per line), interactive prompt on first run
- **2026-08-29**: pipeline established — download → transcode → localize → biliup upload (private + repost), dedup by YouTube URL, quality-first, scheduled monitoring

### 💓 Heartbeat mode

A resident loop that **syncs your channel/playlist every minute** and, when a new video appears, automatically runs the full pipeline: **download → transcode → localize → upload (private)**.

```bash
./run.sh --heartbeat --upload --auto
```

- **Interval**: default 60s, adjust with `--interval <seconds>`.
- **Stop**: `Ctrl-C`.
- **Privacy**: channels are read from `channels_local.txt` (gitignored) first, falling back to `channels.txt`.
- **Dedup**: already-processed videos are skipped via `config/processed.json` (keyed on YouTube `video_id`).

Equivalent: `python -m src.monitor --heartbeat [--interval <s>] [--upload] [--auto] [--dry-run]`

## ✨ Features

- ✅ **Fully-automatic pipeline**: download → transcode → localize → upload, one command
- ✅ **Dedup by YouTube URL**: keyed on `video_id` (stable URL part), title changes don't matter
- ✅ **Quality-first**: yt-dlp smart format strings, grab best quality+audio, then transcode to Bilibili-compatible H.264+AAC
- ✅ **Private upload**: biliup uploads as private, verify then publish
- ✅ **Repost-compliant**: auto `--copyright 2` + source (original YouTube link)
- ✅ **Scheduled monitoring**: auto-discover and repost new videos (cron, unattended)
- ✅ **Extensible**: modular design, add visualizer / multi-platform etc.

## 🔬 How It Works

### Bypassing YouTube anti-scraping

YouTube actively blocks automated downloads via three mechanisms:

1. **Player-client restrictions** — different clients (web, android, ios, tv) receive different player responses; some are restricted or return lower quality.
2. **JS challenges (n-sig / PO token)** — YouTube requires solving a JavaScript challenge to obtain valid stream URLs.
3. **Signed-in requirements** — some content needs a logged-in session.

Our approach:

- **Player-client fallback chain** — try `web_embedded → android_vr → android → web_safari → web_creator` in order. Each client has different restrictions; we pick the first that works. Some clients (e.g. `android_vr`) don't need cookies at all.
- **Chrome cookies extraction** — pull signed-in cookies from your Chrome browser (`--cookies-from-browser chrome`) for content that needs auth.
- **JS-challenge solver** — yt-dlp uses an external JS runtime (**Deno**) to solve the n-sig / PO-token challenge. We keep yt-dlp updated to the latest version, which ships the fixes for these challenges.
- **Smart format strings** — `bestvideo+bestaudio/best` with `/` fallback chains grab the best quality in a single command, avoiding wasted attempts on fixed format IDs.

### Uploading to Bilibili (API limits)

- **biliup CLI** — uses Bilibili's **official upload API** directly (chunked upload, retries), instead of fragile browser automation that produced broken drafts.
- **Cookies auth** — authenticates via `config/cookies.json`.
- **Private upload** — uploads as **仅自己可见 (private)**, so you verify on your phone before publishing.
- **Repost compliance** — `--copyright 2` (repost) + `--source` (original YouTube URL), required by Bilibili for reposted content.

### What makes this different

- **Fully automatic** — one command: download → transcode → localize → upload.
- **Quality-first** — grabs the best quality, then transcodes to Bilibili-compatible H.264+AAC.
- **Robust dedup** — keyed on YouTube `video_id` (stable URL part), so title changes don't cause duplicates.
- **Safe publishing** — private upload + phone verification, avoids publishing broken content.
- **Metadata localization** — auto-Chinese title/desc/tags.
- **Unattended monitoring** — cron-based scheduled reposting.
- **Modular & extensible** — clean module separation, easy to add features.

## 🚀 Quick Start

### 1. Environment

```bash
# Python deps
pip install -r requirements.txt

# System deps
pip install yt-dlp biliup        # download + upload
brew install ffmpeg              # transcode (macOS)
```

### 2. Login (first time only)

The tool **grabs cookies automatically** — no manual extraction needed:

- **Bilibili**: run `./run.sh --login`, scan the QR code with your phone once. Cookies are auto-saved to `config/cookies.json`.
- **YouTube**: just be logged into YouTube in your Chrome browser — the tool auto-extracts cookies from Chrome.

```bash
./run.sh --login
```

### 3. Configure monitor channels

Edit **`channels_local.txt`** at the project root (local privacy, gitignored) — **one channel/playlist URL per line**, foolproof copy-paste:

```
# 每行一个 YouTube 频道/播放列表 URL
https://www.youtube.com/@ChannelName/videos
https://music.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx
```

- **Privacy**: `channels_local.txt` is loaded first and is **gitignored** — never synced to git. Fallback to `channels.txt` if absent.
- **First run**: if both are empty, the tool prompts you to enter channels interactively.
- **Multiple channels**: just add more lines.
- Template: `channels.example.txt`.

### 4. Dry-run (see new videos only)

```bash
./run.sh --dry-run
```

### 5. Run fully automatic

> **Before running**: make sure `channels_local.txt` has your channels (see step 3). If it's empty, the tool prompts you on first run.

```bash
# Monitor + auto-upload (private)
./run.sh --upload --auto

# Heartbeat: sync every minute, auto download+upload new videos
./run.sh --heartbeat --upload --auto
```

## 📖 Command Reference

| Purpose | Command |
|---------|---------|
| Bilibili login (first) | `./run.sh --login` |
| Dry-run (see new videos) | `./run.sh --dry-run` |
| Monitor + confirm upload | `./run.sh --upload` |
| Monitor + auto-upload | `./run.sh --upload --auto` |
| **Heartbeat** (sync every minute, auto download+upload) | `./run.sh --heartbeat --upload --auto` |
| Process only, no upload | `./run.sh` |
| Single video | `./run.sh --once <URL>` |
| Single video + upload | `./run.sh --once <URL> --upload --auto` |
| **Manual add** (interactive URL input) | `./run.sh --add --upload --auto` |

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
  ┌─ download ─────────────────────────────────────────────┐
  │  player-client fallback chain (web_embedded → android…) │
  │  + Chrome cookies + JS-challenge solver (Deno)          │
  │  + smart format string (bestvideo+bestaudio/best)       │
  └─────────────────────────────────────────────────────────┘
        │
        ▼
  transcode → H.264 + AAC (Bilibili-compatible)
        │
        ▼
  localize metadata → Chinese title / desc / tags
        │
        ▼
  [confirm / --auto] → biliup upload (official API)
        │                 private (仅自己可见) + repost (--copyright 2 --source)
        ▼
  record to processed.json (BV + source_url)
```

Each stage is a separate module (`downloader.py`, `transcoder.py`, `metadata_localizer.py`, `biliup_uploader.py`), so you can swap or extend any step.

## 📁 Directory Structure

```
video_moving/
├── run.sh                       # one-click script
├── AGENT.md                     # agent manual (read this first)
├── channels_local.txt           # local private channels (gitignored) ← edit this
├── channels.txt                 # fallback channels (gitignored)
├── channels.example.txt         # channels template
├── config.yaml                  # single config (format + runtime) ← edit this
├── skill/
│   ├── README.md                # skill usage
│   └── bilimove/SKILL.md        # loadable agent skill
├── pyproject.toml               # package + deps
├── requirements.txt             # Python deps
├── config/
│   ├── monitors.yaml            # advanced monitor config (optional)
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

Edit **`config.yaml`** at the project root — the single config for title/description format, numbers, tags, and download/transcode. Foolproof, out of the box:

```yaml
# 标题格式（占位符 {title} {uploader} {source_title}）
title_format_music: "【搬运】{title} - {uploader}"   # music videos
title_format: "【搬运】{title}"                      # other videos

# 简介模板（占位符 {title} {music_info} {summary} {uploader} {source_title} {copyright} {credit} {tags}）
description_template: |
  🎵 {title}
  原作者：{uploader}

  {music_info}

  {summary}

  {credit}
  ━━━━━━━━━━━━━━━━━━━━

  {copyright}

  {tags}

# 简介里的 credit 内容（通过 {credit} 占位符引用）
credit: |
  本视频由 bilimove 自动搬运
  开源项目：https://github.com/Aztech-Lab/bilimove

# 数字配置
max_desc_length: 2000
max_title_length: 80
max_tags: 10
default_tid: 3
add_copyright_notice: true
base_tags:
  - 音乐搬运

# 下载/转码（可选覆盖）
download:
  max_retries: 5
transcode:
  video_crf: 20
```

### 📝 Description template placeholders

The description structure lives in `config.yaml` → `description_template`. Placeholders are filled per video:

| Placeholder | Meaning |
|-------------|---------|
| `{title}` | video title |
| `{music_info}` | music info block (artist/album/date/label) |
| `{summary}` | description summary (non-music) |
| `{uploader}` | original uploader |
| `{source_title}` | original video title |
| `{copyright}` | copyright notice |
| `{credit}` | content of `credit.txt` |
| `{tags}` | hashtags |

Default template:
```
🎵 {title}

{music_info}

{summary}

━━━━━━━━━━━━━━━━━━━━

原作者：{uploader}
原视频：{source_title}

{copyright}

{credit}

{tags}
```

Edit **`credit.txt`** for the credit/attribution content (referenced via `{credit}`). Delete or empty a file to disable that part.

## 🛠 Troubleshooting

- **Not logged in**: `./run.sh --login`
- **Download fails**: YouTube sometimes rate-limits, retry; ensure Chrome is running (cookies extraction)
- **Upload fails**: check `config/cookies.json` is valid; check title/desc for special chars
- **Monitor finds no new videos**: check `monitors.yaml` URL; `processed.json` records processed videos, delete an entry to reprocess

## ⚠️ Disclaimer

- This is a **research/educational project** for **agent web-adaptation** (how LLM agents interact with web UIs).
- All downloaded content (audio/video/cover) **belongs to the original creators**. This tool only automates the repost workflow.
- **侵删 (remove on request)**: if any content infringes your copyright, contact us and it will be removed immediately.
- **Do not** use this to commercially redistribute copyrighted content. Use only for your own study/research or content you have rights to.
- You are responsible for complying with YouTube/Bilibili terms of service and applicable copyright law.

## 🙏 Acknowledgments

Thanks to the open-source tools and platforms that make this possible:

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — YouTube download engine (player-client fallback, JS-challenge solver)
- **[biliup](https://github.com/biliup/biliup)** — Bilibili upload API client
- **[ffmpeg](https://ffmpeg.org/)** — transcoding to Bilibili-compatible H.264+AAC
- **YouTube / Bilibili** — the platforms this pipeline bridges

---

This project is **specially planned by [Aztech Labs](https://github.com/Aztech-Lab)**, executed and compiled by **DeepSeek V4 Flash**, and engineered end-to-end by **DeepSeek Harness**.


## 📄 License

[MIT](LICENSE)
