#!/usr/bin/env bash
#
# video_moving 一键运行脚本
#
# 用法：
#   ./run.sh                          # 监控一轮（只处理，不上传）
#   ./run.sh --upload                 # 监控 + 上传（每个视频确认后传）
#   ./run.sh --upload --auto          # 监控 + 自动上传（跳过确认）
#   ./run.sh --dry-run                # 只看有哪些新视频，不处理
#   ./run.sh --login                  # B 站扫码登录（首次使用）
#   ./run.sh --once "https://youtu.be/XXXXX"              # 单个视频
#   ./run.sh --once "https://youtu.be/XXXXX" --upload     # 单个 + 上传
#
# 所有参数会透传给 python -m src.monitor 或 src.pipeline

set -euo pipefail

# 切到项目目录（不管从哪里调用）
cd "$(dirname "$0")"

# 激活 venv
source .venv/bin/activate

# 默认动作：跑一轮监控
MODE="monitor"
ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --once)
            MODE="single"
            shift
            URL="$1"
            shift
            ;;
        --login)
            MODE="login"
            shift
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done

case "$MODE" in
    login)
        echo "🔐 启动 B 站扫码登录..."
        python -m src.monitor --login
        ;;
    single)
        python -m src.pipeline "$URL" "${ARGS[@]}"
        ;;
    monitor)
        python -m src.monitor "${ARGS[@]}"
        ;;
esac