# Twitch Ad Overlay — Setup

A local backend service + OBS browser source with two independent pieces:

- **10-second warning pill** — fires before an ad break, driven by Twitch's *Get Ad Schedule* (`next_ad_at`).
- **Ads-playing panel** — a live countdown while the break runs, driven by the EventSub `channel.ad_break.begin` event.

The backend (`twitch-ad-overlay`) owns your Twitch OAuth token and refreshes it automatically, forever — no more copy-pasting a token into a URL every few hours. `ad-overlay.html` never sees your credentials at all; it just polls `localhost` for the current state.

---

## 1. Preview it right now (no login, no backend)

Open `ad-overlay.html` directly in a browser with demo mode:

```
ad-overlay.html?demo=1
```

It loops: warning counts down → ad panel runs 30s → short gap → repeat. Add `&color=ff5c5c&pos=tr` to test styling. This mode is entirely client-side and never talks to the backend.

---

## 2. Install the backend

```
pip install -e .
```

This installs the `twitch-ad-overlay` console command (needs Python 3.9+). A portable Windows `.exe` build is also available — see [Packaging](#10-packaging-a-standalone-exe) below if you don't want a Python environment.

---

## 3. Set up your Twitch app for OAuth

Ad-schedule and EventSub access needs a real **refresh token**, which requires the Authorization Code grant — i.e. your Twitch app needs a **Client Secret**, not just a Client ID.

1. Go to <https://dev.twitch.tv/console/apps> and open your existing app (or **Register Your Application** if you don't have one — Category: *Broadcasting Suite*).
2. Under **OAuth Redirect URLs**, add: `http://localhost:8877/callback` (use whatever `--port` you plan to run with, if not the default 8877).
3. Copy the **Client ID**, and click **New Secret** to generate a **Client Secret**.

You don't need a separate app if you already have one from before — just add the secret and the redirect URL.

---

## 4. First run — one-time browser sign-in

```
twitch-ad-overlay
```

- If it's the first run, it'll prompt for your **Client ID** and **Client Secret** in the terminal.
- It then opens your browser to Twitch's sign-in/consent screen (scope `channel:read:ads`). Approve it as your broadcaster account.
- Twitch redirects back to `http://localhost:8877/callback`, the CLI captures it, exchanges it for a refresh token, and stores everything in `runtime/credentials.json`.
- From then on, `twitch-ad-overlay` just works — it refreshes the access token in the background indefinitely. Re-running it never asks again unless you pass `--reauth`.

Your numeric broadcaster ID is auto-resolved from the token.

Once it's running, it prints the URL to use in OBS:
```
OBS Browser Source URL: http://localhost:8877/ad-overlay.html
```

---

## 5. Add the browser source in OBS

**Sources → + → Browser**, and set the URL to:

```
http://localhost:8877/ad-overlay.html?color=19d3c5&pos=br
```

No `client_id`/`token` in the URL anymore — nothing sensitive is exposed to the OBS scene config. Set width/height to your canvas (e.g. 1920×1080); the overlay is transparent and anchors itself to the corner you choose.

`twitch-ad-overlay` needs to be running in the background whenever you stream (start it before OBS, or set it to run at login).

---

## 6. URL parameters (`ad-overlay.html`)

| Param | Purpose | Default |
|---|---|---|
| `color` | Accent color, hex without `#` (e.g. `19d3c5`) | teal `19d3c5` |
| `pos` | `br` `bl` `tr` `tl` `tc` | `br` (bottom-right) |
| `warn` | Warning lead time in seconds | `10` |
| `demo` | `1` = client-only looping preview, no backend needed | off |
| `debug` | `1` = show a small status line (reflects the backend's status) | off |

## 7. CLI flags (`twitch-ad-overlay`)

| Flag | Purpose | Default |
|---|---|---|
| `--port` | HTTP server / OAuth redirect port | `8877` |
| `--bind` | HTTP server bind address | `127.0.0.1` |
| `--poll-interval` | Ad-schedule poll interval, seconds | `30` |
| `--demo` | Simulate the schedule/ad-break cycle server-side — no credentials needed, useful for testing the full server→file→client pipeline | off |
| `--once` | Do a single poll cycle, write `runtime/adstate.json`, and exit (smoke test) | off |
| `--reauth` | Force the browser sign-in flow again, even if a refresh token already exists | off |

---

## 8. Testing without waiting for a real ad

Right-click the browser source → **Interact**, open the console, and call:

```js
AdOverlay.startWarning(10);   // show the 10s warning
AdOverlay.startAds(90);       // show a 90s ad panel
AdOverlay.stopAds();          // hide it
```

Or run `twitch-ad-overlay --demo` to loop the whole cycle through the real backend instead.

---

## 9. Notes

- `runtime/credentials.json` holds your Client Secret and refresh token — it's gitignored and never leaves your machine, but treat it like a password (don't share the `runtime/` folder).
- `runtime/adstate.json` is regenerated constantly and is safe to delete; it's recreated on the next poll.
- The warning relies on Twitch actually having a scheduled `next_ad_at`. Manually-triggered ads may skip the pre-warning but still trigger the ads-playing panel via EventSub.
- If the panels stop updating, check the terminal running `twitch-ad-overlay` for errors, or add `&debug=1` to the OBS URL to see the current status on-screen.

---

## 10. Packaging a standalone `.exe`

If you'd rather not maintain a Python environment, `scripts/build-windows.ps1` builds a portable one-folder Windows executable via PyInstaller:

```
scripts/build-windows.ps1
```

This produces `dist/TwitchAdOverlay-<version>-windows-<arch>.zip` — unzip it anywhere and run `TwitchAdOverlay.exe` exactly like the `twitch-ad-overlay` command above (same flags, same first-run OAuth flow, same `runtime/` folder alongside the executable).
