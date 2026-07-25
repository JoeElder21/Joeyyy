#!/usr/bin/env bash
# Install richawo/minimal-llm-ui — a minimal Next.js chat interface for local
# Ollama models. Clones (or updates) the app alongside this repository and
# installs its npm dependencies. Verified working with Node 20 / npm 10.
#
# Usage:
#   scripts/install_minimal_llm_ui.sh [target-dir]
#
# Then run it:
#   ollama serve                # Ollama at http://localhost:11434
#   cd <target-dir> && npm run dev   # UI at http://localhost:3000

set -euo pipefail

REPO_URL="https://github.com/richawo/minimal-llm-ui.git"
TARGET_DIR="${1:-$(cd "$(dirname "$0")/../.." && pwd)/minimal-llm-ui}"

if [ -d "$TARGET_DIR/.git" ]; then
  echo "Updating existing clone at $TARGET_DIR"
  git -C "$TARGET_DIR" pull --ff-only
else
  echo "Cloning $REPO_URL to $TARGET_DIR"
  git clone "$REPO_URL" "$TARGET_DIR"
fi

cd "$TARGET_DIR"
npm install --no-audit --no-fund

echo
echo "minimal-llm-ui installed at $TARGET_DIR"
echo "Start Ollama (ollama serve), then: cd $TARGET_DIR && npm run dev"
