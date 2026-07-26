from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


HELIX = "https://api.twitch.tv/helix"


class HelixError(Exception):
    def __init__(self, status: int, path: str, body: str):
        super().__init__(f"{path} -> {status} {body}")
        self.status = status


class TwitchClient:
    """Thin Helix client. `token_provider` is called before every request so callers
    always get the current access token without this class knowing about refresh."""

    def __init__(self, client_id: str, token_provider):
        self.client_id = client_id
        self._token_provider = token_provider
        self.broadcaster_id: Optional[str] = None

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = HELIX + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Client-Id", self.client_id)
        req.add_header("Authorization", "Bearer " + self._token_provider())
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                raw = res.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise HelixError(e.code, path, e.read().decode("utf-8", "replace")) from e

    def resolve_broadcaster_id(self) -> str:
        data = self._request("GET", "/users")
        rows = data.get("data") or []
        if not rows:
            raise HelixError(0, "/users", "no user returned for token")
        self.broadcaster_id = rows[0]["id"]
        return self.broadcaster_id

    def get_ad_schedule(self) -> Dict[str, Any]:
        data = self._request("GET", "/channels/ads?broadcaster_id=" + self.broadcaster_id)
        rows = data.get("data") or []
        return rows[0] if rows else {}

    def create_eventsub_subscription(self, session_id: str) -> None:
        self._request(
            "POST",
            "/eventsub/subscriptions",
            {
                "type": "channel.ad_break.begin",
                "version": "1",
                "condition": {"broadcaster_user_id": self.broadcaster_id},
                "transport": {"method": "websocket", "session_id": session_id},
            },
        )
