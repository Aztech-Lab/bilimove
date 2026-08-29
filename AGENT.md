# AGENT.md — Agent 手册

> 给 LLM Agent 看的项目手册。**Agent 请先读本文件**，再读 `README.md` 或源码。
> 本文件假设读者是能执行命令、读写文件的 agent，不是人类。

## 1. 这是什么

`bilimove` 是一个**全自动**把 YouTube 视频/播放列表搬运到 B 站的流水线：

```
下载(yt-dlp) → 转码(ffmpeg H.264+AAC) → 元数据汉化 → 上传(biliup, 仅自己可见+转载)
```

- 按 YouTube `video_id` 去重（URL 稳定部分，标题变化不影响）
- 上传默认**仅自己可见**，用户手机核实后再公开
- 支持定时监控（cron）和单视频处理

## 2. 环境

- Python venv：`.venv/`（含 yt-dlp、biliup、PyYAML、pytest）
- 系统依赖：`ffmpeg`（转码必需）
- 关键二进制：`.venv/bin/yt-dlp`、`.venv/bin/biliup`

**重要**：必须用 `.venv/bin/yt-dlp`（2026.08.19），不要用 PATH 里的旧版（2025.12.08 有 player-client bug，会导致 403/格式不可用）。

## 3. 快速上手（首次）

```bash
cd <项目目录>
source .venv/bin/activate

# 1) B 站登录（扫码，一次性）——工具自动抓 cookies，无需手动提供
./run.sh --login

# 2) 配置监控频道：编辑根目录 channels.txt，每行一个 URL
#    若为空，首次运行会交互提示输入
```

## 4. 核心命令

| 任务 | 命令 |
|------|------|
| B 站登录 | `./run.sh --login` |
| 监控一轮（只处理不上传） | `./run.sh` |
| 监控 + 上传（逐个确认） | `./run.sh --upload` |
| 监控 + 自动上传 | `./run.sh --upload --auto` |
| 只看新视频 | `./run.sh --dry-run` |
| **心跳模式**（每分钟同步，有新视频自动下载+上传） | `./run.sh --heartbeat --upload --auto` |
| 单个视频 | `./run.sh --once <URL>` |
| 单个 + 上传 | `./run.sh --once <URL> --upload --auto` |
| 批量（文件里每行一个 URL） | `python -m src.pipeline --batch <file>` |

等价底层命令：
- 监控：`python -m src.monitor [--upload] [--auto] [--dry-run] [--config <yaml>]`
- 心跳：`python -m src.monitor --heartbeat [--interval <秒>] [--upload] [--auto]`
- 单视频：`python -m src.pipeline <URL> [--upload] [--auto]`

## 5. 关键文件路径

| 路径 | 作用 |
|------|------|
| `channels_local.txt` | **本地隐私频道**（优先加载，gitignore，绝不进 git） |
| `channels.txt` | 普通频道列表（fallback，gitignore） |
| `channels.example.txt` | 频道模板（提交） |
| `config/cookies.json` | B 站登录 cookies（敏感，gitignore，自动生成） |
| `config/processed.json` | 已处理记录 `{video_id: {status,title,bvid,source_url,...}}`（去重依据） |
| `config/monitors.yaml` | 高级监控配置（可选，`--config` 指定） |
| `data/downloads/{video_id}/` | 原始下载（每视频一个子目录） |
| `data/output/` | 转码后输出 |
| `data/logs/` | 日志 |
| `data/failed/` | 失败记录 |
| `src/` | 源码（模块化） |

## 6. 关键规则（务必遵守）

1. **转载必须带来源**：上传用 `--copyright 2`（转载）+ `--source <原YouTube链接>`。缺 source 会报 `code 21021`。
2. **简介保留换行**：`--desc` 必须原样传，不要压成一行（用户明确要求）。
3. **封面格式**：biliup 不接受 `.webp`，上传前转成 `.png`（uploader 已自动处理）。
4. **去重**：`should_process()` 检查 `video_id in processed.json`。要重处理某视频，删掉对应条目。
5. **画质优先**：下载用 `bestvideo+bestaudio/best` 回退链，先拿最高画质再转码。
6. **上传默认仅自己可见**：`--is-only-self 1`。用户手机核实后再公开。
7. **不要删文件**：没用的代码移到 `legacy/`，调试产物放 `test/`，生成数据放 `data/`。这三个目录 gitignore。

## 7. 常见任务

### 7.1 处理单个视频并上传
```bash
./run.sh --once "https://www.youtube.com/watch?v=XXXXX" --upload --auto
```

### 7.2 添加监控频道
编辑 `channels_local.txt`（本地隐私，不进 git）或 `channels.txt`，每行加一个 URL：
```
https://www.youtube.com/@ChannelName/videos
https://music.youtube.com/playlist?list=PLxxxx
```
然后 `./run.sh --dry-run` 验证能发现新视频。

### 7.3 重处理一个视频
```bash
# 从 processed.json 删掉该 video_id 条目，再跑
python -c "import json;d=json.load(open('config/processed.json'));d.pop('XXXXX',None);json.dump(d,open('config/processed.json','w'),ensure_ascii=False,indent=2)"
./run.sh --once "https://www.youtube.com/watch?v=XXXXX"
```

### 7.4 检查登录是否有效
```bash
.venv/bin/python -m biliup -u config/cookies.json list
# 输出含 "user:" 或 BV 号即有效
```

### 7.5 跑测试
```bash
pytest
```

## 8. 故障排查

| 症状 | 原因 | 处理 |
|------|------|------|
| 下载 403 / "Requested format is not available" | 用了旧 yt-dlp | 用 `.venv/bin/yt-dlp` |
| 上传 `code 21021` | 转载缺 source | 确保 `--source` 非空 |
| 上传 `RuntimeError: Unknown Error` | 封面是 webp | 转 png（uploader 已处理） |
| 草稿箱空 | 浏览器自动化不可靠 | 用 biliup（本项目已切换） |
| 监控无新视频 | channels.txt 空或 URL 错 | 检查 channels.txt；processed.json 记录已处理 |

## 9. 扩展

模块化设计，每阶段独立：
- `src/downloader.py` — 下载（yt-dlp）
- `src/transcoder.py` — 转码（ffmpeg）
- `src/metadata_localizer.py` — 元数据汉化
- `src/biliup_uploader.py` — B 站上传
- `src/pipeline.py` — 单视频编排
- `src/monitor.py` — 频道监控

加新功能（如可视化）时，新增模块并接入 `pipeline.py` 即可。可选可视化：`pip install -e ".[visualizer]"`（muvid，封面+动态频谱）。
