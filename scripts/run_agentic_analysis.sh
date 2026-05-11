#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

UV_BIN="${UV:-uv}"
DRY_RUN=0
RUN_AGGREGATE=1
RUN_REPORTS=1
RUN_TRACES=1
RUN_PLOTS=1

MAIN_AGENTIC_CONFIG="experiments/main_agentic/configs/matrix.yaml"
VERIFIER_EXPOSURE_CONFIG="experiments/verifier_exposure/configs/default.yaml"
TEMPORAL_ROBUSTNESS_CONFIG="experiments/temporal_robustness/configs/default.yaml"
SKILL_INJECTION_CONFIG="experiments/skill_injection/configs/default.yaml"
MEMORY_ACCUMULATION_CONFIG="experiments/memory_accumulation/configs/default.yaml"

MAIN_AGENTIC_ROOT="results/agent_runs/experiments/main_agentic/matrix"

MAIN_AGENTIC_REPORTS_DIR="experiments/main_agentic/reports"
VERIFIER_EXPOSURE_REPORTS_DIR="experiments/verifier_exposure/reports"
TEMPORAL_ROBUSTNESS_REPORTS_DIR="experiments/temporal_robustness/reports"
SKILL_INJECTION_REPORTS_DIR="experiments/skill_injection/reports"

MAIN_AGENTIC_TRACES_DIR="experiments/main_agentic/reports/traces"
VERIFIER_EXPOSURE_TRACES_DIR="experiments/verifier_exposure/reports/traces"
TEMPORAL_ROBUSTNESS_TRACES_DIR="experiments/temporal_robustness/reports/traces"

MAIN_AGENTIC_RADAR_OUTPUT="experiments/main_agentic/reports/harness_radar.png"
BASELINE_DATA=""
MAIN_AGENTIC_HARNESS_ARGS=()

ALL_FAMILIES=(
  main_agentic
  verifier_exposure
  temporal_robustness
  skill_injection
  memory_accumulation
)
SELECTED_FAMILIES=()

usage() {
  cat <<'USAGE'
Usage: scripts/run_agentic_analysis.sh [options]

Run aggregate and available analysis tools for agentic experiment families.
By default this covers:
  - main_agentic
  - verifier_exposure
  - temporal_robustness
  - skill_injection
  - memory_accumulation

Available tools by family:
  main_agentic           aggregate, reports, traces, radar plot
  verifier_exposure      aggregate, reports, traces, exposure plots
  temporal_robustness    aggregate, reports, traces
  skill_injection        aggregate, reports, score plots
  memory_accumulation    aggregate

Selection:
  --family NAME          Run one family. May be repeated.
  --list-families        Print valid family names.

Configs:
  --main-agentic-config PATH
  --verifier-exposure-config PATH
  --temporal-robustness-config PATH
  --skill-injection-config PATH
  --memory-accumulation-config PATH
  --main-agentic-root PATH
                         Main-agentic matrix result root reused by ablation
                         aggregators. Default: results/agent_runs/experiments/main_agentic/matrix

Outputs:
  --main-agentic-reports-dir PATH
  --verifier-exposure-reports-dir PATH
  --temporal-robustness-reports-dir PATH
  --skill-injection-reports-dir PATH
  --main-agentic-traces-dir PATH
  --verifier-exposure-traces-dir PATH
  --temporal-robustness-traces-dir PATH
  --main-agentic-radar-output PATH
  --baseline-data PATH   Main-solver baseline source for main-agentic reports/radar.
  --harness NAME         Harness to include in the main-agentic radar plot.
                         May be repeated.

Step control:
  --aggregate-only       Run only aggregate tools.
  --skip-aggregate       Skip aggregate tools.
  --skip-reports         Skip report writers.
  --skip-traces          Skip trace viewers.
  --skip-plots           Skip plot tools.
  --dry-run              Print commands without running them.
  -h, --help             Show this help.

Environment:
  UV                     uv executable to use. Default: uv
USAGE
}

list_families() {
  printf '%s\n' "${ALL_FAMILIES[@]}"
}

is_valid_family() {
  local candidate="$1"
  local family
  for family in "${ALL_FAMILIES[@]}"; do
    if [[ "${candidate}" == "${family}" ]]; then
      return 0
    fi
  done
  return 1
}

run_step() {
  local family="$1"
  local label="$2"
  shift 2

  printf '\n==> [%s] %s\n' "${family}" "${label}"
  printf '    '
  printf '%q ' "$@"
  printf '\n'

  if [[ "${DRY_RUN}" -eq 0 ]]; then
    "$@"
  fi
}

run_main_agentic() {
  local family="main_agentic"
  local config_args=(--config "${MAIN_AGENTIC_CONFIG}")
  local baseline_args=()
  if [[ -n "${BASELINE_DATA}" ]]; then
    baseline_args=(--baseline-data "${BASELINE_DATA}")
  fi

  if [[ "${RUN_AGGREGATE}" -eq 1 ]]; then
    run_step "${family}" "Aggregate runs" \
      "${UV_BIN}" run python experiments/main_agentic/aggregate.py \
      "${config_args[@]}"
  fi

  if [[ "${RUN_REPORTS}" -eq 1 ]]; then
    run_step "${family}" "Write benchmark reports" \
      "${UV_BIN}" run python experiments/main_agentic/write_reports.py \
      "${config_args[@]}" \
      --reports-dir "${MAIN_AGENTIC_REPORTS_DIR}" \
      "${baseline_args[@]}"
  fi

  if [[ "${RUN_TRACES}" -eq 1 ]]; then
    run_step "${family}" "Build trace viewer" \
      "${UV_BIN}" run python experiments/main_agentic/trace_viewer.py \
      "${config_args[@]}" \
      --output-dir "${MAIN_AGENTIC_TRACES_DIR}"
  fi

  if [[ "${RUN_PLOTS}" -eq 1 ]]; then
    run_step "${family}" "Plot harness radar" \
      "${UV_BIN}" run python experiments/main_agentic/plot_radar.py \
      "${config_args[@]}" \
      --output "${MAIN_AGENTIC_RADAR_OUTPUT}" \
      "${MAIN_AGENTIC_HARNESS_ARGS[@]}" \
      "${baseline_args[@]}"
  fi
}

run_verifier_exposure() {
  local family="verifier_exposure"
  local config_args=(--config "${VERIFIER_EXPOSURE_CONFIG}")

  if [[ "${RUN_AGGREGATE}" -eq 1 ]]; then
    run_step "${family}" "Aggregate runs" \
      "${UV_BIN}" run python experiments/verifier_exposure/aggregate.py \
      "${config_args[@]}" \
      --main-agentic-root "${MAIN_AGENTIC_ROOT}"
  fi

  if [[ "${RUN_REPORTS}" -eq 1 ]]; then
    run_step "${family}" "Write exposure reports" \
      "${UV_BIN}" run python experiments/verifier_exposure/write_reports.py \
      "${config_args[@]}" \
      --reports-dir "${VERIFIER_EXPOSURE_REPORTS_DIR}"
  fi

  if [[ "${RUN_TRACES}" -eq 1 ]]; then
    run_step "${family}" "Build trace viewer" \
      "${UV_BIN}" run python experiments/verifier_exposure/trace_viewer.py \
      "${config_args[@]}" \
      --output-dir "${VERIFIER_EXPOSURE_TRACES_DIR}"
  fi

  if [[ "${RUN_PLOTS}" -eq 1 ]]; then
    run_step "${family}" "Plot exposure scores" \
      "${UV_BIN}" run python experiments/verifier_exposure/plot_exposure.py \
      "${config_args[@]}" \
      --reports-dir "${VERIFIER_EXPOSURE_REPORTS_DIR}"
  fi
}

run_temporal_robustness() {
  local family="temporal_robustness"
  local config_args=(--config "${TEMPORAL_ROBUSTNESS_CONFIG}")

  if [[ "${RUN_AGGREGATE}" -eq 1 ]]; then
    run_step "${family}" "Aggregate runs" \
      "${UV_BIN}" run python experiments/temporal_robustness/aggregate.py \
      "${config_args[@]}"
  fi

  if [[ "${RUN_REPORTS}" -eq 1 ]]; then
    run_step "${family}" "Write robustness reports" \
      "${UV_BIN}" run python experiments/temporal_robustness/write_reports.py \
      "${config_args[@]}" \
      --reports-dir "${TEMPORAL_ROBUSTNESS_REPORTS_DIR}"
  fi

  if [[ "${RUN_TRACES}" -eq 1 ]]; then
    run_step "${family}" "Build trace viewer" \
      "${UV_BIN}" run python experiments/temporal_robustness/trace_viewer.py \
      "${config_args[@]}" \
      --output-dir "${TEMPORAL_ROBUSTNESS_TRACES_DIR}"
  fi
}

run_skill_injection() {
  local family="skill_injection"
  local config_args=(--config "${SKILL_INJECTION_CONFIG}")

  if [[ "${RUN_AGGREGATE}" -eq 1 ]]; then
    run_step "${family}" "Aggregate runs" \
      "${UV_BIN}" run python experiments/skill_injection/aggregate.py \
      "${config_args[@]}" \
      --main-agentic-root "${MAIN_AGENTIC_ROOT}"
  fi

  if [[ "${RUN_REPORTS}" -eq 1 ]]; then
    run_step "${family}" "Write skill reports" \
      "${UV_BIN}" run python experiments/skill_injection/write_reports.py \
      "${config_args[@]}" \
      --reports-dir "${SKILL_INJECTION_REPORTS_DIR}"
  fi

  if [[ "${RUN_PLOTS}" -eq 1 ]]; then
    run_step "${family}" "Plot skill scores" \
      "${UV_BIN}" run python experiments/skill_injection/plot_scores.py \
      "${config_args[@]}" \
      --reports-dir "${SKILL_INJECTION_REPORTS_DIR}"
  fi
}

run_memory_accumulation() {
  local family="memory_accumulation"
  local config_args=(--config "${MEMORY_ACCUMULATION_CONFIG}")

  if [[ "${RUN_AGGREGATE}" -eq 1 ]]; then
    run_step "${family}" "Aggregate runs" \
      "${UV_BIN}" run python experiments/memory_accumulation/aggregate.py \
      "${config_args[@]}" \
      --main-agentic-root "${MAIN_AGENTIC_ROOT}"
  fi
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --family)
      if ! is_valid_family "${2:?--family requires a name}"; then
        echo "Unknown family: $2" >&2
        echo "Valid families:" >&2
        list_families >&2
        exit 2
      fi
      SELECTED_FAMILIES+=("$2")
      shift 2
      ;;
    --list-families)
      list_families
      exit 0
      ;;
    --main-agentic-config)
      MAIN_AGENTIC_CONFIG="${2:?--main-agentic-config requires a path}"
      shift 2
      ;;
    --verifier-exposure-config)
      VERIFIER_EXPOSURE_CONFIG="${2:?--verifier-exposure-config requires a path}"
      shift 2
      ;;
    --temporal-robustness-config)
      TEMPORAL_ROBUSTNESS_CONFIG="${2:?--temporal-robustness-config requires a path}"
      shift 2
      ;;
    --skill-injection-config)
      SKILL_INJECTION_CONFIG="${2:?--skill-injection-config requires a path}"
      shift 2
      ;;
    --memory-accumulation-config)
      MEMORY_ACCUMULATION_CONFIG="${2:?--memory-accumulation-config requires a path}"
      shift 2
      ;;
    --main-agentic-root)
      MAIN_AGENTIC_ROOT="${2:?--main-agentic-root requires a path}"
      shift 2
      ;;
    --main-agentic-reports-dir)
      MAIN_AGENTIC_REPORTS_DIR="${2:?--main-agentic-reports-dir requires a path}"
      shift 2
      ;;
    --verifier-exposure-reports-dir)
      VERIFIER_EXPOSURE_REPORTS_DIR="${2:?--verifier-exposure-reports-dir requires a path}"
      shift 2
      ;;
    --temporal-robustness-reports-dir)
      TEMPORAL_ROBUSTNESS_REPORTS_DIR="${2:?--temporal-robustness-reports-dir requires a path}"
      shift 2
      ;;
    --skill-injection-reports-dir)
      SKILL_INJECTION_REPORTS_DIR="${2:?--skill-injection-reports-dir requires a path}"
      shift 2
      ;;
    --main-agentic-traces-dir)
      MAIN_AGENTIC_TRACES_DIR="${2:?--main-agentic-traces-dir requires a path}"
      shift 2
      ;;
    --verifier-exposure-traces-dir)
      VERIFIER_EXPOSURE_TRACES_DIR="${2:?--verifier-exposure-traces-dir requires a path}"
      shift 2
      ;;
    --temporal-robustness-traces-dir)
      TEMPORAL_ROBUSTNESS_TRACES_DIR="${2:?--temporal-robustness-traces-dir requires a path}"
      shift 2
      ;;
    --main-agentic-radar-output)
      MAIN_AGENTIC_RADAR_OUTPUT="${2:?--main-agentic-radar-output requires a path}"
      shift 2
      ;;
    --baseline-data)
      BASELINE_DATA="${2:?--baseline-data requires a path}"
      shift 2
      ;;
    --harness)
      MAIN_AGENTIC_HARNESS_ARGS+=(--harness "${2:?--harness requires a name}")
      shift 2
      ;;
    --aggregate-only)
      RUN_AGGREGATE=1
      RUN_REPORTS=0
      RUN_TRACES=0
      RUN_PLOTS=0
      shift
      ;;
    --skip-aggregate)
      RUN_AGGREGATE=0
      shift
      ;;
    --skip-reports)
      RUN_REPORTS=0
      shift
      ;;
    --skip-traces)
      RUN_TRACES=0
      shift
      ;;
    --skip-plots)
      RUN_PLOTS=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Run with --help for usage." >&2
      exit 2
      ;;
  esac
done

cd "${REPO_ROOT}"

if [[ "${#SELECTED_FAMILIES[@]}" -eq 0 ]]; then
  SELECTED_FAMILIES=("${ALL_FAMILIES[@]}")
fi

for family in "${SELECTED_FAMILIES[@]}"; do
  case "${family}" in
    main_agentic)
      run_main_agentic
      ;;
    verifier_exposure)
      run_verifier_exposure
      ;;
    temporal_robustness)
      run_temporal_robustness
      ;;
    skill_injection)
      run_skill_injection
      ;;
    memory_accumulation)
      run_memory_accumulation
      ;;
  esac
done
