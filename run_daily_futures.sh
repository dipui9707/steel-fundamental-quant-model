#!/usr/bin/env bash
# ==============================================================================
# 钢材产业基本面量化系统 - 期货端数据日度全自动更新统一入口脚本
# ==============================================================================
set -e

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

PYTHON_EXEC="$BASE_DIR/.venv/bin/python"

if [ ! -f "$PYTHON_EXEC" ]; then
    echo "❌ 错误: 未找到虚拟环境解释器: $PYTHON_EXEC"
    exit 1
fi

# 调用流水线调度器，透传所有参数（如 --date 2026-09-21 或 --mock）
"$PYTHON_EXEC" "$BASE_DIR/scripts/run_daily_futures_pipeline.py" "$@"
