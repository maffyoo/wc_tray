"""Tournament bracket popup window for WC 2026."""

import json
import os
import html as _html

import objc
from AppKit import NSObject, NSApp

DATA_FILE = os.path.join(os.path.dirname(__file__), "schedule_data.json")

KNOCKOUT_STAGES = ["LAST_32", "LAST_16", "QUARTER_FINALS", "SEMI_FINALS", "FINAL"]
STAGE_LABELS = {
    "LAST_32":        "Round of 32",
    "LAST_16":        "Round of 16",
    "QUARTER_FINALS": "Quarter-Finals",
    "SEMI_FINALS":    "Semi-Finals",
    "FINAL":          "Final",
}

FLAGS = {
    "Germany": "🇩🇪", "Netherlands": "🇳🇱", "Japan": "🇯🇵",
    "Australia": "🇦🇺", "Turkey": "🇹🇷", "Türkiye": "🇹🇷",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Haiti": "🇭🇹", "Curaçao": "🇨🇼", "Curacao": "🇨🇼",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "France": "🇫🇷", "Spain": "🇪🇸",
    "Brazil": "🇧🇷", "Argentina": "🇦🇷", "Portugal": "🇵🇹",
    "Belgium": "🇧🇪", "Croatia": "🇭🇷", "Morocco": "🇲🇦",
    "Senegal": "🇸🇳", "United States": "🇺🇸", "USA": "🇺🇸",
    "Mexico": "🇲🇽", "Canada": "🇨🇦", "Uruguay": "🇺🇾",
    "Colombia": "🇨🇴", "Ecuador": "🇪🇨", "Chile": "🇨🇱",
    "Peru": "🇵🇪", "Paraguay": "🇵🇾", "Venezuela": "🇻🇪",
    "Panama": "🇵🇦", "Honduras": "🇭🇳", "Costa Rica": "🇨🇷", "Bolivia": "🇧🇴",
    "Saudi Arabia": "🇸🇦", "Iran": "🇮🇷", "Korea Republic": "🇰🇷",
    "South Korea": "🇰🇷", "China PR": "🇨🇳", "China": "🇨🇳",
    "Iraq": "🇮🇶", "Jordan": "🇯🇴", "Qatar": "🇶🇦",
    "Uzbekistan": "🇺🇿", "New Zealand": "🇳🇿", "Indonesia": "🇮🇩",
    "Nigeria": "🇳🇬", "Cameroon": "🇨🇲", "Ghana": "🇬🇭",
    "Egypt": "🇪🇬", "Algeria": "🇩🇿", "Tunisia": "🇹🇳",
    "Ivory Coast": "🇨🇮", "South Africa": "🇿🇦", "Angola": "🇦🇴",
    "Tanzania": "🇹🇿", "Zimbabwe": "🇿🇼", "Comoros": "🇰🇲",
    "Sweden": "🇸🇪", "Denmark": "🇩🇰", "Norway": "🇳🇴",
    "Poland": "🇵🇱", "Czech Republic": "🇨🇿", "Czechia": "🇨🇿",
    "Serbia": "🇷🇸", "Austria": "🇦🇹", "Switzerland": "🇨🇭",
    "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "Ireland": "🇮🇪", "Ukraine": "🇺🇦",
    "Romania": "🇷🇴", "Albania": "🇦🇱", "Georgia": "🇬🇪",
    "North Macedonia": "🇲🇰", "Kosovo": "🇽🇰",
    "Cape Verde Islands": "🇨🇻", "Cape Verde": "🇨🇻",
    "Congo DR": "🇨🇩", "Bosnia-H.": "🇧🇦", "Bosnia and Herzegovina": "🇧🇦",
    "DR Congo": "🇨🇩",
}

# ── Layout constants ───────────────────────────────────────────────────────────
MATCH_W    = 180   # match box width  (px)
MATCH_H    = 46    # match box height (px) — two team rows
TEAM_ROW_H = MATCH_H // 2   # 23 px per team row
COL_W      = 244   # width allocated per round column (match + connector gap)
UNIT       = 62    # vertical pitch unit — spacing between adjacent R32 match centres
PAD_X      = 24   # horizontal padding
PAD_Y      = 52    # top padding (space for round header labels)
HEADER_H   = 26    # height reserved for round header text
# ──────────────────────────────────────────────────────────────────────────────

# Horizontal gap between right edge of a match box and the left of the next column.
_COL_GAP = COL_W - MATCH_W   # 64 px — connectors live here


class _BracketWindowController(NSObject):
    """Owns the bracket NSWindow and WKWebView; manages open/close lifecycle."""

    def init(self):
        self = objc.super(_BracketWindowController, self).init()
        if self is None:
            return None
        self._window  = None
        self._webview = None
        return self

    def open(self):
        if self._window is not None:
            self._window.makeKeyAndOrderFront_(None)
            NSApp.activateIgnoringOtherApps_(True)
            return
        self._build()

    def _build(self):
        try:
            from WebKit import WKWebView, WKWebViewConfiguration
        except ImportError:
            import rumps
            rumps.alert("WebKit unavailable — cannot open bracket window.")
            return

        from AppKit import (
            NSWindow, NSBackingStoreBuffered,
            NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
            NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable,
            NSMakeRect,
        )

        bracket = _load_bracket()
        content = _build_html(bracket)

        style = (
            NSWindowStyleMaskTitled |
            NSWindowStyleMaskClosable |
            NSWindowStyleMaskMiniaturizable |
            NSWindowStyleMaskResizable
        )
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 1340, 720),
            style,
            NSBackingStoreBuffered,
            False,
        )
        window.setTitle_("WC 2026 — Tournament Bracket")
        window.setReleasedWhenClosed_(False)
        window.setDelegate_(self)
        window.center()

        cfg     = WKWebViewConfiguration.alloc().init()
        webview = WKWebView.alloc().initWithFrame_configuration_(
            window.contentView().bounds(), cfg
        )
        webview.setAutoresizingMask_(2 | 16)   # NSViewWidthSizable | NSViewHeightSizable
        webview.loadHTMLString_baseURL_(content, None)

        window.contentView().addSubview_(webview)
        window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

        self._window  = window
        self._webview = webview

    def windowWillClose_(self, _notification):
        self._window  = None
        self._webview = None


_controller = None   # module-level strong reference prevents GC


def open_bracket_window():
    """Open (or focus) the tournament bracket window."""
    global _controller
    if _controller is None:
        _controller = _BracketWindowController.alloc().init()
    _controller.open()


# ── Data ───────────────────────────────────────────────────────────────────────

def _load_bracket():
    """Return {stage: [match, ...]} for all knockout stages, sorted by UTC date."""
    try:
        with open(DATA_FILE) as f:
            matches = json.load(f).get("matches", [])
    except Exception:
        matches = []

    bracket = {}
    for stage in KNOCKOUT_STAGES + ["THIRD_PLACE"]:
        ms = [m for m in matches if m.get("stage") == stage]
        ms.sort(key=lambda m: m.get("utcDate", ""))
        bracket[stage] = ms
    return bracket


# ── Layout helpers ─────────────────────────────────────────────────────────────

def _match_cy(round_idx: int, match_idx: int) -> float:
    """Y-centre of a match box at (round_idx, match_idx)."""
    spacing      = UNIT * (2 ** round_idx)
    first_centre = PAD_Y + HEADER_H + spacing / 2
    return first_centre + match_idx * spacing


def _decided(m) -> bool:
    return m.get("status") in ("FINISHED", "AWARDED")


def _winner_side(m):
    """Return 'home', 'away', or None."""
    if not _decided(m):
        return None
    sh = (m.get("score") or {}).get("home")
    sa = (m.get("score") or {}).get("away")
    if sh is None or sa is None:
        return None
    if sh > sa: return "home"
    if sa > sh: return "away"
    return None


def _team_info(m, side):
    """Return (flag, display_name, is_tbd) for the given side."""
    name  = m.get(side) or ""
    short = m.get(f"{side}Short") or ""
    if name in ("", "TBC", "TBD"):
        return ("", "TBD", True)
    flag  = FLAGS.get(name) or FLAGS.get(short, "")
    label = short or name
    return (flag, label, False)


# ── SVG ────────────────────────────────────────────────────────────────────────

def _build_svg(bracket: dict) -> str:
    n_rounds = len(KNOCKOUT_STAGES)
    n_slots  = max(len(bracket.get("LAST_32", [])), 16)

    # Canvas dimensions
    svg_w = PAD_X * 2 + n_rounds * COL_W
    # Height = bottom of last R32 slot + padding
    last_r0_cy = _match_cy(0, n_slots - 1)
    svg_h = int(last_r0_cy + MATCH_H / 2 + 60)

    # 3rd place match sits in the Final column, below the Final match
    final_cy  = _match_cy(4, 0)
    third_cy  = final_cy + MATCH_H + 64   # 64 px gap between Final and 3rd-place boxes
    final_col_x = PAD_X + 4 * COL_W

    parts: list[str] = []

    def e(s):
        return _html.escape(str(s))

    def line(x1, y1, x2, y2, cls="conn"):
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="{cls}"/>'
        )

    def text_el(x, y, txt, cls, anchor="start"):
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}">{e(txt)}</text>'
        )

    def draw_match(col_x: float, cy: float, match: dict):
        mx = col_x
        my = cy - MATCH_H / 2

        sh    = (match.get("score") or {}).get("home")
        sa    = (match.get("score") or {}).get("away")
        win   = _winner_side(match)
        done  = _decided(match)

        # Box + divider
        parts.append(
            f'<rect x="{mx:.1f}" y="{my:.1f}" width="{MATCH_W}" height="{MATCH_H}"'
            f' rx="5" class="mbox"/>'
        )
        line(mx, my + TEAM_ROW_H, mx + MATCH_W, my + TEAM_ROW_H, "mdiv")

        for idx, side in enumerate(("home", "away")):
            flag, name, tbd = _team_info(match, side)
            score = sh if side == "home" else sa

            row_top  = my + idx * TEAM_ROW_H
            label_y  = row_top + TEAM_ROW_H - 7   # baseline inside row

            if tbd:
                name_cls = "tn tbd"
            elif win == side:
                name_cls = "tn winner"
            elif done and win is not None:
                name_cls = "tn loser"
            else:
                name_cls = "tn"

            lbl = f"{flag} {name}" if flag else name
            text_el(mx + 7, label_y, lbl, name_cls)

            if score is not None:
                sc_cls = "sc sw" if win == side else "sc"
                text_el(mx + MATCH_W - 8, label_y, str(score), sc_cls, anchor="end")

        # Date/time label below the box for unplayed matches
        if not done:
            ukdate = match.get("ukDate", "")
            uktime = match.get("ukTime", "")
            if uktime:
                month_day = ukdate[5:] if ukdate else ""
                label = f"{month_day} {uktime}" if month_day else uktime
                text_el(mx + MATCH_W / 2, my + MATCH_H + 13, label, "mdt", anchor="middle")

    def draw_connectors(round_idx: int, src_matches: list, dst_matches: list):
        src_col_x = PAD_X + round_idx * COL_W
        dst_col_x = PAD_X + (round_idx + 1) * COL_W
        src_right = src_col_x + MATCH_W
        mid_x     = src_right + _COL_GAP / 2

        for di in range(len(dst_matches)):
            si1, si2 = di * 2, di * 2 + 1
            if si2 >= len(src_matches):
                continue

            cy1 = _match_cy(round_idx, si1)
            cy2 = _match_cy(round_idx, si2)
            dcy = _match_cy(round_idx + 1, di)

            # Horizontal stubs from each source match to the vertical spine
            line(src_right, cy1, mid_x, cy1)
            line(src_right, cy2, mid_x, cy2)
            # Vertical spine joining the two stubs
            line(mid_x, cy1, mid_x, cy2)
            # Horizontal from spine midpoint to destination match left edge
            line(mid_x, dcy, dst_col_x, dcy)

    # ── Round headers + match boxes ──────────────────────────────────────────
    for ri, stage in enumerate(KNOCKOUT_STAGES):
        col_x = PAD_X + ri * COL_W
        label = STAGE_LABELS[stage]
        text_el(col_x + MATCH_W / 2, PAD_Y - 8, label, "rh", anchor="middle")

        for mi, m in enumerate(bracket.get(stage, [])):
            draw_match(col_x, _match_cy(ri, mi), m)

    # ── Bracket connectors ───────────────────────────────────────────────────
    for ri in range(n_rounds - 1):
        draw_connectors(
            ri,
            bracket.get(KNOCKOUT_STAGES[ri], []),
            bracket.get(KNOCKOUT_STAGES[ri + 1], []),
        )

    # ── 3rd place play-off ───────────────────────────────────────────────────
    third = bracket.get("THIRD_PLACE", [])
    if third and third_cy < svg_h:
        text_el(
            final_col_x + MATCH_W / 2,
            third_cy - MATCH_H / 2 - 10,
            "3rd Place Play-off",
            "tph",
            anchor="middle",
        )
        draw_match(final_col_x, third_cy, third[0])

    body = "\n  ".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' width="{svg_w}" height="{svg_h}"'
        f' viewBox="0 0 {svg_w} {svg_h}">\n  {body}\n</svg>'
    )


# ── CSS ────────────────────────────────────────────────────────────────────────

_CSS = """
:root {
  --bg:      #1c1c1e;
  --surface: #2c2c2e;
  --border:  #3a3a3c;
  --fg:      #f2f2f7;
  --fg-dim:  #aeaeb2;
  --tbd:     #636366;
  --winner:  #30d158;
  --loser:   #636366;
  --conn:    #48484a;
  --accent:  #0a84ff;
  --muted:   #636366;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg:      #f2f2f7;
    --surface: #ffffff;
    --border:  #d1d1d6;
    --fg:      #1c1c1e;
    --fg-dim:  #6c6c70;
    --tbd:     #aeaeb2;
    --winner:  #28a745;
    --loser:   #aeaeb2;
    --conn:    #c6c6c8;
    --accent:  #007aff;
    --muted:   #aeaeb2;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  width: 100%; height: 100%;
  background: var(--bg);
  font-family: -apple-system, "SF Pro Text", BlinkMacSystemFont, sans-serif;
  -webkit-font-smoothing: antialiased;
  overflow: auto;
}
.wrap { padding: 24px; display: inline-block; min-width: 100%; }

/* SVG element classes */
.mbox  { fill: var(--surface); stroke: var(--border); stroke-width: 1; }
.mdiv  { stroke: var(--border); stroke-width: 0.5; }
.conn  { stroke: var(--conn);   stroke-width: 1.5; }

.tn         { fill: var(--fg);     font-size: 11.5px; }
.tn.tbd     { fill: var(--tbd);    font-style: italic; }
.tn.winner  { fill: var(--fg);     font-weight: 700; }
.tn.loser   { fill: var(--loser);  }

.sc         { fill: var(--fg-dim); font-size: 11.5px;
              font-variant-numeric: tabular-nums; }
.sc.sw      { fill: var(--winner); font-weight: 700; }

.rh  { fill: var(--accent); font-size: 10px; font-weight: 600;
       text-transform: uppercase; letter-spacing: .07em; }
.tph { fill: var(--muted);  font-size: 9.5px; font-weight: 500;
       text-transform: uppercase; letter-spacing: .06em; }
.mdt { fill: var(--tbd);    font-size: 9px; }
"""


# ── HTML wrapper ───────────────────────────────────────────────────────────────

def _build_html(bracket: dict) -> str:
    svg = _build_svg(bracket)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="color-scheme" content="dark light">
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
{svg}
</div>
</body>
</html>"""
