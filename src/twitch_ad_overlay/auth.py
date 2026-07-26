from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

from .output import atomic_write_text

AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
SCOPE = "channel:read:ads"
TOKEN_REFRESH_MARGIN_SEC = 300


class AuthError(Exception):
    pass


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


class Credentials:
    def __init__(self, runtime_dir: Path):
        self.path = runtime_dir / "credentials.json"
        data = _read_json(self.path)
        self.client_id: str = data.get("client_id", "")
        self.client_secret: str = data.get("client_secret", "")
        self.refresh_token: str = data.get("refresh_token", "")

    def save(self) -> None:
        atomic_write_text(
            self.path,
            json.dumps(
                {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                },
                indent=2,
            ),
        )

    @property
    def is_app_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def has_refresh_token(self) -> bool:
        return bool(self.refresh_token)


def prompt_for_app_credentials(creds: Credentials, port: int) -> None:
    print()
    print("Twitch app credentials needed.")
    print("  1. Go to https://dev.twitch.tv/console/apps and open your app (or register one).")
    print(f"  2. Add this OAuth Redirect URL: http://localhost:{port}/callback")
    print("  3. Copy the Client ID, and click 'New Secret' to get a Client Secret.")
    print()
    creds.client_id = input("Client ID: ").strip()
    creds.client_secret = input("Client Secret: ").strip()
    creds.save()


class _CallbackResult:
    def __init__(self):
        self.code: Optional[str] = None
        self.error: Optional[str] = None
        self.event = threading.Event()


def _make_callback_handler(result: _CallbackResult):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(parsed.query)
            result.code = qs.get("code", [None])[0]
            result.error = qs.get("error_description", qs.get("error", [None]))[0]
            body = b"<html><body>Twitch sign-in complete. You can close this tab.</body></html>"
            if result.error:
                body = f"<html><body>Twitch sign-in failed: {result.error}</body></html>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
            result.event.set()

        def log_message(self, format, *args):  # noqa: A002 - matches BaseHTTPRequestHandler signature
            return

    return Handler


def run_authorization_flow(creds: Credentials, port: int, bind: str = "127.0.0.1", timeout: float = 300.0) -> None:
    """One-shot local server that captures Twitch's OAuth redirect, then exchanges the code."""
    if not creds.is_app_configured:
        raise AuthError("Client ID/Secret must be configured before running the authorization flow.")

    redirect_uri = f"http://localhost:{port}/callback"
    authorize_url = AUTHORIZE_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": creds.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
        }
    )

    result = _CallbackResult()
    server = HTTPServer((bind, port), _make_callback_handler(result))
    threading.Thread(target=server.handle_request, daemon=True).start()

    print()
    print("Opening your browser to authorize with Twitch...")
    print(f"If it doesn't open automatically, visit:\n  {authorize_url}")
    webbrowser.open(authorize_url)

    try:
        if not result.event.wait(timeout):
            raise AuthError("Timed out waiting for Twitch authorization.")
    finally:
        server.server_close()

    if result.error or not result.code:
        raise AuthError(f"Twitch authorization failed: {result.error or 'no code returned'}")

    _exchange_code(creds, result.code, redirect_uri)


def _post_token_request(body: dict) -> dict:
    encoded = urllib.parse.urlencode(body).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=encoded, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AuthError(f"Twitch token endpoint error: {e.code} {e.read().decode('utf-8', 'replace')}") from e


def _exchange_code(creds: Credentials, code: str, redirect_uri: str) -> None:
    data = _post_token_request(
        {
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
    )
    creds.refresh_token = data["refresh_token"]
    creds.save()


class TokenManager:
    """Owns the current access token; refreshes proactively in the background and on demand."""

    def __init__(self, creds: Credentials):
        self._creds = creds
        self._state_lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._access_token = ""
        self._expires_at = 0.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self.refresh(force=True)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def get_token(self) -> str:
        if time.time() >= self._expires_at:
            self.refresh()
        with self._state_lock:
            return self._access_token

    def refresh(self, force: bool = False) -> None:
        with self._refresh_lock:
            if not force and time.time() < self._expires_at:
                return
            data = _post_token_request(
                {
                    "client_id": self._creds.client_id,
                    "client_secret": self._creds.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self._creds.refresh_token,
                }
            )
            with self._state_lock:
                self._access_token = data["access_token"]
                self._expires_at = time.time() + float(data.get("expires_in", 14400)) - TOKEN_REFRESH_MARGIN_SEC
            new_refresh = data.get("refresh_token")
            if new_refresh:
                self._creds.refresh_token = new_refresh
                self._creds.save()

    def _loop(self) -> None:
        while not self._stop.is_set():
            wait_for = max(30.0, self._expires_at - time.time())
            if self._stop.wait(wait_for):
                return
            try:
                self.refresh(force=True)
            except AuthError:
                self._stop.wait(30.0)
