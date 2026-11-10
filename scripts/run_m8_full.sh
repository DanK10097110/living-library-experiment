#!/usr/bin/env bash
# run_m8_full.sh — M8: Full 300-episode practice + 140-episode valid_seen evaluation
#
# Runs:
#   1. System E-  on train       (300 episodes)  — practice
#   2. System C   on train       (300 episodes)  — practice
#   3. System E-  on valid_seen  (140 episodes)  — evaluation
#   4. System C   on valid_seen  (140 episodes)  — evaluation
#
# Usage (from repo root, with venv active):
#   bash scripts/run_m8_full.sh 2>&1 | tee results/run_m8.log
#
# IMPORTANT: valid_unseen is never touched here.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS="$REPO_ROOT/results"
PYTHON=python

echo "============================================================"
echo "  M8 Full Pilot Run — $(date)"
echo "  Repo: $REPO_ROOT"
echo "============================================================"

# ── Step 1: Practice — System E- (300 episodes, train) ──────────────────────
echo ""
echo "[STEP 1/4] System E-  |  train  |  300 episodes"
echo "------------------------------------------------------------"
$PYTHON "$REPO_ROOT/scripts/run_pilot.py" \
    --condition E- \
    --split train \
    --episodes 300 \
    --seed 42 \
    --output-dir "$RESULTS"

echo "[STEP 1/4] DONE"

# ── Step 2: Practice — System C (300 episodes, train) ───────────────────────
echo ""
echo "[STEP 2/4] System C   |  train  |  300 episodes"
echo "------------------------------------------------------------"
$PYTHON "$REPO_ROOT/scripts/run_pilot.py" \
    --condition C \
    --split train \
    --episodes 300 \
    --seed 42 \
    --output-dir "$RESULTS"

echo "[STEP 2/4] DONE"

# ── Step 3: Evaluate — System E- (140 episodes, valid_seen) ─────────────────
echo ""
echo "[STEP 3/4] System E-  |  valid_seen  |  140 episodes"
echo "------------------------------------------------------------"
$PYTHON "$REPO_ROOT/scripts/run_pilot.py" \
    --condition E- \
    --split valid_seen \
    --episodes 140 \
    --seed 42 \
    --output-dir "$RESULTS/eval"

echo "[STEP 3/4] DONE"

# ── Step 4: Evaluate — System C (140 episodes, valid_seen) ──────────────────
echo ""
echo "[STEP 4/4] System C   |  valid_seen  |  140 episodes"
echo "------------------------------------------------------------"
$PYTHON "$REPO_ROOT/scripts/run_pilot.py" \
    --condition C \
    --split valid_seen \
    --episodes 140 \
    --seed 42 \
    --output-dir "$RESULTS/eval"

echo "[STEP 4/4] DONE"

# ── Step 5: Generate M10 final report ───────────────────────────────────────
echo ""
echo "[STEP 5/5] Generating M10 pilot report..."
$PYTHON "$REPO_ROOT/scripts/generate_pilot_report.py" \
    --results-dir "$RESULTS" \
    --output "$RESULTS/pilot_report.md"

echo ""
echo "============================================================"
echo "  M8–M10 Complete — $(date)"
echo "  Results: $RESULTS"
echo "  Report:  $RESULTS/pilot_report.md"
echo "============================================================"
