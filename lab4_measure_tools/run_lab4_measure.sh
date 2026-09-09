#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BIN="${BIN:-build/NULL/gem5.opt}"
WARMUP="${WARMUP:-20000}"
MEASURE="${MEASURE:-100000}"
RATES="${RATES:-0.01 0.05 0.10 0.15 0.20 0.30 0.40 0.60 0.80}"
SEEDS="${SEEDS:-1}"
PATTERNS="${PATTERNS:-uniform_random}"
VCS_LIST="${VCS_LIST:-4}"
NODES="${NODES:-256}"
JOBS="${JOBS:-1}"
RUN_TIMEOUT="${RUN_TIMEOUT:-20m}"
BUDGET_SECONDS="${BUDGET_SECONDS:-0}"
case "$NODES" in
  64) MESH_ROWS=8; DIMS2=8,8; DIMS3=4,4,4; DEFAULT_CASES="mesh2_xy torus2_dor torus2_adaptive torus3_dor torus3_adaptive" ;;
  256) MESH_ROWS=16; DIMS2=16,16; DIMS3=8,8,4; DEFAULT_CASES="mesh2_xy torus2_dor torus2_adaptive torus3_dor torus3_adaptive torus4_dor torus4_adaptive" ;;
  *) echo "Supported NODES: 64 or 256" >&2; exit 1 ;;
esac
CASES="${CASES:-$DEFAULT_CASES}"
RESULTS="${RESULTS:-m5out/lab4_measure_$(date +%Y%m%d_%H%M%S)_$$}"
if ! [[ "$JOBS" =~ ^[1-9][0-9]*$ ]]; then
  echo "JOBS must be a positive integer" >&2
  exit 1
fi
if ! [[ "$BUDGET_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "BUDGET_SECONDS must be a nonnegative integer" >&2
  exit 1
fi
for CASE in $CASES; do
  if [[ "$CASE" == torus4_* && "$NODES" != 256 ]]; then
    echo "4D cases require NODES=256 to avoid dimension-size-2 parallel links" >&2
    exit 1
  fi
done
command -v timeout > /dev/null

test -x "$BIN"
test -f configs/example/garnet_synth_traffic.py
test ! -e "$RESULTS"
mkdir -p "$RESULTS"
python3 "$SCRIPT_DIR/lab4_measure.py" prepare "$PWD"
git rev-parse HEAD > "$RESULTS/commit.txt"
git status --short > "$RESULTS/git-status.txt"
git diff > "$RESULTS/source.diff"
sha256sum "$BIN" > "$RESULTS/binary.sha256"
printf 'warmup=%s\nmeasure=%s\nrates=%s\nseeds=%s\ncases=%s\npatterns=%s\nvcs=%s\n' \
  "$WARMUP" "$MEASURE" "$RATES" "$SEEDS" "$CASES" "$PATTERNS" "$VCS_LIST" > "$RESULTS/settings.txt"
printf 'nodes=%s\njobs=%s\nrun_timeout=%s\nbudget_seconds=%s\n' \
  "$NODES" "$JOBS" "$RUN_TIMEOUT" "$BUDGET_SECONDS" >> "$RESULTS/settings.txt"
PIDS=()
FINISHED=0
FAILED=0
START_SECONDS=$SECONDS

reap_one() {
  if wait "${PIDS[0]}"; then
    :
  else
    FAILED=$((FAILED + 1))
  fi
  PIDS=("${PIDS[@]:1}")
  FINISHED=$((FINISHED + 1))
  python3 "$SCRIPT_DIR/lab4_measure.py" merge "$RESULTS"
  echo "Completed=$FINISHED failed=$FAILED elapsed=$((SECONDS - START_SECONDS))s"
}

run_point() {
  OUT="$RESULTS/n${NODES}_${CASE}_${PATTERN}_vc${VCS}_r${RATE}_s${SEED}"
  mkdir -p "$OUT"
  COMMAND=("$BIN" -d "$OUT" configs/example/garnet_synth_measure.py
    --network=garnet --num-cpus="$NODES" --num-dirs="$NODES"
    --sys-clock=2GHz --ruby-clock=2GHz
    --router-latency=1 --link-latency=1 --link-width-bits=128
    --vcs-per-vnet="$VCS" --inj-vnet=0 --synthetic="$PATTERN"
    --injectionrate="$RATE" --num-packets-max=-1
    --garnet-deadlock-threshold="$((WARMUP + MEASURE + 10000))"
    "${OPTIONS[@]}")
  printf '%q ' "${COMMAND[@]}" > "$OUT/command.sh"
  printf '\n' >> "$OUT/command.sh"
  printf 'LAB4_WARMUP=%s\nLAB4_MEASURE=%s\nLAB4_SEED=%s\n' \
    "$WARMUP" "$MEASURE" "$SEED" > "$OUT/environment.txt"
  echo "Running $CASE pattern=$PATTERN vcs=$VCS rate=$RATE seed=$SEED"
  POINT_START=$SECONDS
  STATUS=0
  timeout --kill-after=30s "$RUN_TIMEOUT" env \
    LAB4_WARMUP="$WARMUP" LAB4_MEASURE="$MEASURE" LAB4_SEED="$SEED" \
    "${COMMAND[@]}" > "$OUT/run.log" 2>&1 || STATUS=$?
  printf '%s\n' "$STATUS" > "$OUT/exit-code.txt"
  printf '%s\n' "$((SECONDS - POINT_START))" > "$OUT/wall-seconds.txt"
  PARSE_STATUS=0
  python3 "$SCRIPT_DIR/lab4_measure.py" collect "$OUT" "$OUT/result.csv" \
    "$CASE" "$RATE" "$SEED" "$WARMUP" "$MEASURE" "$STATUS" \
    --pattern "$PATTERN" --vcs "$VCS" --nodes "$NODES" || PARSE_STATUS=$?
  touch "$OUT/complete"
  if ((STATUS != 0)); then
    tail -n 15 "$OUT/run.log"
    echo "Run failed (124 indicates timeout): $OUT"
    exit "$STATUS"
  fi
  return "$PARSE_STATUS"
}

for CASE in $CASES; do
  CASE_VCS_LIST="$VCS_LIST"
  case "$CASE" in
    torus3_dor_raw) OPTIONS=(--topology=NDtorus --torus-dims="$DIMS3" --routing-algorithm=3) ;;
    torus3_adaptive_raw) OPTIONS=(--topology=NDtorus --torus-dims="$DIMS3" --routing-algorithm=4) ;;
    mesh2_xy) OPTIONS=(--topology=Mesh_XY --mesh-rows="$MESH_ROWS" --routing-algorithm=1) ;;
    torus2_dor) OPTIONS=(--topology=NDtorus --torus-dims="$DIMS2" --routing-algorithm=3 --escape) ;;
    torus2_adaptive) OPTIONS=(--topology=NDtorus --torus-dims="$DIMS2" --routing-algorithm=4 --escape) ;;
    torus2_dor_nosticky) OPTIONS=(--topology=NDtorus --torus-dims="$DIMS2" --routing-algorithm=3 --escape --no-sticky) ;;
    torus3_dor) OPTIONS=(--topology=NDtorus --torus-dims="$DIMS3" --routing-algorithm=3 --escape) ;;
    torus3_adaptive) OPTIONS=(--topology=NDtorus --torus-dims="$DIMS3" --routing-algorithm=4 --escape) ;;
    torus3_dor_nosticky) OPTIONS=(--topology=NDtorus --torus-dims="$DIMS3" --routing-algorithm=3 --escape --no-sticky) ;;
    torus4_dor) OPTIONS=(--topology=NDtorus --torus-dims=4,4,4,4 --routing-algorithm=3 --escape) ;;
    torus4_adaptive) OPTIONS=(--topology=NDtorus --torus-dims=4,4,4,4 --routing-algorithm=4 --escape) ;;
    torus4_dor_nosticky) OPTIONS=(--topology=NDtorus --torus-dims=4,4,4,4 --routing-algorithm=3 --escape --no-sticky) ;;
    torus1_adaptive_balanced) OPTIONS=(--topology=NDtorus --torus-dims=256 --routing-algorithm=4 --escape); CASE_VCS_LIST=12 ;;
    torus2_adaptive_balanced) OPTIONS=(--topology=NDtorus --torus-dims=16,16 --routing-algorithm=4 --escape); CASE_VCS_LIST=6 ;;
    torus3_adaptive_balanced) OPTIONS=(--topology=NDtorus --torus-dims=8,8,4 --routing-algorithm=4 --escape); CASE_VCS_LIST=4 ;;
    torus4_adaptive_balanced) OPTIONS=(--topology=NDtorus --torus-dims=4,4,4,4 --routing-algorithm=4 --escape); CASE_VCS_LIST=3 ;;
    torus3_escape2) OPTIONS=(--topology=NDtorus --torus-dims="$DIMS3" --routing-algorithm=3 --escape); CASE_VCS_LIST=2 ;;
    *) echo "Unknown case: $CASE" >&2; exit 1 ;;
  esac
  for VCS in $CASE_VCS_LIST; do
    if ! [[ "$VCS" =~ ^[0-9]+$ ]] || ((VCS < 2)); then
      echo "VC count must be an integer >= 2: $VCS" >&2
      exit 1
    fi
    for PATTERN in $PATTERNS; do
      case "$PATTERN" in
        uniform_random|neighbor|tornado|transpose|bit_complement|bit_reverse|bit_rotation|shuffle) ;;
        *) echo "Unknown pattern: $PATTERN" >&2; exit 1 ;;
      esac
      for RATE in $RATES; do
        for SEED in $SEEDS; do
          if ((${#PIDS[@]} >= JOBS)); then
            reap_one
          fi
          if ((BUDGET_SECONDS > 0 && SECONDS - START_SECONDS >= BUDGET_SECONDS)); then
            echo "Time budget reached; waiting for running simulations"
            break 5
          fi
          run_point &
          PIDS+=("$!")
        done
      done
    done
  done
done
while ((${#PIDS[@]} > 0)); do
  reap_one
done
echo "Results: $RESULTS/summary.csv"
if ((FAILED > 0)); then
  exit 1
fi
