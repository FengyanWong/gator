#!/usr/bin/env bash
# The browser checks in parallel lanes (run_checks.mjs, run by Windows node) behind two scratch backends that this script
# starts and stops: A for the hermetic checks, B with its own output root for the two checks that start real MOCK runs.
# Never the user's backend on 8765; both settings folders are empty temporary ones. From the repository root:
#   bash frontend/scripts/run_checks.sh [--lanes 4] [--only a,b] [--skip a,b] [--retry-failed] [--out <Windows dir>]
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python="${GATOR_PYTHON:-$HOME/analog-optimizer-venv/bin/python}"
node="${GATOR_WINDOWS_NODE:-/mnt/c/Program Files/nodejs/node.exe}"
tmp="$(mktemp -d /tmp/gator-checks.XXXXXX)"
mkdir -p "$tmp/settings-a" "$tmp/settings-b" "$tmp/out-b"
pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; wait 2>/dev/null || true; rm -rf "$tmp"; }
trap cleanup EXIT
free_port() { "$python" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'; }
serve() {   # <settings folder> <port> <log> [serve options...]
  local settings="$1" port="$2" log="$3"; shift 3
  # The workbench has no MOCK task since 2026-09-30 (record 7.128): the checks' backends register the tests' stand-in.
  (cd "$repo" && GATOR_WORKBENCH_SETTINGS_DIR="$settings" \
    GATOR_WORKBENCH_SYNTHETIC_FIXTURES="$repo/tests/workbench/fixtures/synthetic_fixtures.json" PYTHONPATH=src \
    exec "$python" -m gator_workbench.cli serve --port "$port" "$@" > "$log" 2>&1) &
  pids+=($!)
}
port_a="$(free_port)"; port_b="$(free_port)"
extra_a=(); flags=()                                    # checks that need a fixture their author made (see PORTED)
if [ -d /tmp/gator-reward-v21-browser ]; then extra_a+=(--allow-root /tmp/gator-reward-v21-browser); flags+=(--reward-fixture); fi
llm="$repo/artifacts/local/llm-sizing/browser-fixture"
if [ -d "$llm" ]; then extra_a+=(--allow-root "$llm"); flags+=(--llm-fixture); fi
serve "$tmp/settings-a" "$port_a" "$tmp/backend-a.log" "${extra_a[@]}"
serve "$tmp/settings-b" "$port_b" "$tmp/backend-b.log" --allow-root "$tmp/out-b"
for port in "$port_a" "$port_b"; do
  for _ in $(seq 1 120); do curl -sf "http://127.0.0.1:$port/api/meta" > /dev/null && break; sleep 0.5; done
  if ! curl -sf "http://127.0.0.1:$port/api/meta" > /dev/null; then
    echo "ERROR the scratch backend on port $port did not start:"; tail -5 "$tmp"/backend-*.log; exit 2
  fi
done
"$node" "$(wslpath -w "$repo/frontend/scripts/run_checks.mjs")" --hermetic-api "http://127.0.0.1:$port_a" \
  --writer-api "http://127.0.0.1:$port_b" --scratch-out "$tmp/out-b" "${flags[@]}" "$@"
