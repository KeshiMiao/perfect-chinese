#!/usr/bin/env bash
# 在 4.5 与 5.x 上各跑一次无头冒烟测试，使用临时脚本/配置目录，不碰用户配置。
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
BLENDER_BIN="${BLENDER_BIN:-}"
CANDIDATES=(
  "$HOME/.blender/stable/blender-4.5.16-macos-arm64+lts.3f6797307da5/Blender.app/Contents/MacOS/Blender"
  "$HOME/.blender/stable/blender-5.2.4-macos-arm64+lts.cd5dc428cce1/Blender.app/Contents/MacOS/Blender"
)
if [ -n "$BLENDER_BIN" ]; then
  CANDIDATES=("$BLENDER_BIN")
fi

status=0
ran=0
for bin in "${CANDIDATES[@]}"; do
  if [ ! -x "$bin" ]; then
    echo "skip（未安装）：$bin"
    continue
  fi
  ran=$((ran + 1))
  tmp="$(mktemp -d)"
  mkdir -p "$tmp/ext/user_default" "$tmp/scripts" "$tmp/config" "$tmp/data"
  rsync -a \
    --exclude .git --exclude __pycache__ --exclude tests --exclude doc \
    --exclude .env --exclude .venv --exclude .vscode --exclude data \
    "$SRC/" "$tmp/ext/user_default/perfect_chinese/"

  env_common=(BLENDER_USER_EXTENSIONS="$tmp/ext" BLENDER_USER_SCRIPTS="$tmp/scripts" BLENDER_USER_CONFIG="$tmp/config" BLENDER_USER_DATAFILES="$tmp/data")

  echo "=== $("$bin" --version | head -1)"
  if env "${env_common[@]}" "$bin" -b --factory-startup --python "$SRC/tests/smoke.py" -- 1 \
      && env "${env_common[@]}" "$bin" -b --python "$SRC/tests/smoke.py" -- 2; then
    echo "=== PASS"
  else
    echo "=== FAIL"
    status=1
  fi

  # 阶段 3：老用户（缓存目录已存在）+ 界面本来就是中文，启用插件不应改语言或开关
  mkdir -p "$tmp/config3" "$tmp/data3/perfect_chinese"
  if env BLENDER_USER_EXTENSIONS="$tmp/ext" BLENDER_USER_SCRIPTS="$tmp/scripts" \
      BLENDER_USER_CONFIG="$tmp/config3" BLENDER_USER_DATAFILES="$tmp/data3" \
      "$bin" -b --factory-startup --python "$SRC/tests/smoke.py" -- 3; then
    echo "=== PASS（中文环境启用）"
  else
    echo "=== FAIL（中文环境启用）"
    status=1
  fi
  rm -rf "$tmp"
done

if [ "$ran" -eq 0 ]; then
  echo "没有可用的 Blender：请设置 BLENDER_BIN 或安装 4.5 / 5.x" >&2
  exit 1
fi
exit $status
