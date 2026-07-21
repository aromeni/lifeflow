#!/usr/bin/env python3
"""Entry point for the Stage 8 Phase 2 scheduled-brief worker (ADR 0004 D48).

No business logic lives here, per this directory's README — it only starts
arq against `lifeflow_api.worker_app.WorkerSettings`, where all of the
dispatch/DST/catch-up/generation logic actually lives (in `apps/api`,
alongside its pytest coverage).

Run from anywhere, using the apps/api environment:

    cd apps/api && uv run python ../../workers/scheduler_worker.py

(equivalently: `cd apps/api && uv run arq lifeflow_api.worker_app.WorkerSettings`
directly, once `apps/api/src` is on `PYTHONPATH` — this script does that for
you so it works regardless of invocation directory.)
"""

import sys
from pathlib import Path

_API_SRC = Path(__file__).resolve().parents[1] / "apps" / "api" / "src"
sys.path.insert(0, str(_API_SRC))

from arq import run_worker  # noqa: E402 - path must be extended first

from lifeflow_api.worker_app import WorkerSettings  # noqa: E402 - path must be extended first

if __name__ == "__main__":
    run_worker(WorkerSettings)
