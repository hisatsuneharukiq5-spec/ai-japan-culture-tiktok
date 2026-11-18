#!/usr/bin/env bash
# Run a command under a memory ceiling and report its memory use.
#
#   .github/scripts/run_with_memory_cap.sh python main.py obscura-run
#
# Why: on 2026-11-18 an Obscura run starved the GitHub runner of memory and the runner died
# ("The hosted runner lost communication with the server"), taking the whole log with it.
# Inside a transient systemd scope with MemoryMax, an out-of-memory kill hits the command,
# not the runner: the step fails normally, the log survives, and the later steps still run.
#
# Prints the scope's memory every MEM_SAMPLE_SECONDS (default 60) and, at the end, the
# peak (memory.peak) and memory.events (oom_kill count). Exits with the command's status.
# Env: MEMORY_MAX (default 12G), MEM_SAMPLE_SECONDS (default 60).
set -uo pipefail

LIMIT="${MEMORY_MAX:-12G}"
SAMPLE="${MEM_SAMPLE_SECONDS:-60}"

if [ "${_MEMCAP_INSIDE:-}" = "1" ]; then
  # ---- inside the scope: watch memory, run the command, report ----
  cg="/sys/fs/cgroup$(awk -F: '$1 == "0" { print $3 }' /proc/self/cgroup)"
  mib() { awk '{ printf "%.0f MiB", $1 / 1048576 }' "$1" 2>/dev/null || echo "n/a"; }
  echo "[memcap] cgroup ${cg#/sys/fs/cgroup} | MemoryMax=$(cat "$cg/memory.max" 2>/dev/null || echo n/a) bytes"
  start=$(date +%s)
  (
    while sleep "$SAMPLE"; do
      echo "[memcap] +$(( ($(date +%s) - start) / 60 ))min current=$(mib "$cg/memory.current") peak=$(mib "$cg/memory.peak")"
    done
  ) &
  watcher=$!
  "$@"
  rc=$?
  kill "$watcher" 2>/dev/null
  echo "[memcap] exit=$rc elapsed=$(( ($(date +%s) - start) / 60 ))min peak=$(mib "$cg/memory.peak") events: $(tr '\n' ' ' < "$cg/memory.events" 2>/dev/null)"
  exit "$rc"
fi

# ---- outside: start the scope (sudo strips PATH / LD_* so they are passed explicitly) ----
if sudo -n systemd-run --scope --quiet --collect -p MemoryMax=64M --uid="$(id -u)" --gid="$(id -g)" /bin/true 2>/dev/null; then
  echo "[memcap] running under a systemd scope with MemoryMax=$LIMIT (swap disabled for the scope)"
  exec sudo -n --preserve-env systemd-run --scope --quiet --collect \
    -p MemoryMax="$LIMIT" -p MemorySwapMax=0 \
    --uid="$(id -u)" --gid="$(id -g)" \
    /usr/bin/env PATH="$PATH" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" HOME="$HOME" _MEMCAP_INSIDE=1 \
    MEM_SAMPLE_SECONDS="$SAMPLE" bash "$0" "$@"
else
  echo "[memcap] WARNING: systemd-run scope not available here; running WITHOUT a memory cap (still reporting usage)"
  _MEMCAP_INSIDE=1 exec bash "$0" "$@"
fi
