# mlb-totals-agent
MLB Totals Analyzer — pybaseball edition
A Streamlit app that pulls live Statcast, FanGraphs, and Baseball Reference data via
pybaseball to support pre-game total-runs (Over/Under) analysis.
This app is a parallel analytical view — it is intentionally separate from the Pre-Bet
Checklist so you can compare both views before integrating them. Run them side-by-side;
do not let one dominate the other until you’ve validated agreement over a meaningful
sample.
What it does
For a given game, the app pulls:
Starting pitcher quality (xERA, SIERA, K%, BB%) → FanGraphs leaderboard
Recent pitcher form (L21d Statcast: velocity trend, whiff trend) → Baseball Savant
Park factor + marine layer flag → static table (update each season)
Team offense (wRC+, wOBA, BABIP regression flags) → FanGraphs team batting
It then maps those into Tier 1 / Tier 2 run adjustments aligned with the Pre-Bet Checklist’s
weights, sums them against a league-average baseline (~8.6 R/G), and reports:
Expected total
Edge vs. the posted line
Verdict (Over lean / Under lean / No play if |edge| < 0.30)
Per-factor signal breakdown with narrative + heatmap
Project structure
mlb-totals-pybaseball/
├── app.py # Streamlit app — single-file by design
├── requirements.txt # pinned-floor dependencies
└── README.md # this file
Local setup
Requires Python 3.10+.
git clone https://github.com/<your-username>/mlb-totals-pybaseball.git
cd mlb-totals-pybaseball
python -m venv .venv
source .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
The app will open at http://localhost:8501.
First run will be slow (30–90 seconds) as pybaseball warms its local cache. Subsequent
runs hit the cache and are near-instant.
Deploying to Streamlit Community Cloud
1. Push this repo to GitHub (public or private — Streamlit Cloud supports both with a free
account).
2. Sign in to share.streamlit.io with your GitHub account.
3. Click New app → select this repo, branch main , main file path app.py.
4. Click Deploy. First build takes ~3–5 minutes (Streamlit Cloud installs pybaseball and
its dependencies).
5. Once live, your app will be at https://<your-app-name>.streamlit.app.
Streamlit Cloud notes
Memory limit: Free tier gives 1 GB RAM. The app stays well under this for single-game
analysis. Avoid pulling full-season Statcast in one call ( statcast(start_dt, end_dt)
over a wide range will OOM).
Cold starts: Apps idle after ~10 minutes of no traffic. First request after idle takes 30–
60s to respawn.
Cache: @st.cache_data decorators are tuned per endpoint (15 min for player lookups, 1
hour for season leaderboards). This keeps reruns fast without serving stale data.
No secrets needed. All data sources used are public — no API keys, no Pinnacle
credentials, no sportsbook integration.
How to use it
1. Sidebar — Game Setup:
Pick season (defaults to current year)
Pick away and home teams (3-letter abbreviations)
Type each starting pitcher’s first and last name (case-insensitive)
Enter the posted O/U total
Toggle “Night game” (matters for marine-layer parks)
2. Click “Run analysis.” Watch the progress bar — it runs four data pulls in sequence.
3. Read the output:
Top metrics: posted total, expected total, edge, verdict
Signal breakdown table with adjustments and narratives
Horizontal bar chart showing each factor’s run impact
Pitcher-detail expanders for season stats and L21d Statcast pitch arsenal
4. Compare against your Pre-Bet Checklist. If both views agree on Over/Under and
direction, your conviction is justified. If they disagree, dig into the disagreement — that’s
where most learning happens.
Updating park factors
The PARK_FACTORS dict in app.py is hand-maintained from Baseball Savant’s Statcast Park
Factors leaderboard. Update at season start using the 3-year rolling view (single-season
factors are too noisy).
The marine_layer_flag is set to True only for parks where research has shown
statistically significant fly-ball suppression (Petco, Oracle, T-Mobile) or directional effect
(Angel Stadium). Reference: Marine Layer effect on fly balls (Chico State Physics).
What this app does NOT do
By design, this is a lean, auditable view — not a kitchen-sink model. The following are
intentionally left to the Pre-Bet Checklist:
Bullpen analysis (usage logs, fatigue, rest days) — InsideThePen + FanGraphs reliever
logs
Weather (wind vector, temp, humidity, precip) — weather.gov + BallparkPal
Umpire (zone size, run-suppression history) — UmpScorecards + UmpScores
Lineup confirmation + bat tracking (Statcast bat speed leaderboard, swing decisions)
Market microstructure (RLM, steam, sharp vs. public splits) — Action Network +
DonBest
CLV tracking (no-vig Pinnacle close vs. bet number) — manual logging required
If a factor matters but isn’t here, it’s a checklist responsibility. Add it deliberately, with
weights, after both views have validated each other.
Caveats
Edge < 0.30 runs is model noise. A “0.4-run edge” is a modest signal, not a green
light. Cross-reference the checklist before sizing any bet.
pybaseball scrapes public sources. Endpoints occasionally change (especially after
MLB.com redesigns). If a function fails, check the pybaseball GitHub issues or pin to a
known-good version.
Player name lookups can be ambiguous. The app picks the most recently active
player matching a last/first name. If you have two active pitchers with the same name,
edit the lookup logic to disambiguate by team.
CLV is the only honest scoreboard. Track no-vig Pinnacle close vs. your bet number
across 200+ wagers. Short-term P&L is variance.
Data sources
Source Purpose Access
Baseball Savant
(Statcast)
Pitch-level data, expected
stats, park factors
Free; via
pybaseball.statcast_pitcher,
statcast
FanGraphs xERA, SIERA, wRC+, wOBA,
BABIP, leaderboards
Free; via
pybaseball.pitching_stats,
team_batting
Baseball
Reference Schedule, game results Free; via
pybaseball.schedule_and_record
weather.gov Coastal marine layer forecast Free; manual cross-reference (not
yet integrated)
License
MIT. Use at your own risk. Not affiliated with MLB, Anthropic, or any sportsbook.
Roadmap (optional future additions)
These would be considered only after the parallel view has proven its value vs. the checklist:
Pull schedule + auto-resolve starting pitchers from MLB Stats API
Integrate hourly weather forecast + wind vector for outdoor parks
Add bat tracking metrics (Savant 2023+ leaderboard) for each lineup
Add umpire zone factor lookup (UmpScorecards)
Track historical predictions vs. actual results in a local SQLite log
Add Monte Carlo simulation for total-runs distribution (not just point estimate)