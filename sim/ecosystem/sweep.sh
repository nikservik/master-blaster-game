#!/bin/bash
# Серия прогонов для сравнения вариантов на одном seed. Запуск в WSL из папки проекта: bash sweep.sh <серия>.
# Каждая строка: имя вариант животных дней режим. Отчёты — ~/ml/out/<серия>_<имя>/report.json.
set -u
SERIES=${1:-scale}
run() {
  local name=$1 variant=$2 animals=$3 days=$4 mode=$5; shift 5
  echo "== $name $(date +%T)"
  uv run python -m eco.run --variant "$variant" --oracle kev --animals "$animals" --days "$days" --time "$mode" \
    --seed 1 --run "${SERIES}_${name}" --quiet "$@" || echo "FAILED $name"
}
case $SERIES in
scale)
  for v in V0; do
    run v0_100 V0 100 1 batched; run v0_1k V0 1000 1 batched; run v0_10k V0 10000 0.2 batched; run v0_50k V0 50000 0.05 batched
  done
  run v1_100 V1 100 0.5 batched; run v1_1k V1 1000 0.1 batched; run v1_10k V1 10000 0.01 batched
  run v2_100 V2 100 0.5 batched; run v2_1k V2 1000 0.1 batched; run v2_10k V2 10000 0.01 batched
  run v3_100 V3 100 0.5 batched; run v3_1k V3 1000 0.2 batched; run v3_10k V3 10000 0.03 batched; run v3_50k V3 50000 0.01 batched
  run v4_1k V4 1000 0.2 batched --observer 250,250; run v4_10k V4 10000 0.03 batched; run v4_50k V4 50000 0.01 batched
  run v5_100 V5 100 0.5 batched; run v5_1k V5 1000 0.2 batched; run v5_10k V5 10000 0.03 batched; run v5_50k V5 50000 0.01 batched
  ;;
realtime)
  run v1_100 V1 100 0.05 realtime; run v1_500 V1 500 0.05 realtime; run v1_1k V1 1000 0.05 realtime
  run v2_1k V2 1000 0.05 realtime; run v3_1k V3 1000 0.05 realtime; run v4_1k V4 1000 0.05 realtime
  run v5_1k V5 1000 0.05 realtime; run v5_10k V5 10000 0.02 realtime; run v4_10k V4 10000 0.02 realtime
  run burst_v1 V1 100 0.01 realtime --scenario wolves; run burst_v2 V2 100 0.01 realtime --scenario wolves
  run burst_v4 V4 1000 0.01 realtime --scenario wolves; run burst_v5 V5 1000 0.01 realtime --scenario wolves
  ;;
dynamics)
  run v0_1k V0 1000 10 batched; run v3_1k V3 1000 10 batched; run v4_1k V4 1000 10 batched --observer 250,250
  run v5_1k V5 1000 10 batched; run v0_300 V0 300 3 batched; run v1_300 V1 300 3 batched; run v2_300 V2 300 3 batched
  ;;
esac
echo "== done $(date +%T)"
