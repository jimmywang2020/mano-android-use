"""Minimal .env loader (no third-party python-dotenv dependency)."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path | str | None = None, *, override: bool = False) -> Path | None:
    """Load KEY=VALUE lines into os.environ. Returns path loaded or None."""
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    else:
        cwd = Path.cwd() / ".env"
        here = Path(__file__).resolve().parents[2] / ".env"
        candidates.extend([cwd, here])
    for env_path in candidates:
        if not env_path.is_file():
            continue
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if not key:
                continue
            if override or key not in os.environ or os.environ.get(key, "") == "":
                os.environ[key] = value
        return env_path
    return None
