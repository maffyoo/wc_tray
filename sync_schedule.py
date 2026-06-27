#!/usr/bin/env python3
"""
Daily sync:
  - Fetches all WC 2026 fixtures + scores from football-data.org
  - Scrapes wheresthematch.com for UK broadcast assignments on upcoming matches
  - Preserves previously-discovered broadcast data across runs
Run once manually, then launchd keeps it updated daily at 06:00.
"""

import os
import sys
import json
import re
import unicodedata
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
SCHEDULE_FILE = os.path.join(SCRIPT_DIR, "schedule_data.json")
MANUAL_BROADCASTS_FILE = os.path.join(SCRIPT_DIR, "broadcasts.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "sync.log")

UK_TZ = ZoneInfo("Europe/London")
FD_BASE = "https://api.football-data.org/v4"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

CHANNEL_PATTERNS = [
    (re.compile(r"BBC\s+One", re.I), "BBC One"),
    (re.compile(r"BBC\s+Two", re.I), "BBC Two"),
    (re.compile(r"BBC\s+iPlayer", re.I), "BBC iPlayer"),
    (re.compile(r"ITV\s*X", re.I), "ITVX"),
    (re.compile(r"ITV\s*4", re.I), "ITV4"),
    (re.compile(r"ITV\s*2", re.I), "ITV2"),
    (re.compile(r"\bITV\s*1?\b", re.I), "ITV1"),
]

FINISHED = {"FINISHED", "AWARDED", "CANCELLED", "POSTPONED", "SUSPENDED"}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception as e:
        log(f"Could not load config.json: {e}")
        return {}


def load_manual_broadcasts():
    try:
        with open(MANUAL_BROADCASTS_FILE) as f:
            data = json.load(f)
        data.pop("_note", None)
        return data
    except Exception:
        return {}


def load_existing_schedule():
    try:
        with open(SCHEDULE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"matches": []}


def detect_channel(text):
    for pattern, name in CHANNEL_PATTERNS:
        if pattern.search(text):
            return name
    return None


def _strip_accents(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _fuzzy_team_match(text, match_name):
    """Return True if both team names from match_name appear in text.
    Handles 'v' vs 'vs', accents, and common name variants."""
    # Normalise both sides
    text_norm = _strip_accents(text.lower())
    parts = [_strip_accents(p.strip().lower()) for p in match_name.split(" vs ")]
    if len(parts) != 2:
        return False
    # Allow short names to match (min 4 chars to avoid false positives)
    return all(len(p) >= 3 and p in text_norm for p in parts)


# ---------------------------------------------------------------------------
# football-data.org — all fixtures + scores
# ---------------------------------------------------------------------------

def fetch_fd_matches(api_key):
    log("Fetching all WC matches from football-data.org...")
    resp = requests.get(
        f"{FD_BASE}/competitions/WC/matches",
        headers={**HEADERS, "X-Auth-Token": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    matches = resp.json().get("matches", [])
    log(f"  Got {len(matches)} matches")
    return matches


# ---------------------------------------------------------------------------
# wheresthematch.com — upcoming UK broadcast assignments
# ---------------------------------------------------------------------------

WTM_URL = "https://www.wheresthematch.com/live-world-cup-football-on-tv/"

# Channels to skip (not free-to-air UK national)
SKIP_CHANNELS = {"STV", "STV Player", "S4C"}

# Priority order: prefer linear TV over streaming
CHANNEL_PRIORITY = ["BBC One", "BBC Two", "ITV1", "ITV4", "ITV2", "BBC iPlayer", "ITVX"]


def _best_channel(channels):
    """Pick the most prominent free-to-air UK channel from a list."""
    for preferred in CHANNEL_PRIORITY:
        if preferred in channels:
            return preferred
    return channels[0] if channels else None


def _channel_from_alt(alt_text):
    """Convert image alt text like 'ITV1 logo' to canonical channel name."""
    name = re.sub(r"\s*logo\s*$", "", alt_text, flags=re.I).strip()
    if name in SKIP_CHANNELS:
        return None
    # Normalise
    for pattern, canonical in CHANNEL_PATTERNS:
        if pattern.fullmatch(name):
            return canonical
    return detect_channel(name)


def scrape_wheresthematch(existing_by_name):
    """
    Scrape wheresthematch.com World Cup page.
    Uses <tr itemtype="BroadcastEvent"> rows, extracting:
      - match name from <meta itemprop="name">
      - kickoff from <meta itemprop="startDate">
      - channels from <td class="channel-details"> img alt texts
    Only assigns broadcasters to non-finished matches.
    Returns:
      broadcaster_data: {date_str: {match_name: broadcaster}}
      teams_by_slot:    {(date_str, time_str): (home, away)} for resolving TBD fixtures
    """
    log(f"Scraping {WTM_URL} ...")
    results = {}
    teams_by_slot = {}
    upcoming = {k: v for k, v in existing_by_name.items() if v["status"] not in FINISHED}

    try:
        resp = requests.get(WTM_URL, timeout=20, headers=HEADERS)
        resp.raise_for_status()
    except Exception as e:
        log(f"  fetch failed: {e}")
        return results, teams_by_slot

    soup = BeautifulSoup(resp.text, "lxml")

    rows = soup.find_all("tr", attrs={"itemtype": re.compile(r"BroadcastEvent", re.I)})
    log(f"  Found {len(rows)} BroadcastEvent rows")

    for row in rows:
        # Match name
        name_meta = row.find("meta", attrs={"itemprop": "name"})
        wtm_name = name_meta["content"] if name_meta else ""
        if not wtm_name:
            continue

        # Kickoff UTC
        date_meta = row.find("meta", attrs={"itemprop": "startDate"})
        if not date_meta:
            date_meta = row.find("td", attrs={"itemprop": "startDate"})
        start_raw = (date_meta.get("content") or date_meta.get("datetime", "")) if date_meta else ""

        try:
            utc_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            uk_dt = utc_dt.astimezone(UK_TZ)
            date_str = uk_dt.strftime("%Y-%m-%d")
            # WTM labels UK (BST) times as UTC, so the raw "UTC" hour matches
            # entry["ukTime"] directly — don't apply another +1h conversion.
            time_str = utc_dt.strftime("%H:%M")
        except (ValueError, AttributeError):
            date_str = None
            time_str = None

        # Always capture team names by slot — WTM uses "A v B", we store (A, B).
        # This lets us resolve TBD fixtures even when the football-data API lags.
        parts = [p.strip() for p in wtm_name.split(" v ", 1)]
        if len(parts) == 2 and all(parts) and date_str and time_str:
            teams_by_slot.setdefault((date_str, time_str), (parts[0], parts[1]))

        # Channels from img alt attributes in channel-details td
        channel_td = row.find("td", class_="channel-details")
        channels = []
        if channel_td:
            for img in channel_td.find_all("img"):
                alt = img.get("alt") or img.get("title") or ""
                ch = _channel_from_alt(alt)
                if ch:
                    channels.append(ch)

        if not channels:
            continue

        best = _best_channel(channels)
        if not best:
            continue

        # Match by team name; fall back to kickoff slot for TBD fixtures
        for key, entry in upcoming.items():
            if date_str and entry["ukDate"] != date_str:
                continue
            if _fuzzy_team_match(wtm_name, key) or (
                time_str and entry["ukTime"] == time_str and entry["home"] == "TBD"
            ):
                results.setdefault(entry["ukDate"], {})[key] = best
                break

    count = sum(len(v) for v in results.values())
    log(f"  Found {count} broadcast assignments")
    return results, teams_by_slot


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log("=== WC Tray sync starting ===")

    config = load_config()
    api_key = config.get("football_data_api_key", "")

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        log("ERROR: No football-data.org API key in config.json")
        log("       Register free at https://www.football-data.org/client/register")
        sys.exit(1)

    try:
        fd_matches = fetch_fd_matches(api_key)
    except Exception as e:
        log(f"ERROR fetching fixtures: {e}")
        sys.exit(1)

    # Build match list
    matches_out = []
    existing_by_name = {}

    for m in fd_matches:
        utc_dt = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
        uk_dt = utc_dt.astimezone(UK_TZ)
        date_str = uk_dt.strftime("%Y-%m-%d")
        time_str = uk_dt.strftime("%H:%M")

        home = m.get("homeTeam", {}).get("name") or "TBD"
        away = m.get("awayTeam", {}).get("name") or "TBD"
        home_short = m.get("homeTeam", {}).get("shortName") or home
        away_short = m.get("awayTeam", {}).get("shortName") or away
        match_name = f"{home} vs {away}"

        score = m.get("score", {})
        ft = score.get("fullTime", {"home": None, "away": None}) or {}
        status = m.get("status", "SCHEDULED")

        entry = {
            "id": m["id"],
            "utcDate": m["utcDate"],
            "ukDate": date_str,
            "ukTime": time_str,
            "status": status,
            "stage": m.get("stage", ""),
            "group": m.get("group", ""),
            "home": home,
            "homeShort": home_short,
            "away": away,
            "awayShort": away_short,
            "matchName": match_name,
            "broadcaster": None,
            "score": {"home": ft.get("home"), "away": ft.get("away")},
        }
        matches_out.append(entry)
        existing_by_name[match_name] = entry

    # Broadcaster lookup — only for non-finished matches
    wtm_data, wtm_by_slot = scrape_wheresthematch(existing_by_name)
    manual = load_manual_broadcasts()
    def real_channel(val):
        """Return val only if it's a real channel name, not a placeholder."""
        return val if (val and val.upper() not in ("TBC", "TBD", "")) else None

    prior = {
        m["matchName"]: real_channel(m.get("broadcaster"))
        for m in load_existing_schedule().get("matches", [])
    }

    assigned = 0
    for entry in matches_out:
        if entry["status"] in FINISHED:
            entry["broadcaster"] = None
            continue

        name = entry["matchName"]
        date = entry["ukDate"]

        broadcaster = (
            real_channel(manual.get(date, {}).get(name))
            or real_channel(wtm_data.get(date, {}).get(name))
            or prior.get(name)
        )
        entry["broadcaster"] = broadcaster
        if broadcaster:
            assigned += 1

    # Resolve TBD team names from WTM slot data — runs after broadcaster assignment
    # so the "TBD vs TBD" key still works for the wtm_data lookup above.
    resolved = 0
    for entry in matches_out:
        if entry["home"] != "TBD" and entry["away"] != "TBD":
            continue
        slot = (entry["ukDate"], entry["ukTime"])
        if slot in wtm_by_slot:
            h, a = wtm_by_slot[slot]
            entry["home"] = entry["homeShort"] = h
            entry["away"] = entry["awayShort"] = a
            entry["matchName"] = f"{h} vs {a}"
            resolved += 1
    if resolved:
        log(f"  Resolved {resolved} TBD team name(s) from wheresthematch.com")

    schedule = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_matches": len(matches_out),
        "matches": matches_out,
    }

    with open(SCHEDULE_FILE, "w") as f:
        json.dump(schedule, f, indent=2, ensure_ascii=False)

    log(f"Saved {len(matches_out)} matches ({assigned} upcoming with broadcaster)")
    log("=== Sync complete ===")


if __name__ == "__main__":
    main()
