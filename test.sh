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

PYTHONPATH=. .venv/bin/pytest "$@"
