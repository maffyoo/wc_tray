#!/usr/bin/env python3

import os
import json
import rumps
import requests
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo

import objc
from AppKit import NSView, NSSegmentedControl, NSMenuItem, NSMakeRect

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE  = os.path.join(SCRIPT_DIR, "config.json")
SCHEDULE_FILE = os.path.join(SCRIPT_DIR, "schedule_data.json")

UK_TZ = ZoneInfo("Europe/London")
FD_BASE = "https://api.football-data.org/v4"

TOURNAMENT_START = date(2026, 6, 11)
TOURNAMENT_END   = date(2026, 7, 19)

POLL_LIVE = 60
POLL_IDLE = 300

BROADCASTER_SHORT = {
    "BBC One": "BBC1", "BBC Two": "BBC2", "BBC iPlayer": "iPlayer",
    "ITV1": "ITV1", "ITV2": "ITV2", "ITV4": "ITV4", "ITVX": "ITVX",
}

FLAGS = {
    "Germany": "🇩🇪",  "Netherlands": "🇳🇱",  "Japan": "🇯🇵",
    "Australia": "🇦🇺",  "Turkey": "🇹🇷",  "Türkiye": "🇹🇷",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",  "Haiti": "🇭🇹",  "Curaçao": "🇨🇼",  "Curacao": "🇨🇼",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",  "France": "🇫🇷",  "Spain": "🇪🇸",
    "Brazil": "🇧🇷",  "Argentina": "🇦🇷",  "Portugal": "🇵🇹",
    "Belgium": "🇧🇪",  "Croatia": "🇭🇷",  "Morocco": "🇲🇦",
    "Senegal": "🇸🇳",  "United States": "🇺🇸",  "USA": "🇺🇸",
    "Mexico": "🇲🇽",  "Canada": "🇨🇦",  "Uruguay": "🇺🇾",
    "Colombia": "🇨🇴",  "Ecuador": "🇪🇨",  "Chile": "🇨🇱",
    "Peru": "🇵🇪",  "Paraguay": "🇵🇾",  "Venezuela": "🇻🇪",
    "Panama": "🇵🇦",  "Honduras": "🇭🇳",  "Costa Rica": "🇨🇷",  "Bolivia": "🇧🇴",
    "Saudi Arabia": "🇸🇦",  "Iran": "🇮🇷",  "Korea Republic": "🇰🇷",
    "South Korea": "🇰🇷",  "China PR": "🇨🇳",  "China": "🇨🇳",
    "Iraq": "🇮🇶",  "Jordan": "🇯🇴",  "Qatar": "🇶🇦",
    "Uzbekistan": "🇺🇿",  "New Zealand": "🇳🇿",  "Indonesia": "🇮🇩",
    "Nigeria": "🇳🇬",  "Cameroon": "🇨🇲",  "Ghana": "🇬🇭",
    "Egypt": "🇪🇬",  "Algeria": "🇩🇿",  "Tunisia": "🇹🇳",
    "Ivory Coast": "🇨🇮",  "South Africa": "🇿🇦",  "Angola": "🇦🇴",
    "Tanzania": "🇹🇿",  "Zimbabwe": "🇿🇼",  "Comoros": "🇰🇲",
    "Sweden": "🇸🇪",  "Denmark": "🇩🇰",  "Norway": "🇳🇴",
    "Poland": "🇵🇱",  "Czech Republic": "🇨🇿",  "Czechia": "🇨🇿",
    "Serbia": "🇷🇸",  "Austria": "🇦🇹",  "Switzerland": "🇨🇭",
    "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",  "Ireland": "🇮🇪",  "Ukraine": "🇺🇦",
    "Romania": "🇷🇴",  "Albania": "🇦🇱",  "Georgia": "🇬🇪",
    "North Macedonia": "🇲🇰",  "Kosovo": "🇽🇰",
    "Cape Verde Islands": "🇨🇻",  "Cape Verde": "🇨🇻",
    "Congo DR": "🇨🇩",
}

FINISHED  = {"FINISHED", "AWARDED"}
HALFTIMES = {"PAUSED", "HALFTIME"}          # football-data.org uses PAUSED for HT
LIVE      = {"IN_PLAY"} | HALFTIMES

THIN = " "   # thin space — saves width in the title bar vs a full space


def _flag(name):
    return FLAGS.get(name, "")


def _day_label(d: date, today: date) -> str:
    if d == today:                        return "Today"
    if d == today - timedelta(days=1):    return "Yesterday"
    if d == today + timedelta(days=1):    return "Tomorrow"
    return d.strftime("%-d %b")


# ── Custom NSView nav bar ──────────────────────────────────────────────────
# Uses NSSegmentedControl so clicks keep the menu open (native macOS pattern).

class NavView(NSView):

    def initWithApp_viewing_today_(self, app, viewing, today):
        self = objc.super(NavView, self).initWithFrame_(NSMakeRect(0, 0, 290, 32))
        if self is None:
            return None
        # Store via object dict (not ObjC property) to avoid retain issues
        self.__dict__["_wc_app"] = app

        prev_d = viewing - timedelta(days=1)
        next_d = viewing + timedelta(days=1)
        can_prev = prev_d >= TOURNAMENT_START
        can_next = next_d <= TOURNAMENT_END
        is_today = viewing == today

        seg = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(8, 4, 274, 24))
        seg.setSegmentCount_(3)
        seg.setLabel_forSegment_(f"◀  {_day_label(prev_d, today)}", 0)
        seg.setLabel_forSegment_("Today", 1)
        seg.setLabel_forSegment_(f"{_day_label(next_d, today)}  ▶", 2)
        seg.setEnabled_forSegment_(can_prev, 0)
        seg.setEnabled_forSegment_(not is_today, 1)
        seg.setEnabled_forSegment_(can_next, 2)
        seg.setTrackingMode_(2)   # NSSegmentSwitchTrackingMomentary
        seg.setTarget_(self)
        seg.setAction_(b"segClicked:")
        self.addSubview_(seg)
        return self

    def segClicked_(self, sender):
        app     = self.__dict__["_wc_app"]
        viewing = app._viewing
        today   = datetime.now(UK_TZ).date()
        idx     = sender.selectedSegment()

        if idx == 0:
            candidate = viewing - timedelta(days=1)
            if candidate >= TOURNAMENT_START:
                app._viewing = candidate
        elif idx == 1:
            app._viewing = today
        elif idx == 2:
            candidate = viewing + timedelta(days=1)
            if candidate <= TOURNAMENT_END:
                app._viewing = candidate

        # Rebuild from cache — no network call so it's instant
        app._rebuild_from_cache()


# ── Main app ───────────────────────────────────────────────────────────────

class WorldCupApp(rumps.App):

    def __init__(self):
        super().__init__("⚽", quit_button=None)
        self._viewing     = datetime.now(UK_TZ).date()
        self._all_matches = []
        self._live_cache  = {}   # last fetched live data
        self._timer = rumps.Timer(self._tick, POLL_IDLE)
        self._timer.start()
        self.refresh()

    # ── Data ──────────────────────────────────────────────────────────

    def _load_schedule(self):
        try:
            with open(SCHEDULE_FILE) as f:
                return json.load(f).get("matches", [])
        except Exception:
            return None

    def _fd_headers(self):
        try:
            with open(CONFIG_FILE) as f:
                key = json.load(f).get("football_data_api_key", "")
            return {"X-Auth-Token": key} if key and key != "YOUR_API_KEY_HERE" else None
        except Exception:
            return None

    def _fetch_live(self, ids):
        headers = self._fd_headers()
        if not headers or not ids:
            return {}
        try:
            resp = requests.get(
                f"{FD_BASE}/matches",
                headers=headers,
                params={"ids": ",".join(str(i) for i in ids)},
                timeout=8,
            )
            resp.raise_for_status()
            return {m["id"]: m for m in resp.json().get("matches", [])}
        except Exception:
            return {}

    # ── Refresh paths ─────────────────────────────────────────────────

    def _tick(self, _):
        self.refresh()

    def refresh(self, _ = None):
        """Full refresh: reload schedule + fetch live scores."""
        loaded = self._load_schedule()
        if loaded is not None:
            self._all_matches = loaded

        today = datetime.now(UK_TZ).date()
        viewing_str = self._viewing.isoformat()
        today_str   = today.isoformat()

        day_matches = [m for m in self._all_matches if m.get("ukDate") == viewing_str]

        # Fetch live data for today's non-finished matches
        if self._viewing == today:
            ids = [m["id"] for m in day_matches if m.get("status") not in FINISHED]
            self._live_cache = self._fetch_live(ids)
        else:
            # Also keep title bar current even when browsing another day
            today_ids = [m["id"] for m in self._all_matches
                         if m.get("ukDate") == today_str and m.get("status") not in FINISHED]
            self._live_cache = self._fetch_live(today_ids)

        self._update_title(today_str)
        self._set_poll_rate()
        self._rebuild_menu(day_matches, self._live_cache, today)

    def _rebuild_from_cache(self):
        """Fast rebuild using cached live data — called by nav buttons."""
        today       = datetime.now(UK_TZ).date()
        viewing_str = self._viewing.isoformat()
        day_matches = [m for m in self._all_matches if m.get("ukDate") == viewing_str]
        self._rebuild_menu(day_matches, self._live_cache, today)

    # ── Title bar ─────────────────────────────────────────────────────

    def _update_title(self, today_str):
        live_now = [
            m for m in self._all_matches
            if m.get("ukDate") == today_str
            and (self._live_cache.get(m["id"], {}).get("status") or m.get("status")) in LIVE
        ]
        if not live_now:
            self.title = "⚽"
            return

        parts = []
        for m in live_now:
            ld      = self._live_cache.get(m["id"], {})
            status  = ld.get("status") or m.get("status", "")
            ft      = (ld.get("score") or {}).get("fullTime") or m.get("score") or {}
            hs, aws = ft.get("home"), ft.get("away")

            hf = _flag(m.get("home", ""))
            af = _flag(m.get("away", ""))
            score = f"{hs}–{aws}" if hs is not None else "?–?"
            if status in HALFTIMES:
                score += f"{THIN}HT"

            parts.append(f"{hf}{THIN}{score}{THIN}{af}")

        self.title = f"⚽{THIN}" + f"{THIN}·{THIN}".join(parts)

    def _set_poll_rate(self):
        any_live = any(m.get("status") in LIVE for m in self._live_cache.values())
        target = POLL_LIVE if any_live else POLL_IDLE
        if self._timer.interval != target:
            self._timer.stop()
            self._timer = rumps.Timer(self._tick, target)
            self._timer.start()

    # ── Menu construction ─────────────────────────────────────────────

    def _mi(self, label, cb=None):
        return rumps.MenuItem(label, callback=cb if cb else (lambda _: None))

    def _rebuild_menu(self, day_matches, live_data, today: date):
        viewing = self._viewing

        # Enrich matches with live data
        enriched = []
        for m in day_matches:
            ld     = live_data.get(m["id"], {})
            status = ld.get("status") or m.get("status", "SCHEDULED")
            ft     = (ld.get("score") or {}).get("fullTime") or m.get("score") or {}
            enriched.append({
                **m,
                "status":     status,
                "score":      {"home": ft.get("home"), "away": ft.get("away")},
                "minute":     ld.get("minute"),
                "injuryTime": ld.get("injuryTime"),
            })

        live_ms     = [m for m in enriched if m["status"] in LIVE]
        finished_ms = [m for m in enriched if m["status"] in FINISHED]
        upcoming_ms = [m for m in enriched if m["status"] not in LIVE | FINISHED]

        items = []

        # Match rows
        if not self._all_matches:
            items.append(self._mi("⚠  Run ./sync_now.sh first"))
        elif not day_matches:
            items.append(self._mi("No fixtures on this date"))
        else:
            if live_ms:
                items.append(self._mi("  🔴 LIVE"))
                for m in live_ms:
                    items.append(self._mi(self._fmt(m)))
                items.append(None)

            if finished_ms:
                items.append(self._mi("  ✓ RESULTS"))
                for m in finished_ms:
                    items.append(self._mi(self._fmt(m)))
                if upcoming_ms:
                    items.append(None)

            if upcoming_ms:
                if not finished_ms:
                    items.append(self._mi("  ○ UPCOMING"))
                for m in upcoming_ms:
                    items.append(self._mi(self._fmt(m)))

        # Footer
        items.append(None)
        updated = datetime.now(UK_TZ).strftime("%H:%M")
        items.append(self._mi(f"  Updated {updated}"))
        items.append(self._mi("  Refresh", self.refresh))
        items.append(None)
        items.append(self._mi("  Quit", lambda _: rumps.quit_application()))

        # Rebuild NSMenu
        self.menu.clear()
        for item in items:
            self.menu.add(rumps.separator if item is None else item)

        # Insert nav view at position 0 (after other items are in place)
        nav_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        nav_view = NavView.alloc().initWithApp_viewing_today_(self, viewing, today)
        nav_item.setView_(nav_view)
        self.menu._menu.insertItem_atIndex_(nav_item, 0)

        # Separator after nav
        self.menu._menu.insertItem_atIndex_(NSMenuItem.separatorItem(), 1)

    # ── Match formatting ──────────────────────────────────────────────

    def _fmt(self, m):
        home_full = m.get("home", "?")
        away_full = m.get("away", "?")
        home = m.get("homeShort") or home_full
        away = m.get("awayShort") or away_full

        hf  = _flag(home_full)
        af  = _flag(away_full)

        score  = m.get("score") or {}
        hs     = score.get("home")
        aws    = score.get("away")
        status = (m.get("status") or "SCHEDULED").upper()

        raw_bc = m.get("broadcaster") or ""
        bc = BROADCASTER_SHORT.get(raw_bc, raw_bc)
        bc_str = f"  {bc}" if bc else ""

        if status in FINISHED:
            return f"  {hf} {home}  {hs}–{aws}  {af} {away}{bc_str}"

        if status in LIVE:
            minute = m.get("minute")
            inj    = m.get("injuryTime")
            if status in HALFTIMES:
                clk = "HT"
            elif minute:
                clk = f"{minute}+{inj}'" if inj else f"{minute}'"
            else:
                clk = "●"
            s = f"{hs}–{aws}" if hs is not None else "·–·"
            return f"  ● {clk}  {hf} {home}  {s}  {af} {away}{bc_str}"

        # Upcoming
        t = m.get("ukTime", "--:--")
        return f"  {t}  {hf} {home}  ·–·  {af} {away}{bc_str}"


if __name__ == "__main__":
    WorldCupApp().run()
