#!/bin/bash
# Source with ROOT set to the repository root. This changes only this process PATH.
jobflow_node_path() {
  local node_bin
  node_bin="$(python3 "$ROOT/00-工作流系统/bin/jobflow_environment.py" --node-bin)" || return 1
  export PATH="$node_bin:$PATH"
}
