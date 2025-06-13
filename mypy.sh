#!/usr/bin/env bash
set -euo pipefail

# change to script directory
cd $(dirname "$0")

# make sure virtual env is active
if [ -z "${VIRTUAL_ENV:-}" ]; then
    source venv/bin/activate
fi

echo "Type checking libres..."
mypy -p libres

echo "Type checking tests..."
mypy -p tests
