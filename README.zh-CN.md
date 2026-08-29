# YouTube → B 站 全自动搬运

**中文** | [**English**](README.md)

> **科研项目** — 本项目是**学术/科研用途**，用于 **agent 网页端适配**（LLM 智能体操作网页 UI）研究。**不用于**受版权保护内容的商业再分发。

全自动把 YouTube 视频/播放列表搬运到 B 站：**下载 → 转码 → 元数据汉化 → 上传（仅自己可见）**，支持定时监控、按 YouTube 地址去重。

它**绕过 YouTube 反爬**（player-client 回退链、Chrome cookies、JS 挑战求解器），并**通过 B 站官方 API 上传**（biliup），配合**仅自己可见 + 手机核实**安全发布。技术细节见 [原理解析](#-原理解析)。

> 🤖 **给 AI Agent**：读 [`AGENT.md`](AGENT.md)（agent 手册）或加载 [`skill/bilimove`](skill/bilimove/SKILL.md) skill，无需读代码/文档。

## 📰 更新动态

- **2026-08-29**：心跳模式（每分钟同步，自动下载+上传）+ 本地隐私频道（`channels_local.txt`，gitignore）
- **2026-08-29**：AGENT.md + skill — agent 手册和可加载 skill，AI Agent 无需读代码/文档即可使用
- **2026-08-29**：channels.txt — 根目录配置监控频道（每行一个 URL），首次运行交互提示
- **2026-08-29**：流水线建立 — 下载 → 转码 → 汉化 → biliup 上传（仅自己可见 + 转载），按 YouTube 地址去重，画质优先，定时监控

### 💓 心跳模式

常驻循环，**每分钟同步你的频道/播放列表**，发现新视频就自动跑完整流水线：**下载 → 转码 → 汉化 → 上传（仅自己可见）**。

```bash
./run.sh --heartbeat --upload --auto
```

- **间隔**：默认 60 秒，用 `--interval <秒>` 调整。
- **停止**：`Ctrl-C`。
- **隐私**：频道优先从 `channels_local.txt`（gitignore）读取，fallback 到 `channels.txt`。
- **去重**：已处理视频通过 `config/processed.json` 跳过（以 YouTube `video_id` 为 key）。

等价命令：`python -m src.monitor --heartbeat [--interval <秒>] [--upload] [--auto] [--dry-run]`

## ✨ 核心功能

- ✅ **全自动流水线**：下载 → 转码 → 汉化 → 上传，一条命令跑完
- ✅ **按 YouTube 地址去重**：`video_id`（URL 稳定部分）为 key，标题怎么变都不影响
- ✅ **画质优先**：yt-dlp 智能格式串，优先拿最高画质+音质，再转成 B 站兼容的 H.264+AAC
- ✅ **仅自己可见上传**：biliup 上传为私有，核实后再公开
- ✅ **转载合规**：自动带 `--copyright 2` + 转载来源（原 YouTube 链接）
- ✅ **定时监控**：自动发现新视频并搬运（cron 无人值守）
- ✅ **可扩展**：模块化设计，可加可视化、多平台等

## 🔬 原理解析

### 绕过 YouTube 反爬

YouTube 通过三种机制阻止自动化下载：

1. **player-client 限制** — 不同客户端（web、android、ios、tv）返回不同的播放器响应，有些被限制或画质更低。
2. **JS 挑战（n-sig / PO token）** — YouTube 要求解一个 JavaScript 挑战才能拿到有效的流地址。
3. **登录要求** — 部分内容需要登录会话。

我们的做法：

- **player-client 回退链** — 依次尝试 `web_embedded → android_vr → android → web_safari → web_creator`。每个客户端限制不同，取第一个成功的；有些客户端（如 `android_vr`）完全不需要 cookies。
- **Chrome cookies 提取** — 从你的 Chrome 浏览器拉取登录 cookies（`--cookies-from-browser chrome`），用于需要登录的内容。
- **JS 挑战求解器** — yt-dlp 用外部 JS 运行时（**Deno**）解 n-sig / PO-token 挑战。我们保持 yt-dlp 更新到最新版，新版自带这些挑战的修复。
- **智能格式串** — `bestvideo+bestaudio/best` 带 `/` 回退链，一条命令拿最高画质，避免在固定 format_id 上空转。

### 上传到 B 站（API 限制）

- **biliup CLI** — 直接走 B 站**官方上传 API**（分片上传、重试），替代脆弱的浏览器自动化（之前会产出残缺草稿）。
- **cookies 认证** — 通过 `config/cookies.json` 认证。
- **仅自己可见上传** — 上传为私有，你在手机核实后再公开。
- **转载合规** — `--copyright 2`（转载）+ `--source`（原 YouTube 链接），B 站转载必需。

### 和其他项目有什么不一样

- **全自动** — 一条命令：下载 → 转码 → 汉化 → 上传。
- **画质优先** — 先拿最高画质，再转成 B 站兼容的 H.264+AAC。
- **去重稳健** — 以 YouTube `video_id`（URL 稳定部分）为 key，标题变化不会导致重复。
- **安全发布** — 仅自己可见 + 手机核实，避免误发残破内容。
- **元数据汉化** — 自动生成中文标题/简介/标签。
- **无人值守监控** — cron 定时自动搬运。
- **模块化可扩展** — 模块清晰分离，易加功能。

## 🚀 快速开始

### 1. 环境准备

```bash
# Python 依赖
pip install -r requirements.txt

# 系统依赖
pip install yt-dlp biliup        # 下载 + 上传
brew install ffmpeg              # 转码（macOS）
```

### 2. 登录（首次，只需一次）

工具**自动抓取 cookies**，无需手动提取：

- **B 站**：跑一次 `./run.sh --login`，手机扫码即可。cookies 自动保存到 `config/cookies.json`。
- **YouTube**：只需 Chrome 里登录过 YouTube，工具自动从 Chrome 提取 cookies。

```bash
./run.sh --login
```

### 3. 配置监控频道

编辑项目根目录的 **`channels_local.txt`**（本地隐私，gitignore）—— **每行一个频道/播放列表 URL**，傻瓜式复制粘贴：

```
# 每行一个 YouTube 频道/播放列表 URL
https://www.youtube.com/@频道名/videos
https://music.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx
```

- **隐私**：`channels_local.txt` 优先加载且 **gitignore**，绝不同步到 git。没有则 fallback 到 `channels.txt`。
- **首次运行**：若两者都为空，工具会交互式提示你输入频道。
- **多个频道**：直接加行即可。
- 模板：`channels.example.txt`。

### 4. 试跑（只看新视频）

```bash
./run.sh --dry-run
```

### 5. 正式全自动跑

> **运行前**：确认 `channels_local.txt` 已填好频道（见第 3 步）。若为空，首次运行会提示你输入。

```bash
# 监控 + 自动上传（仅自己可见）
./run.sh --upload --auto

# 心跳模式：每分钟同步列表，有新视频自动下载+上传
./run.sh --heartbeat --upload --auto
```

## 📖 命令速查

| 目的 | 命令 |
|------|------|
| B 站登录（首次） | `./run.sh --login` |
| 试跑（看新视频） | `./run.sh --dry-run` |
| 监控 + 确认上传 | `./run.sh --upload` |
| 监控 + 自动上传 | `./run.sh --upload --auto` |
| **心跳模式**（每分钟同步，自动下载+上传） | `./run.sh --heartbeat --upload --auto` |
| 只处理不上传 | `./run.sh` |
| 单个视频 | `./run.sh --once <URL>` |
| 单个视频 + 上传 | `./run.sh --once <URL> --upload --auto` |

## 🔄 工作流程

```
监控目标 (config/monitors.yaml)
        │
        ▼
   yt-dlp 拉取视频列表
        │
        ▼
  对比 config/processed.json ── 已处理 → 跳过
        │ 新视频
        ▼
  ┌─ 下载 ────────────────────────────────────────────────┐
  │  player-client 回退链 (web_embedded → android…)        │
  │  + Chrome cookies + JS 挑战求解器 (Deno)               │
  │  + 智能格式串 (bestvideo+bestaudio/best)               │
  └────────────────────────────────────────────────────────┘
        │
        ▼
  转码 → H.264 + AAC（B 站兼容）
        │
        ▼
  元数据汉化 → 中文标题 / 简介 / 标签
        │
        ▼
  [确认 / --auto] → biliup 上传（官方 API）
        │                仅自己可见 + 转载 (--copyright 2 --source)
        ▼
  记录到 processed.json（BV 号 + source_url）
```

每个阶段都是独立模块（`downloader.py`、`transcoder.py`、`metadata_localizer.py`、`biliup_uploader.py`），可单独替换或扩展。

## 📁 目录结构

```
video_moving/
├── run.sh                       # 一键脚本
├── AGENT.md                     # agent 手册（先读这个）
├── channels_local.txt           # 本地隐私频道（gitignore）← 编辑这个
├── channels.txt                 # fallback 频道（gitignore）
├── channels.example.txt         # 频道模板
├── skill/
│   ├── README.md                # skill 使用说明
│   └── bilimove/SKILL.md        # 可加载的 agent skill
├── pyproject.toml               # 包定义 + 依赖
├── requirements.txt             # Python 依赖
├── config/
│   ├── monitors.yaml            # 高级监控配置（可选）
│   ├── monitors.yaml.example    # 配置模板
│   ├── cookies.json             # B 站登录（敏感，gitignore）
│   └── processed.json           # 已处理记录（自动生成，gitignore）
├── src/
│   ├── config.py                # 全局配置
│   ├── models.py                # 共享数据模型（UploadTask/Result）
│   ├── downloader.py            # yt-dlp 下载
│   ├── transcoder.py            # ffmpeg 转码
│   ├── metadata_localizer.py    # 元数据汉化
│   ├── biliup_uploader.py       # B 站上传（biliup CLI）
│   ├── pipeline.py              # 主调度器（单视频全流程）
│   ├── monitor.py               # 频道监控器
│   └── cookie_extractor.py      # YouTube cookies 提取
├── data/                        # 生成数据（gitignore，自动创建）
│   ├── downloads/               # 原始下载（每个视频一个子文件夹）
│   ├── output/                  # 处理产出
│   └── logs/                    # 日志
├── test/                        # 调试/测试产物（gitignore）
└── legacy/                      # 遗留/不再使用的代码（本地保留，gitignore）
```

> **约定**：`data/`、`test/`、`legacy/` 均 gitignore，不进开源仓库。项目**自举**：克隆后首次运行会自动创建 `data/`（downloads/output/logs/archive/failed）。不再使用的代码移入 `legacy/`，调试/测试产物移入 `test/`，**都不删除**。

## 🧪 测试

```bash
pip install pytest
pytest
```

覆盖：数据模型、配置、下载器（ID 提取/文件名清理/质量预设）、转码器（兼容性判断/命令构造）、元数据汉化、biliup 上传（BV 解析/命令构造/任务加载）、监控去重逻辑。

## 🧩 扩展：可视化（封面 + 动态频谱）

可选扩展，用 `muvid` 把「音频 + 封面」渲染成动态频谱视频，避免和原作重复：

```bash
pip install -e ".[visualizer]"
```

```python
from muvid.visualize import render_audio_video
render_audio_video("song.wav", image="cover.png", visual="spectrum")
```

## ⚙️ 配置覆盖

可选创建 `config/settings.json` 覆盖默认参数：

```json
{
  "download": { "max_retries": 5, "rate_limit": "10M" },
  "transcode": { "video_crf": 20, "audio_bitrate": "256k" }
}
```

## 🛠 故障排查

- **未登录 B 站**：`./run.sh --login`
- **下载失败**：YouTube 有时限流，多试几次；确认 Chrome 在运行（cookies 提取需要）
- **上传失败**：确认 `config/cookies.json` 有效；检查标题/简介是否含特殊字符
- **监控没发现新视频**：确认 `monitors.yaml` URL 正确；`processed.json` 记录了已处理视频，想重处理就删对应条目

## ⚠️ 免责声明

- 本项目是**科研/教育用途**，用于 **agent 网页端适配**（LLM 智能体如何操作网页 UI）研究。
- 所有下载内容（音频/视频/封面）**版权归原作者所有**。本工具仅自动化搬运流程。
- **侵删**：如任何内容侵犯您的版权，请联系我们，将立即删除。
- **请勿**用本工具商业再分发受版权保护的内容。仅用于个人学习/研究，或您拥有权利的内容。
- 您需自行遵守 YouTube/B 站服务条款及适用的版权法律。

## 🙏 鸣谢

感谢让本项目成为可能的开源工具与平台：

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — YouTube 下载引擎（player-client 回退、JS 挑战求解）
- **[biliup](https://github.com/biliup/biliup)** — B 站上传 API 客户端
- **[ffmpeg](https://ffmpeg.org/)** — 转码为 B 站兼容的 H.264+AAC
- **YouTube / B 站** — 本项目桥接的两个平台

---

本项目由 **[Aztech Labs](https://github.com/Aztech-Lab) 特别企划**，由 **DeepSeek V4 Flash** 执行与编译，由 **DeepSeek Harness** 工程化落地。


## 📄 License

[MIT](LICENSE)