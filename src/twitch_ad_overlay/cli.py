from __future__ import annotations

import argparse
import sys
import sysconfig
import threading
from pathlib import Path
from typing import Optional

from .auth import Credentials, TokenManager, prompt_for_app_credentials, run_authorization_flow
from .eventsub import EventSubClient
from .output import ensure_runtime_dir
from .poller import demo_loop, demo_once, poll_loop, poll_once
from .server import serve
from .state import StateStore, with_status
from .twitch import TwitchClient


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def frozen_bundle_dir() -> Optional[Path]:
    if not is_frozen_app():
        return None

    candidates = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass))
    candidates.append(Path(sys.executable).resolve().parent)

    for candidate in candidates:
        if (candidate / "ad-overlay.html").exists():
            return candidate
    return None


def executable_dir() -> Path:
    if is_frozen_app():
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def find_app_dir() -> Path:
    bundle_dir = frozen_bundle_dir()
    if bundle_dir is not None:
        return bundle_dir

    repo_dir = Path(__file__).resolve().parents[2]
    if (repo_dir / "ad-overlay.html").exists():
        return repo_dir
    cwd = Path.cwd()
    if (cwd / "ad-overlay.html").exists():
        return cwd
    data_dir = Path(sysconfig.get_path("data")) / "share" / "twitch-ad-overlay"
    if (data_dir / "ad-overlay.html").exists():
        return data_dir
    return repo_dir


def find_runtime_dir(app_dir: Path) -> Path:
    if is_frozen_app():
        return executable_dir() / "runtime"
    if app_dir == Path.cwd() or app_dir == Path(__file__).resolve().parents[2]:
        return app_dir / "runtime"
    return executable_dir() / "runtime"


APP_DIR = find_app_dir()
RUNTIME_DIR = find_runtime_dir(APP_DIR)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Twitch ad-break overlay backend for OBS.")
    parser.add_argument("--port", type=int, default=8877, help="HTTP server port. Default: 8877")
    parser.add_argument("--bind", default="127.0.0.1", help="HTTP server bind address. Default: 127.0.0.1")
    parser.add_argument(
        "--poll-interval", type=float, default=30.0, help="Ad-schedule poll interval in seconds. Default: 30"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Simulate the schedule/ad-break cycle; no Twitch credentials needed."
    )
    parser.add_argument("--once", action="store_true", help="Do a single poll cycle, write adstate.json, and exit.")
    parser.add_argument(
        "--reauth",
        action="store_true",
        help="Re-run the browser authorization flow, even if a refresh token already exists.",
    )
    return parser.parse_args()


def _ensure_authorized(creds: Credentials, port: int, force: bool) -> None:
    if not creds.is_app_configured:
        prompt_for_app_credentials(creds, port)
    if force or not creds.has_refresh_token:
        run_authorization_flow(creds, port)


def _run_demo(args: argparse.Namespace, store: StateStore) -> int:
    if args.once:
        demo_once(store)
        print(RUNTIME_DIR / "adstate.json")
        return 0

    stop_event = threading.Event()
    threading.Thread(target=demo_loop, args=(stop_event, store), daemon=True).start()

    try:
        serve(args.port, args.bind, APP_DIR, RUNTIME_DIR)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
    return 0


def _run_live(args: argparse.Namespace, store: StateStore) -> int:
    creds = Credentials(RUNTIME_DIR)
    try:
        _ensure_authorized(creds, args.port, force=args.reauth)
    except Exception as exc:
        print(f"Authorization failed: {exc}", file=sys.stderr)
        return 1

    token_mgr = TokenManager(creds)
    token_mgr.start()

    twitch = TwitchClient(creds.client_id, token_mgr.get_token)
    try:
        twitch.resolve_broadcaster_id()
    except Exception as exc:
        store.update(lambda s: with_status(s, "auth_error", str(exc)))
        print(f"Could not resolve broadcaster id: {exc}", file=sys.stderr)
        return 1

    if args.once:
        poll_once(twitch, store)
        print(RUNTIME_DIR / "adstate.json")
        return 0

    stop_event = threading.Event()
    threading.Thread(
        target=poll_loop, args=(stop_event, twitch, store, args.poll_interval), daemon=True
    ).start()

    eventsub = EventSubClient(twitch, store)
    eventsub.start()

    try:
        serve(args.port, args.bind, APP_DIR, RUNTIME_DIR)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        eventsub.stop()
        token_mgr.stop()
    return 0


def main() -> int:
    args = parse_args()
    ensure_runtime_dir(RUNTIME_DIR)
    store = StateStore(RUNTIME_DIR)

    if args.demo:
        return _run_demo(args, store)
    return _run_live(args, store)


if __name__ == "__main__":
    sys.exit(main())
