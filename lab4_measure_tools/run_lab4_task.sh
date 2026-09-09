#!/usr/bin/env bash
set -euo pipefail

TASK="${1:-}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RATES="0.01 0.05 0.10 0.15 0.20 0.25 0.30 0.35 0.40 0.45 0.50 0.55 0.60 0.65 0.70 0.75 0.80 0.85 0.90"
BASE="m5out/lab4_experiments"
STAMP="$(date +%Y%m%d_%H%M%S)_$$"
RESULTS="$BASE/${TASK}_${STAMP}"

case "$TASK" in
  task1)
    NODES=64
    DEFAULT_JOBS=4
    CASES="torus3_dor_raw torus3_adaptive_raw torus3_dor torus3_dor_nosticky torus3_adaptive"
    PATTERNS="uniform_random bit_complement bit_reverse bit_rotation shuffle"
    VCS_LIST=4
    ;;
  task2)
    NODES=64
    DEFAULT_JOBS=4
    CASES="torus3_dor_raw torus3_adaptive_raw torus3_dor torus3_dor_nosticky torus3_adaptive"
    PATTERNS=uniform_random
    VCS_LIST="2 3 4 6 8"
    ;;
  task3)
    NODES=256
    DEFAULT_JOBS=1
    CASES="torus1_adaptive_balanced torus2_adaptive_balanced torus3_adaptive_balanced torus4_adaptive_balanced"
    PATTERNS="uniform_random bit_reverse"
    VCS_LIST=4
    ;;
  *)
    echo "Usage: $0 task1|task2|task3" >&2
    exit 2
    ;;
esac

mkdir -p "$BASE"
ln -sfn "$(basename "$RESULTS")" "$BASE/${TASK}_latest"
STATUS=0
env RESULTS="$RESULTS" NODES="$NODES" JOBS="${JOBS:-$DEFAULT_JOBS}" \
  WARMUP="${WARMUP:-1000}" MEASURE="${MEASURE:-10000}" \
  RUN_TIMEOUT="${RUN_TIMEOUT:-10m}" BUDGET_SECONDS="${BUDGET_SECONDS:-0}" \
  RATES="$RATES" SEEDS="${SEEDS:-1}" CASES="$CASES" PATTERNS="$PATTERNS" \
  VCS_LIST="$VCS_LIST" BIN="${BIN:-build/NULL/gem5.opt}" \
  bash "$SCRIPT_DIR/run_lab4_measure.sh" || STATUS=$?

python3 "$SCRIPT_DIR/lab4_measure.py" merge "$RESULTS"
if [[ -s "$RESULTS/summary.csv" ]]; then
  python3 "$SCRIPT_DIR/plot_lab4_results.py" "$TASK" "$RESULTS"
else
  echo "No completed points were collected" >&2
fi
echo "Task output: $RESULTS"
echo "Latest link: $BASE/${TASK}_latest"
exit "$STATUS"
