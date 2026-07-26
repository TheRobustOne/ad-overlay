"use strict";
/* =========================================================================
   Twitch Ad Overlay  —  single-file OBS browser source
   -------------------------------------------------------------------------
   Two independent pieces:
     1) Pre-roll WARNING pill  — driven by Get Ad Schedule (next_ad_at)
     2) Ad-break PLAYING panel — driven by EventSub channel.ad_break.begin
   Both are normally driven by the local twitch-ad-overlay backend service
   (see SETUP.md), which owns the Twitch OAuth token, polls the ad schedule,
   and listens to EventSub — this page just polls its local runtime JSON.
   A demo mode runs the whole thing client-side with no backend at all, so
   you can preview the look.

   URL parameters
   --------------
     ?color=00ffcc       Accent color (hex, no #)
     ?pos=br|bl|tr|tl|tc Placement (default br = bottom-right)
     ?warn=10            Pre-roll warning lead time in seconds (default 10)
     ?demo=1             Demo/preview mode (loops warning -> ads, no backend)
     ?debug=1            Show a small status line
   ========================================================================= */

const qs = new URLSearchParams(location.search);
const CFG = {
  color:         qs.get("color") || "",
  pos:           qs.get("pos") || "br",
  warnLead:      Math.max(3, parseInt(qs.get("warn") || "10", 10)),
  demo:          qs.get("demo") === "1",
  debug:         qs.get("debug") === "1",
};

const LOCAL_POLL_MS = 1000;    // local runtime-state poll interval

// ---- elements ----
const $warn = document.getElementById("warn");
const $warnNum = document.getElementById("warnNum");
const $ads = document.getElementById("ads");
const $adsTime = document.getElementById("adsTime");
const $adsBar = document.getElementById("adsBar");
const $adsSub = document.getElementById("adsSub");
const $anchor = document.getElementById("anchor");
const $status = document.getElementById("status");

// ---- theming ----
(function applyTheme() {
  if (CFG.color) {
    const hex = CFG.color.replace(/^#/, "");
    const c = "#" + hex;
    document.documentElement.style.setProperty("--accent", c);
    const r = parseInt(hex.substr(0,2),16), g = parseInt(hex.substr(2,2),16), b = parseInt(hex.substr(4,2),16);
    if (!isNaN(r) && !isNaN(g) && !isNaN(b)) {
      document.documentElement.style.setProperty("--accent-soft", `rgba(${r},${g},${b},0.18)`);
    }
  }
  $anchor.className = "anchor " + (["br","bl","tr","tl","tc"].includes(CFG.pos) ? CFG.pos : "br");
})();

function setStatus(msg) {
  if (!CFG.debug) return;
  $status.textContent = msg;
  $status.classList.add("show");
}
function fmt(sec) {
  sec = Math.max(0, Math.round(sec));
  const m = Math.floor(sec / 60), s = sec % 60;
  return m + ":" + String(s).padStart(2, "0");
}

/* ---------------- Pre-roll WARNING controller ---------------- */
let warnTimer = null, warnShownFor = null;
function startWarning(secondsUntilAd) {
  const key = Math.round(Date.now() / 1000 + secondsUntilAd);
  if (warnShownFor === key) return;   // already counting down to this ad
  warnShownFor = key;
  clearInterval(warnTimer);
  let remaining = Math.round(secondsUntilAd);
  $warn.classList.add("show");
  const tick = () => {
    if (remaining <= 0) { hideWarning(); return; }
    $warnNum.textContent = remaining;
    remaining--;
  };
  tick();
  warnTimer = setInterval(tick, 1000);
}
function hideWarning() {
  clearInterval(warnTimer); warnTimer = null;
  $warn.classList.remove("show");
}

/* ---------------- Ads-playing controller ---------------- */
let adsTimer = null;
function startAds(durationSec, startedAtIso) {
  clearInterval(adsTimer);
  hideWarning();                       // warning done, ad is live
  const total = Math.max(1, Math.round(durationSec || 90));
  // Driven off an absolute start time (not a decrementing counter) so a page
  // reload mid-break — or a poll tick arriving late — still shows the right
  // remaining time instead of restarting the countdown from the full duration.
  const startMs = startedAtIso ? new Date(startedAtIso).getTime() : Date.now();
  $ads.classList.add("show");
  const tick = () => {
    const elapsed = (Date.now() - startMs) / 1000;
    const remaining = Math.max(0, total - elapsed);
    $adsTime.textContent = fmt(remaining);
    $adsBar.style.width = ((remaining / total) * 100) + "%";
    $adsSub.textContent = remaining > 3 ? "Back shortly" : "Back now!";
    if (remaining <= 0) { stopAds(); return; }
  };
  tick();
  adsTimer = setInterval(tick, 1000);
}
function stopAds() {
  clearInterval(adsTimer); adsTimer = null;
  $ads.classList.remove("show");
}

/* ============================ LIVE MODE ============================ */
// The twitch-ad-overlay backend service (SETUP.md) owns the Twitch OAuth
// token, polls the ad schedule, and listens to EventSub — all this page does
// is poll its local runtime state and drive the same two controllers above.
let localAdActive = false;

async function pollLocalState() {
  try {
    const res = await fetch("/runtime/adstate.json?ts=" + Date.now(), { cache: "no-store" });
    if (!res.ok) { setStatus("Local service error: " + res.status); return; }
    const s = await res.json();

    if (s.adActive) {
      localAdActive = true;
      startAds(s.adDurationSec, s.adStartedAt);
    } else if (localAdActive) {
      localAdActive = false;
      stopAds();
    } else if (s.nextAdAt) {
      const until = (new Date(s.nextAdAt).getTime() - Date.now()) / 1000;
      if (until <= CFG.warnLead && until > 0) startWarning(until);
      else if (until <= 0) hideWarning();
    } else {
      hideWarning();
    }

    setStatus(s.statusMessage || s.status || "");
  } catch (e) {
    setStatus("Local service unreachable — is twitch-ad-overlay running?");
  }
}

function runLive() {
  pollLocalState();
  setInterval(pollLocalState, LOCAL_POLL_MS);
}

/* ============================ DEMO MODE ============================ */
function runDemo() {
  setStatus("DEMO mode — looping preview");
  const loop = () => {
    // 10s warning
    startWarning(CFG.warnLead);
    // ad break begins right after the countdown
    setTimeout(() => startAds(30), (CFG.warnLead + 0.3) * 1000);
    // then a quiet gap before the next cycle
    setTimeout(loop, (CFG.warnLead + 30 + 6) * 1000);
  };
  loop();
}

/* ---------------- boot ---------------- */
if (CFG.demo) runDemo(); else runLive();

// expose manual hooks for testing from the console / OBS interact
window.AdOverlay = { startWarning, hideWarning, startAds, stopAds };
