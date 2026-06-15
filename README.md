# WC Tray

A macOS menu bar app showing FIFA World Cup 2026 fixtures with live scores and UK broadcast info (BBC/ITV).

![Menu bar showing live score with flags](https://placeholder)

## What it does

- Shows today's fixtures in the menu with kickoff times, teams, and BBC/ITV channel
- Displays live scores and flags in the menu bar title while matches are in play
- Shows HT indicator at half time
- Navigate to past/future days with ◀ Today ▶ buttons (menu stays open)
- Polls every 60 seconds during live matches, every 5 minutes otherwise
- Refreshes match/broadcaster data automatically each morning at 6am via launchd

## Requirements

- macOS 12+
- Python 3.10+
- A free API key from [football-data.org](https://www.football-data.org/client/register)

## Setup

**1. Clone the repo**
```bash
git clone <repo-url>
cd WC_Tray
```

**2. Get a free API key**

Register at https://www.football-data.org/client/register — it's free, no credit card needed. You'll get an email with your key.

**3. Add your API key**
```bash
cp config.json.example config.json
# Edit config.json and replace YOUR_API_KEY_HERE with your actual key
```

**4. Run setup** (creates virtualenv and installs dependencies)
```bash
./setup.sh
```

**5. Sync match data**
```bash
./sync_now.sh
```

**6. Install the daily 6am sync** (one-time)
```bash
./install_launchd.sh
```

**7. Start the app**
```bash
./start.sh
```

The football icon will appear in your menu bar.

## Daily use

The app auto-starts when you run `./start.sh`. To have it launch at login, add it to **System Settings → General → Login Items**.

The launchd job keeps match data fresh each morning. You can also manually sync anytime:
```bash
./sync_now.sh
```

## Files

| File | Purpose |
|------|---------|
| `wc_tray.py` | Main menu bar app |
| `sync_schedule.py` | Daily sync — fetches from football-data.org + scrapes wheresthematch.com |
| `broadcasts.json` | BBC/ITV broadcast schedule (safe to commit, no secrets) |
| `config.json` | **Your API key — never commit this** (gitignored) |
| `config.json.example` | Safe template for sharing |
| `schedule_data.json` | Generated match data (gitignored) |

## Data sources

- **Match data & live scores** — [football-data.org](https://www.football-data.org) free tier (v4 API)
- **UK broadcasters** — [wheresthematch.com](https://www.wheresthematch.com) (scraped daily) + hardcoded group-stage schedule from official ITV Media / BBC Sport release

## Dependencies

```
rumps          # macOS menu bar wrapper
requests       # HTTP
beautifulsoup4 # HTML scraping
lxml           # HTML parser
```

Install via `./setup.sh` or manually: `pip install -r requirements.txt`
