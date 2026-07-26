from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from .state import StateStore, with_ad_break, with_ad_cleared, with_schedule, with_status
from .twitch import HelixError, TwitchClient

TICK_SEC = 2.0
DEMO_WARN_LEAD_SEC = 10.0
DEMO_AD_DURATION_SEC = 30.0
DEMO_GAP_SEC = 6.0


def poll_once(twitch: TwitchClient, store: StateStore) -> None:
    """One Get-Ad-Schedule cycle. Never raises -- failures are recorded as status, not exceptions."""
    try:
        row = twitch.get_ad_schedule()
        next_ad_at = row.get("next_ad_at") or None
        store.update(lambda s: with_status(with_schedule(s, next_ad_at), "ok", ""))
    except HelixError as exc:
        status = "auth_error" if exc.status in (401, 403) else "schedule_error"
        store.update(lambda s, exc=exc, status=status: with_status(s, status, str(exc)))
    except Exception as exc:  # noqa: BLE001 - never let the poller thread die
        store.update(lambda s, exc=exc: with_status(s, "schedule_error", str(exc)))


def poll_loop(stop_event: threading.Event, twitch: TwitchClient, store: StateStore, interval: float) -> None:
    """Polls Get Ad Schedule on `interval`, and self-clears a finished ad break every tick
    (Twitch's EventSub only sends ad_break.begin, never an "end" event)."""
    last_poll = 0.0
    while not stop_event.is_set():
        now = time.time()
        _clear_expired_ad(store)

        if now - last_poll >= interval:
            last_poll = now
            poll_once(twitch, store)

        stop_event.wait(TICK_SEC)


def _clear_expired_ad(store: StateStore) -> None:
    snap = store.snapshot()
    if not snap.get("adActive"):
        return
    started_at = snap.get("adStartedAt")
    duration = snap.get("adDurationSec")
    if not started_at or duration is None:
        store.update(with_ad_cleared)
        return
    try:
        start_ts = datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        store.update(with_ad_cleared)
        return
    if time.time() >= start_ts + float(duration):
        store.update(with_ad_cleared)


def demo_once(store: StateStore) -> None:
    """A single, synchronous simulated schedule update -- used by --demo --once so the
    smoke test doesn't race a background thread against an immediate stop signal."""
    next_ad_iso = datetime.fromtimestamp(time.time() + DEMO_WARN_LEAD_SEC, tz=timezone.utc).isoformat()
    store.update(lambda s: with_status(with_schedule(s, next_ad_iso), "ok", "DEMO mode (server-simulated schedule)"))


def demo_loop(stop_event: threading.Event, store: StateStore) -> None:
    """Fabricates the same warning -> ad-break -> gap cycle as the HTML's own ?demo=1
    mode, but through the real server -> runtime JSON -> client pipeline."""
    store.update(lambda s: with_status(s, "ok", "DEMO mode (server-simulated schedule)"))
    while not stop_event.is_set():
        next_ad_iso = datetime.fromtimestamp(
            time.time() + DEMO_WARN_LEAD_SEC, tz=timezone.utc
        ).isoformat()
        store.update(lambda s: with_schedule(s, next_ad_iso))
        if stop_event.wait(DEMO_WARN_LEAD_SEC):
            return

        started_at = datetime.now(timezone.utc).isoformat()
        store.update(lambda s: with_ad_break(s, started_at, DEMO_AD_DURATION_SEC))
        if stop_event.wait(DEMO_AD_DURATION_SEC):
            return

        store.update(with_ad_cleared)
        if stop_event.wait(DEMO_GAP_SEC):
            return
