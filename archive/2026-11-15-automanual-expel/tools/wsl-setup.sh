#!/usr/bin/env bash
# One-time Linux (WSL) setup for the ALFWorld experiment. Safe to rerun.
# Usage (from Windows): wsl -d Ubuntu-24.04 -u root -- bash "/mnt/c/Git Repos/living-library-experiment/tools/wsl-setup.sh"
set -euo pipefail
REPO="/mnt/c/Git Repos/living-library-experiment"
VENV=/root/venvs/living
DATA=/root/.cache/alfworld
BGE_REVISION=5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

echo '== system packages'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq build-essential curl git default-jre-headless > /dev/null

echo '== python 3.11 environment (uv)'
if ! command -v uv > /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="/root/.local/bin:$PATH"
[ -x "$VENV/bin/python" ] || uv venv --python 3.11 "$VENV"
# CPU-only torch: embeddings run on CPU, the GPU belongs to the model server.
uv pip install --python "$VENV/bin/python" -q torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python "$VENV/bin/python" -q -e "$REPO[alfworld,embeddings]"

echo '== ALFWorld game data'
if [ ! -d "$DATA/json_2.1.1/valid_unseen" ]; then
    ALFWORLD_DATA="$DATA" "$VENV/bin/alfworld-download"
fi

echo '== embedding model (pinned revision)'
"$VENV/bin/python" - <<PY
from huggingface_hub import snapshot_download
print(snapshot_download('BAAI/bge-small-en-v1.5', revision='$BGE_REVISION'))
PY

echo '== manifest'
mkdir -p /root/ll-runs
"$VENV/bin/python" -m living_library manifest --data-root "$DATA/json_2.1.1" --output /root/ll-runs/manifest.json
"$VENV/bin/python" - <<'PY'
import json
m = json.load(open('/root/ll-runs/manifest.json'))
print({k: len(v) for k, v in m['splits'].items()})
PY
echo '== done'
