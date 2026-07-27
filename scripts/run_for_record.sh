#!/usr/bin/env bash
# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Launch the run-for-record batch, fully detached, with a timestamped log and a
# recorded PID so it survives this shell/session and can be monitored or resumed.
# The batch itself is resumable: re-running this (or `sara batch`) re-scans the
# output dir and only runs replicates still missing, so a reboot / LM Studio
# blip / Ctrl-C does not lose finished cells.
#
# Usage:  scripts/run_for_record.sh [experiments.yaml]
set -euo pipefail
cd "$(dirname "$0")/.."

CONFIG="${1:-experiments.yaml}"
LOG="runs/batch.log"
PIDFILE="runs/batch.pid"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "batch already running (pid $(cat "$PIDFILE")); tail -f $LOG to watch" >&2
  exit 1
fi

mkdir -p runs
# setsid + nohup fully detaches from the controlling terminal; stdout/stderr to
# the log. Rich renders plainly to a non-tty.
setsid nohup .venv/bin/sara batch --config "$CONFIG" >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"
echo "launched: pid $(cat "$PIDFILE")  config=$CONFIG  log=$LOG"
