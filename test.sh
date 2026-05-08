#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "No virtual environment found. Run ./bootstrap.sh first."
  exit 1
fi

if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

usage() {
  cat <<EOF
Usage: $0 [MODE] [pytest-args...]

Modes:
  (none)        Unit tests only (default)
  --integration Run unit + SQLite file + Ollama integration tests
  --azure       Run unit + SQLite file + Ollama + Azure contract tests
  --all         Same as --azure
  --help        Show this message

Any extra arguments are forwarded to pytest.
EOF
}

MODE="unit"
EXTRA_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --integration) MODE="integration" ;;
    --azure|--all)  MODE="azure" ;;
    --help)        usage; exit 0 ;;
    *)             EXTRA_ARGS+=("$arg") ;;
  esac
done

case "$MODE" in
  unit)
    echo "Running unit tests..."
    PYTHONPATH=. .venv/bin/pytest -m "not integration" "${EXTRA_ARGS[@]}"
    ;;
  integration)
    echo "Running unit + integration tests (Ollama required, Azure skipped)..."
    PYTHONPATH=. .venv/bin/pytest -m "not azure" "${EXTRA_ARGS[@]}"
    ;;
  azure)
    echo "Running full test suite including Azure contract tests..."
    PYTHONPATH=. .venv/bin/pytest "${EXTRA_ARGS[@]}"
    ;;
esac
