#!/usr/bin/env bash
# Pipeline gratuito Urbanova (fora do OpenHands).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -x .venv/bin/python ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi

CFG="${BUSCAS_CONFIG:-$ROOT/config/buscas_urbanova.json}"
[[ "$CFG" != /* ]] && CFG="$ROOT/$CFG"
if [[ ! -f "$CFG" ]]; then
  echo "Criando $CFG (segmentos padrão)..."
  "$PY" "$ROOT/gerenciar_buscas.py" init --config "$CFG"
fi

exec "$PY" "$ROOT/pipeline_gratuito.py" --buscas-config "$CFG" "$@"
