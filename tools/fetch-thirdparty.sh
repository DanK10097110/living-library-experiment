#!/usr/bin/env bash
# Fetch the published ALFWorld agent code this project reuses (pinned commits recorded in third_party/SOURCES.md).
set -euo pipefail
mkdir -p /root/thirdparty && cd /root/thirdparty
for repo in ysymyth/ReAct haotiansun14/AdaPlanner langfengQ/verl-agent; do
    dir=$(basename "$repo")
    [ -d "$dir" ] || git clone -q --depth 1 "https://github.com/$repo" "$dir"
    echo "$repo $(git -C "$dir" rev-parse HEAD) | $(head -1 "$dir/LICENSE" 2>/dev/null || echo 'no LICENSE file')"
done
ls ReAct/prompts AdaPlanner/ALFWorld
wc -c verl-agent/agent_system/environments/prompts/alfworld.py
