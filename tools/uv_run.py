"""Run ``uv run <args>`` in this repository's own environment.

Some machines set ``UV_PROJECT_ENVIRONMENT`` globally for another project; uv would then sync
this project's dependencies into that foreign environment. Git hooks and scripts call this
wrapper instead of ``uv run`` so the variable is always cleared first.

Usage: ``python tools/uv_run.py pyright``
"""

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def project_env(environ: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of ``environ`` without ``UV_PROJECT_ENVIRONMENT``."""
    return {k: v for k, v in environ.items() if k != "UV_PROJECT_ENVIRONMENT"}


def main(argv: list[str]) -> int:
    """Run ``uv run`` with the cleaned environment and return its exit code."""
    cmd = ["uv", "run", "--project", str(REPO_ROOT), *argv]
    return subprocess.call(cmd, env=project_env(os.environ))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
