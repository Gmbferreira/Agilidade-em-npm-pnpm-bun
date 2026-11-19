#!/usr/bin/env bash
# Controla o Verdaccio local.
#   scripts/registry.sh start popular   # com uplink (preparação)
#   scripts/registry.sh start coleta    # sem uplink (medição)
#   scripts/registry.sh stop | status
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="$ROOT/env/verdaccio"
PIDFILE="$DIR/verdaccio.pid"
LOGFILE="$DIR/verdaccio.log"
URL="http://127.0.0.1:4873"

running() { [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

mode_of() { [[ -f "$DIR/verdaccio.mode" ]] && cat "$DIR/verdaccio.mode" || echo "?"; }

case "${1:-}" in
  start)
    mode="${2:-}"
    [[ "$mode" == popular || "$mode" == coleta ]] || { echo "uso: $0 start popular|coleta" >&2; exit 2; }
    if running; then echo "Verdaccio já está rodando (modo $(mode_of)). Use stop antes." >&2; exit 1; fi
    mkdir -p "$DIR/storage"
    cd "$ROOT"
    nohup mise exec -- verdaccio --config "$DIR/config.$mode.yaml" >"$LOGFILE" 2>&1 &
    echo $! >"$PIDFILE"
    echo "$mode" >"$DIR/verdaccio.mode"
    for _ in $(seq 1 50); do
      curl -fs "$URL/-/ping" >/dev/null 2>&1 && { echo "Verdaccio no ar em $URL (modo $mode)"; exit 0; }
      sleep 0.2
    done
    echo "Verdaccio não respondeu; veja $LOGFILE" >&2; exit 1
    ;;
  stop)
    if running; then
      pid="$(cat "$PIDFILE")"
      pkill -P "$pid" 2>/dev/null || true
      kill "$pid" 2>/dev/null || true
      echo "Verdaccio parado."
    else
      echo "Verdaccio não estava rodando."
    fi
    rm -f "$PIDFILE" "$DIR/verdaccio.mode"
    ;;
  status)
    if running && curl -fs "$URL/-/ping" >/dev/null 2>&1; then
      echo "rodando (modo $(mode_of)) em $URL"
    else
      echo "parado"; exit 1
    fi
    ;;
  *)
    echo "uso: $0 start popular|coleta | stop | status" >&2; exit 2 ;;
esac
