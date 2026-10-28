#!/usr/bin/env bash
# Quick launcher for Bot or Not with automatic Cloudflare Quick Tunnel
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

# Activate virtual environment if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

python3 run_with_tunnel.py "$@"

