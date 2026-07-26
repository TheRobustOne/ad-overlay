from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .output import write_state


def default_state(status: str = "starting", message: str = "") -> Dict[str, Any]:
    return {
        "nextAdAt": None,
        "adActive": False,
        "adStartedAt": None,
        "adDurationSec": None,
        "status": status,
        "statusMessage": message,
        "updatedAt": time.time(),
    }


def with_schedule(state: Dict[str, Any], next_ad_at: Optional[str]) -> Dict[str, Any]:
    updated = dict(state)
    updated["nextAdAt"] = next_ad_at
    updated["updatedAt"] = time.time()
    return updated


def with_ad_break(state: Dict[str, Any], started_at: str, duration_sec: float) -> Dict[str, Any]:
    updated = dict(state)
    updated["adActive"] = True
    updated["adStartedAt"] = started_at
    updated["adDurationSec"] = duration_sec
    updated["nextAdAt"] = None
    updated["updatedAt"] = time.time()
    return updated


def with_ad_cleared(state: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(state)
    updated["adActive"] = False
    updated["adStartedAt"] = None
    updated["adDurationSec"] = None
    updated["updatedAt"] = time.time()
    return updated


def with_status(state: Dict[str, Any], status: str, message: str = "") -> Dict[str, Any]:
    updated = dict(state)
    updated["status"] = status
    updated["statusMessage"] = message
    updated["updatedAt"] = time.time()
    return updated


class StateStore:
    """Thread-safe holder for the shared AdState, persisted to runtime/adstate.json on every update."""

    def __init__(self, runtime_dir: Path):
        self._runtime_dir = runtime_dir
        self._lock = threading.Lock()
        self._state = default_state()
        self._persist()

    def update(self, fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        with self._lock:
            self._state = fn(self._state)
            self._persist()
            return self._state

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def _persist(self) -> None:
        try:
            write_state(self._state, self._runtime_dir)
        except OSError:
            pass
