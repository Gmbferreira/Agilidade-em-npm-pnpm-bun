#!/usr/bin/env bash
# Limpa o cache/store global de um gerenciador (cenário S1 Frio e S2 CI, docs/02 §2.3)
# e confere que ficou vazio.
#   scripts/clean-cache.sh npm|pnpm|bun|all
# Não apaga node_modules nem lockfiles: isso é parte da preparação de cada projeto (#4).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"   # garante as versões fixadas no mise.toml

size() { if [[ -e "$1" ]]; then du -sh "$1" 2>/dev/null | cut -f1; else echo "ausente"; fi; }

# Falha se o diretório existir e tiver qualquer arquivo
assert_empty() {
  local d="$1"
  if [[ -e "$d" ]] && [[ -n "$(find "$d" -type f -print -quit 2>/dev/null)" ]]; then
    echo "  ERRO: $d ainda contém arquivos" >&2; return 1
  fi
  echo "  ok: $d vazio/ausente"
}

clean_npm() {
  local cache; cache="$(mise exec -- npm config get cache)"
  echo "npm  — cache em $cache ($(size "$cache/_cacache"))"
  mise exec -- npm cache clean --force >/dev/null 2>&1
  assert_empty "$cache/_cacache"
}

clean_pnpm() {
  local store meta
  store="$(mise exec -- pnpm store path)"
  meta="${XDG_CACHE_HOME:-$HOME/.cache}/pnpm"
  echo "pnpm — store em $store ($(size "$store")); metadados em $meta ($(size "$meta"))"
  # `pnpm store prune` só remove pacotes não referenciados; para o cache frio
  # o store e o cache de metadados são removidos por inteiro.
  rm -rf "$store" "$meta"
  assert_empty "$store"; assert_empty "$meta"
}

clean_bun() {
  local cache; cache="$(mise exec -- bun pm cache 2>/dev/null)"
  echo "bun  — cache em $cache ($(size "$cache"))"
  mise exec -- bun pm cache rm >/dev/null 2>&1 || true
  assert_empty "$cache"
}

case "${1:-}" in
  npm)  clean_npm ;;
  pnpm) clean_pnpm ;;
  bun)  clean_bun ;;
  all)  clean_npm; clean_pnpm; clean_bun ;;
  *) echo "uso: $0 npm|pnpm|bun|all" >&2; exit 2 ;;
esac
