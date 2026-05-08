#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r requirements.txt

echo "Done. Run 'source activate.sh' to activate."
