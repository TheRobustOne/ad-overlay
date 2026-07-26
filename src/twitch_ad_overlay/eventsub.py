from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Optional

import websocket

from .state import StateStore, with_ad_break, with_status
from .twitch import TwitchClient

EVENTSUB_WS = "wss://eventsub.wss.twitch.tv/ws"
RECONNECT_DELAY_SEC = 2.0


class EventSubClient:
    """Background WebSocket connection subscribed to channel.ad_break.begin.

    Drives the ads-playing panel: this is the low-latency, authoritative signal for
    "an ad just started", unlike the ad-schedule poll which only knows what's upcoming.
    """

    def __init__(self, twitch: TwitchClient, store: StateStore):
        self._twitch = twitch
        self._store = store
        self._stop = threading.Event()
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._ws is not None:
            self._ws.close()

    def _run_forever(self) -> None:
        url = EVENTSUB_WS
        while not self._stop.is_set():
            try:
                url = self._connect_once(url)
            except Exception as exc:
                self._store.update(lambda s: with_status(s, "eventsub_error", str(exc)))
                url = EVENTSUB_WS
            if self._stop.is_set():
                return
            self._stop.wait(RECONNECT_DELAY_SEC)

    def _connect_once(self, url: str) -> str:
        next_url = {"value": EVENTSUB_WS}

        def on_message(ws, message):
            msg = json.loads(message)
            msg_type = msg.get("metadata", {}).get("message_type")

            if msg_type == "session_welcome":
                session_id = msg["payload"]["session"]["id"]
                try:
                    self._twitch.create_eventsub_subscription(session_id)
                    self._store.update(lambda s: with_status(s, "ok", "EventSub connected"))
                except Exception as exc:
                    self._store.update(lambda s: with_status(s, "eventsub_error", f"subscribe failed: {exc}"))
            elif msg_type == "session_reconnect":
                next_url["value"] = msg["payload"]["session"]["reconnect_url"]
                ws.close()
            elif msg_type == "notification":
                if msg["metadata"].get("subscription_type") == "channel.ad_break.begin":
                    event = msg["payload"]["event"]
                    duration = float(event.get("duration_seconds", event.get("duration", 90)))
                    started_at = datetime.now(timezone.utc).isoformat()
                    self._store.update(lambda s: with_ad_break(s, started_at, duration))

        def on_error(ws, error):
            self._store.update(lambda s: with_status(s, "eventsub_error", str(error)))

        def on_close(ws, close_status_code, close_msg):
            return

        self._ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error, on_close=on_close)
        self._ws.run_forever()
        return next_url["value"]
