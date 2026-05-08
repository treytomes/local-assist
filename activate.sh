#!/bin/bash
# Must be sourced, not executed: source activate.sh
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "ERROR: source this script, don't run it: source activate.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "No virtual environment found. Run ./bootstrap.sh first."
  return 1
fi

source "$VENV_DIR/bin/activate"

# Load .env into the shell environment
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  source "$SCRIPT_DIR/.env"
  set +a
fi

echo "Activated local-assist environment (python: $(which python3))"
