#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "No virtual environment found. Run ./bootstrap.sh first."
  exit 1
fi

echo "Updating dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r requirements.txt
"$VENV_DIR/bin/pip" install --quiet -r proxy/requirements.txt

echo "Done."
