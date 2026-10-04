#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PYCACHE="${JOBFLOW_PYCACHE:-${PYTHONPYCACHEPREFIX:-/private/tmp/jobflow-pycache}}"
export PYTHONPYCACHEPREFIX="$PYCACHE"

if [ ! -f "00-工作流系统/state/current.json" ]; then
  echo "ERROR: state 不存在；先运行 python3 00-工作流系统/bin/jobflow.py init" >&2
  exit 1
fi

python3 00-工作流系统/bin/jobflow.py validate
python3 00-工作流系统/bin/memoryctl.py validate
python3 00-工作流系统/bin/jobflow.py cold-start-check
python3 00-工作流系统/bin/jobflow.py render-views
python3 00-工作流系统/bin/jobflow.py golden-check
python3 00-工作流系统/bin/jobflow.py evidence-verify
python3 -m unittest -q 00-工作流系统/tests/test_jobflow.py
python3 -m unittest -q 00-工作流系统/tests/test_engine_diff.py
python3 -m unittest -q 00-工作流系统/tests/test_progress.py
python3 -m unittest -q 00-工作流系统/tests/test_catalog.py
python3 -m unittest -q 00-工作流系统/tests/test_ontrace.py
python3 -m unittest -q 00-工作流系统/tests/test_priority.py
python3 -m unittest -q 00-工作流系统/tests/test_memory.py
python3 -m unittest -q 00-工作流系统/tests/test_screening.py
python3 -m unittest -q 00-工作流系统/tests/test_onboarding.py
python3 -m unittest -q 00-工作流系统/tests/test_setup.py
python3 -m unittest -q 00-工作流系统/tests/test_inbound_digest.py
python3 -m unittest -q 00-工作流系统/tests/test_report_v2.py
python3 -m unittest -q 00-工作流系统/tests/test_today.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q 00-工作流系统/dashboard/test_server.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q \
  00-工作流系统/local-control/test_runtime_store.py \
  00-工作流系统/local-control/test_runtime_adapters.py \
  00-工作流系统/local-control/test_jobflowd.py
source "$ROOT/00-工作流系统/scripts/node-path.sh"
CONSOLE_DIR="${JOBFLOW_CONSOLE_DIR:-$ROOT/console}"
if jobflow_node_path && python3 00-工作流系统/bin/jobflow_environment.py "$CONSOLE_DIR"; then
  (cd "$CONSOLE_DIR" && npm run typecheck --silent -- --incremental false)
elif [ -f "$CONSOLE_DIR/package.json" ]; then
  echo "WARN: Node or console dependencies are missing or incomplete; run 00-工作流系统/scripts/setup.sh with per-item consent; skipping TypeScript check"
else
  echo "WARN: console repo not found at $CONSOLE_DIR; skipping TypeScript check"
fi
python3 00-工作流系统/bin/check_job_reports.py
bash -n 00-工作流系统/scripts/setup.sh
bash -n 00-工作流系统/scripts/node-path.sh
bash -n 00-工作流系统/dashboard/start.sh
bash -n 00-工作流系统/local-control/start.sh
bash -n 打开看板.command
find . -maxdepth 1 -name '*.command' -print0 | xargs -0 -n1 bash -n
if git rev-parse --verify HEAD >/dev/null 2>&1; then
  git diff --check
else
  git diff --cached --check
fi

echo "OK: jobflow full check passed"
