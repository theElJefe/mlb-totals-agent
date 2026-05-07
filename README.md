# mlb-totals-agent
# ⚾ MLB Totals Bet Tracker — Streamlit App

A mobile-friendly Streamlit app that pulls every MLB game within the next **72 hours**
and provides a full pre-bet checklist, run adjuster, quarter-Kelly sizer, and bet log —
all based on the MLB Totals Pre-Bet Evaluation Checklist (2026 Edition).

---

## Features

| Tab | What it does |
|-----|-------------|
| 📋 Games (72h) | Lists all upcoming games with probable pitchers; edit/save bet card data per game |
| ✅ Pre-Bet Checklist | T1/T2/T3 checklist, run adjuster (16 factors), quarter-Kelly sizer, copyable bet card template |
| 📓 Bet Log | All saved bets with market, price, stake, CLV, notes |

---

## Setup

```bash
# 1. Clone or copy files into your repo
# 2. Install dependencies
pip install -r requirements.txt

# 3. Run locally
streamlit run app.py
```

### On your phone (Streamlit Cloud)
1. Push `app.py` and `requirements.txt` to your GitHub repo.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app** → select your repo.
3. Set **Main file path** to `app.py`.
4. Deploy — share the URL and open it on your phone browser.

---

## Data Sources Used (Free)

- **MLB Stats API** via `MLB-StatsAPI` Python wrapper — schedule, probable pitchers, game status
- All analysis inputs (FanGraphs, Baseball Savant, UmpScorecards) are external links you check manually
- Bet data is stored locally in `bet_log.json` (persists between sessions)

---

## Bet Card Output Format

```
Date: 2026-05-07
Game: TEX @ NYY 12:35 PM ET
Market: F5 Under 4.5
Stake: $81.25 (quarter-Kelly)
Price: -115
No-vig fair: 4.3
Pinnacle close: TBD (log post-game)
CLV: TBD
Base line: 8.5 | Adj: -0.57 → Fair 7.9
Signal: UNDER
Active factors: Wind -, Marine, Ump +, BatSpd-
Notes: Bullpen-day trigger via late SP scratch. Gore elite peripherals on TEX side.
T1 pass: YES
T2 complete: 86%
```

---

## Checklist Coverage

| Tier | Items | Purpose |
|------|-------|---------|
| T1 — Deal-Breakers | 15 | Game confirmation, SP health, weather blowouts |
| T2 — Run Adjusters | 21 | xERA, velo, bullpen, lineup, park, ump, bat tracking, marine layer |
| T3 — Market Signals | 9 | Sharp money, line movement, CLV setup, regression flags |

Run Adjustment Factors (16 available):
Wind +/-, Temp +/-, Marine layer, Ump large/small zone, Park HR factor,
Bullpen fresh/depleted, F5 divergence, Short-series familiarity,
Bat speed decline, Lineup protection collapse, Sharp steam Over/Under

---

## Notes

- `bet_log.json` is created automatically on first save.
- Schedule refreshes every 15 minutes (`@st.cache_data(ttl=900)`).
- Click **🔄 Refresh Schedule** to force a live pull.
- Quarter-Kelly formula: `max(0, full_kelly / 4) × bankroll`
