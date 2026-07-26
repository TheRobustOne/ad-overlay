Twitch Ad Overlay
=================

This is the Windows portable build of the Twitch ad-break OBS overlay backend.
Python is not required.

How to use
----------

1. Extract the ZIP anywhere.
2. Double-click `TwitchAdOverlay.exe`. On first run it will ask for your
   Twitch app's Client ID and Client Secret, then open your browser to sign
   in and grant access (see SETUP.md for how to set up the Twitch app).
3. In OBS Studio, add a `Browser` source from the source `+` menu.
4. Configure the Browser source like this:

URL: http://localhost:8877/ad-overlay.html
Width: 1920
Height: 1080

The overlay background is transparent. Keep the `TwitchAdOverlay.exe` window
running while you stream.

Troubleshooting
----------------

- If port 8877 is already in use, start from Command Prompt with
  `TwitchAdOverlay.exe --port 8878`, then change the OBS URL to
  `http://localhost:8878/ad-overlay.html`.
- The `runtime` folder holds your OAuth credentials and the live overlay
  state. Do not delete it during streaming; it's safe to delete only when
  the app is closed (you'll just need to sign in again).
- Add `&debug=1` to the OBS URL to show a small on-screen status line.
