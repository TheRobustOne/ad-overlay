from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict


def ensure_runtime_dir(runtime_dir: Path) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)


def replace_with_retry(tmp_path: Path, dest_path: Path, attempts: int = 5, initial_delay: float = 0.05) -> None:
    delay = initial_delay
    for attempt in range(attempts):
        try:
            tmp_path.replace(dest_path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2


def atomic_write_text(path: Path, text: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    replace_with_retry(tmp_path, path)


def write_state(state: Dict[str, Any], runtime_dir: Path) -> None:
    json_path = runtime_dir / "adstate.json"
    atomic_write_text(json_path, json.dumps(state, ensure_ascii=False))
