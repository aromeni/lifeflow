#!/usr/bin/env bash
# Run the golden-dataset evaluations.
# Usage: ./scripts/run-evals.sh [det|det+mock|det+anthropic|brief|brief+mock]
set -euo pipefail
cd "$(dirname "$0")/../apps/api"
MODE="${1:-det}"
PYTHONPATH=src uv run python ../../evals/run_evals.py --mode "$MODE"
