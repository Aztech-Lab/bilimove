# video_moving — YouTube → B 站 全自动搬运

全自动把 YouTube 视频/播放列表搬运到 B 站：**下载 → 转码 → 元数据汉化 → 上传（仅自己可见）**，支持定时监控、按 YouTube 地址去重。

> 上传默认设为**仅自己可见**，你在手机/网页核实无误后再手动改公开，避免误发残破内容。

## ✨ 核心功能

- ✅ **全自动流水线**：下载 → 转码 → 汉化 → 上传，一条命令跑完
- ✅ **按 YouTube 地址去重**：`video_id`（URL 稳定部分）为 key，标题怎么变都不影响
- ✅ **画质优先**：yt-dlp 智能格式串，优先拿最高画质+音质，再转成 B 站兼容的 H.264+AAC
- ✅ **仅自己可见上传**：biliup 上传为私有，核实后再公开
- ✅ **转载合规**：自动带 `--copyright 2` + 转载来源（原 YouTube 链接）
- ✅ **定时监控**：自动发现新视频并搬运（cron 无人值守）
- ✅ **可扩展**：模块化设计，可加可视化、多平台等

## 🚀 快速开始

### 1. 环境准备

```bash
# Python 依赖
pip install -r requirements.txt

# 系统依赖
pip install yt-dlp biliup        # 下载 + 上传
brew install ffmpeg              # 转码（macOS）
```

### 2. B 站登录（首次，只需一次）

把 B 站 cookies 放到项目根目录 `cookies.json`（biliup 格式），或运行：

```bash
./run.sh --login
```

### 3. 配置监控目标

编辑 `config/monitors.yaml`：

```yaml
monitors:
  - name: "Naruto 音乐播放列表"
    url: "https://music.youtube.com/playlist?list=PLdJQK0KLodKg"
    limit: 10
    exclude: ["#short", " Shorts"]
```

### 4. 试跑（只看新视频）

```bash
./run.sh --dry-run
```

### 5. 正式全自动跑

```bash
# 监控 + 自动上传（仅自己可见）
./run.sh --upload --auto
```

## 📖 命令速查

| 目的 | 命令 |
|------|------|
| B 站登录（首次） | `./run.sh --login` |
| 试跑（看新视频） | `./run.sh --dry-run` |
| 监控 + 确认上传 | `./run.sh --upload` |
| 监控 + 自动上传 | `./run.sh --upload --auto` |
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
  下载 → 转码(H.264+AAC) → 元数据汉化
        │
        ▼
  [确认 / --auto] → biliup 上传（仅自己可见 + 转载）
        │
        ▼
  记录到 processed.json（含 BV 号 + source_url）
```

## 📁 目录结构

```
video_moving/
├── run.sh                       # 一键脚本
├── pyproject.toml               # 包定义 + 依赖
├── requirements.txt             # Python 依赖
├── config/
│   ├── monitors.yaml            # 监控目标配置 ← 编辑这个
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
├── data/                        # 生成数据（gitignore）
│   ├── downloads/               # 原始下载（每个视频一个子文件夹）
│   ├── output/                  # 处理产出
│   └── logs/                    # 日志
├── test/                        # 调试/测试产物（gitignore）
│   ├── diagnostics/             # 调试截图
│   ├── fixtures/                # 测试数据
│   └── samples/                 # 测试样片
└── legacy/                      # 遗留/不再使用的代码（保留本地，gitignore）
```

> **约定**：不再使用的代码/工具移入 `legacy/`，调试/测试产物移入 `test/`，**都不删除**。生成数据统一放 `data/`，保持根目录清爽。`data/`、`test/`、`legacy/`、`config/cookies.json` 均已 gitignore，不进开源仓库。

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
- **上传失败**：确认 `cookies.json` 有效；检查标题/简介是否含特殊字符
- **监控没发现新视频**：确认 `monitors.yaml` URL 正确；`processed.json` 记录了已处理视频，想重处理就删对应条目

## 📄 License

[MIT](LICENSE)
