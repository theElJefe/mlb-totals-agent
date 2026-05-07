import streamlit as st
import statsapi
import requests
from datetime import datetime, timedelta, timezone
import pytz
import json
import os

st.set_page_config(
    page_title="MLB Totals Bet Tracker",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Mobile-friendly CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Tighter padding on mobile */
  .block-container { padding: 0.75rem 0.75rem 2rem; }
  /* Card styling */
  .bet-card {
    background: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 10px;
    padding: 14px;
    margin-bottom: 12px;
  }
  .bet-card h4 { margin: 0 0 6px; font-size: 1.05rem; color: #cdd6f4; }
  .field-label { color: #a6adc8; font-size: 0.78rem; text-transform: uppercase; letter-spacing: .04em; }
  .field-value { color: #cdd6f4; font-size: 0.92rem; margin-bottom: 8px; }
  .tag-over  { background:#a6e3a1; color:#1e1e2e; border-radius:4px; padding:2px 6px; font-size:.75rem; font-weight:700; }
  .tag-under { background:#f38ba8; color:#1e1e2e; border-radius:4px; padding:2px 6px; font-size:.75rem; font-weight:700; }
  .tag-pass  { background:#585b70; color:#cdd6f4; border-radius:4px; padding:2px 6px; font-size:.75rem; font-weight:700; }
  .tier-pass { color:#f38ba8; font-weight:700; }
  .tier-ok   { color:#a6e3a1; font-weight:700; }
  .tier-warn { color:#fab387; font-weight:700; }
  /* Checklist row */
  .chk-row { display:flex; justify-content:space-between; align-items:center;
             padding:4px 0; border-bottom:1px solid #313244; font-size:.85rem; }
  .chk-row:last-child { border-bottom:none; }
  .score-box {
    background:#181825; border:1px solid #313244; border-radius:8px;
    padding:10px; margin-top:8px; text-align:center;
  }
  .score-num { font-size:2.2rem; font-weight:900; }
  .score-pos { color:#a6e3a1; }
  .score-neg { color:#f38ba8; }
  .score-neu { color:#fab387; }
</style>
""", unsafe_allow_html=True)

# ── Persistent storage (JSON file) ────────────────────────────────────────────
DATA_FILE = "bet_log.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=2)

bet_log = load_data()

# ── Helper: fetch 72-hour schedule ────────────────────────────────────────────
ET = pytz.timezone("America/New_York")

@st.cache_data(ttl=900)
def fetch_games_72h():
    now_et = datetime.now(ET)
    end_et = now_et + timedelta(hours=72)
    start_str = now_et.strftime("%m/%d/%Y")
    end_str   = end_et.strftime("%m/%d/%Y")
    try:
        games = statsapi.schedule(start_date=start_str, end_date=end_str)
    except Exception as e:
        st.error(f"MLB API error: {e}")
        return []
    # Filter only scheduled / warmup / live
    live_statuses = {"Scheduled", "Pre-Game", "Warmup", "In Progress"}
    out = []
    for g in games:
        if g.get("game_type") != "R":
            continue
        try:
            gdt = datetime.fromisoformat(g["game_datetime"].replace("Z", "+00:00"))
            gdt_et = gdt.astimezone(ET)
        except Exception:
            continue
        if gdt_et < now_et:
            continue
        g["game_datetime_et"] = gdt_et
        out.append(g)
    out.sort(key=lambda x: x["game_datetime_et"])
    return out

def abbrev(team_name: str) -> str:
    ABBR = {
        "Arizona Diamondbacks":"ARI","Atlanta Braves":"ATL","Baltimore Orioles":"BAL",
        "Boston Red Sox":"BOS","Chicago Cubs":"CHC","Chicago White Sox":"CWS",
        "Cincinnati Reds":"CIN","Cleveland Guardians":"CLE","Colorado Rockies":"COL",
        "Detroit Tigers":"DET","Houston Astros":"HOU","Kansas City Royals":"KC",
        "Los Angeles Angels":"LAA","Los Angeles Dodgers":"LAD","Miami Marlins":"MIA",
        "Milwaukee Brewers":"MIL","Minnesota Twins":"MIN","New York Mets":"NYM",
        "New York Yankees":"NYY","Oakland Athletics":"OAK","Philadelphia Phillies":"PHI",
        "Pittsburgh Pirates":"PIT","San Diego Padres":"SD","San Francisco Giants":"SF",
        "Seattle Mariners":"SEA","St. Louis Cardinals":"STL","Tampa Bay Rays":"TB",
        "Texas Rangers":"TEX","Toronto Blue Jays":"TOR","Washington Nationals":"WSH",
        "Athletics":"ATH",
    }
    for k, v in ABBR.items():
        if k in team_name:
            return v
    return team_name[:3].upper()

def game_label(g):
    away = abbrev(g["away_name"])
    home = abbrev(g["home_name"])
    dt   = g["game_datetime_et"]
    return f"{away} @ {home}  {dt.strftime('%-m/%-d %I:%M%p ET').replace('AM','am').replace('PM','pm')}"

def game_key(g):
    return str(g["game_id"])

# ── Checklist engine ───────────────────────────────────────────────────────────
CHECKLIST_T1 = [
    ("1.1.1", "Line active / not stale (Pinnacle moving)?"),
    ("1.1.2", "Game confirmed (no postponement risk)?"),
    ("1.1.3", "Starting pitcher confirmed on both sides?"),
    ("1.1.4", "Plate umpire known (UmpScorecards checked)?"),
    ("1.1.5", "Roof/weather not a binary blowout factor?"),
    ("1.2.1", "No relevant SP injury report in last 6h?"),
    ("1.2.2", "SP on normal rest (≥4 days)?"),
    ("1.2.3", "SP pitch count trend normal (not fatigued)?"),
    ("1.2.4", "No concerning postgame quotes from SP?"),
    ("1.2.5", "Opener/bulk arm confirmed if bullpen game?"),
    ("1.3.1", "Confirmed lineup posted (both sides)?"),
    ("1.3.2", "No key bat scratched vs platoon advantage?"),
    ("1.4.1", "Wind ≤12 mph OR direction neutral for park?"),
    ("1.4.2", "Temp reasonable (45°F–95°F range)?"),
    ("1.4.3", "No rain delay risk >30%?"),
]

CHECKLIST_T2 = [
    ("2.1.1",  "SP xERA vs ERA gap checked (luck-adjusted)?"),
    ("2.1.2",  "SP BABIP & LOB% regression flags cleared?"),
    ("2.1.3",  "SP velo/spin trending normal L5 starts?"),
    ("2.1.4",  "SP arm angle no recent mechanical change?"),
    ("2.1.5",  "Stuff+/Pitching+ within normal range?"),
    ("2.1.6",  "SP CSW% / Chase% / Whiff% trending OK?"),
    ("2.1.7",  "SP home/road & day/night splits considered?"),
    ("2.1.8",  "SP 1st-inning ERA vs rest-of-game noted?"),
    ("2.1.9",  "TTOP: 3rd time through order risk assessed?"),
    ("2.1.10", "Short-series familiarity cycle checked (2.1.18)?"),
    ("2.2.1",  "Bullpen usage logs checked last 3 days?"),
    ("2.2.2",  "No closer/setup arm taxed 3+ days in a row?"),
    ("2.2.3",  "Bullpen ERA/xFIP vs season norm?"),
    ("2.3.1",  "Lineup wRC+ vs LHP/RHP split applied?"),
    ("2.3.2",  "Recent L14d vs season avg hot/cold flag?"),
    ("2.3.3",  "Bat speed / swing decision trend checked?"),
    ("2.3.4",  "Lineup protection quality assessed?"),
    ("2.4.1",  "Park HR factor applied to run total?"),
    ("2.4.2",  "Marine layer flag checked (if West Coast night)?"),
    ("2.5.1",  "Ump zone size / run impact estimated?"),
    ("2.5.2",  "ABS-exempt game flag cleared?"),
]

CHECKLIST_T3 = [
    ("3.1.1", "xRuns vs actual runs regression flag?"),
    ("3.1.2", "HR/FB rate luck regression checked?"),
    ("3.1.3", "RISP wOBA vs overall wOBA divergence?"),
    ("3.2.1", "Schedule fatigue / travel considered?"),
    ("3.3.1", "Sharp money / steam move direction confirmed?"),
    ("3.3.2", "Line movement consistent with your side?"),
    ("3.3.3", "F5 vs full-game divergence play assessed?"),
    ("3.3.4", "RLM (reverse line movement) check done?"),
    ("3.4.1", "CLV benchmark (Pinnacle no-vig) set pre-bet?"),
]

RUN_ADJ_FACTORS = {
    "Wind +": ("Wind blowing OUT strongly (≥15 mph)", +0.40),
    "Wind -": ("Wind blowing IN strongly (≥15 mph)", -0.35),
    "Temp +": ("Very hot game (≥90°F)", +0.20),
    "Temp -": ("Cold game (≤45°F)", -0.20),
    "Marine": ("Marine layer confirmed (West Coast night)", -0.12),
    "Ump +":  ("Ump large zone — pitcher favored", -0.20),
    "Ump -":  ("Ump small zone — hitter favored", +0.20),
    "Park +":  ("High run-environment park (COL, CIN, etc.)", +0.30),
    "Park -":  ("Low run-environment park (SD, OAK, etc.)", -0.20),
    "Bull +":  ("Both bullpens fresh / lights out", -0.25),
    "Bull -":  ("Both bullpens depleted", +0.30),
    "F5 div": ("F5/Full-game divergence play active", +0.15),
    "Famil":  ("Short-series familiarity boost (2nd facing)", +0.10),
    "BatSpd-": ("Bat speed declining L14d both lineups", -0.10),
    "LinePro-":("Lineup protection broken (cleanup <.340 wOBA)", -0.08),
    "Sharp O": ("Sharp steam on Over", +0.20),
    "Sharp U": ("Sharp steam on Under", -0.20),
}

KELLY_TABLE = {
    "2%": 0.02, "3%": 0.03, "4%": 0.04, "5%": 0.05,
    "6%": 0.06, "7%": 0.07, "8%": 0.08, "10%": 0.10,
}

def kelly_stake(bankroll: float, edge_pct: float, odds_american: int) -> float:
    if odds_american < 0:
        implied = (-odds_american) / (-odds_american + 100)
    else:
        implied = 100 / (odds_american + 100)
    b = (1 / implied) - 1
    p = implied + edge_pct
    q = 1 - p
    full_kelly = (b * p - q) / b
    return max(0.0, full_kelly / 4) * bankroll

# ── Main UI ────────────────────────────────────────────────────────────────────
st.title("⚾ MLB Totals Bet Tracker")

tab_dash, tab_check, tab_log = st.tabs(["📋 Games (72h)", "✅ Pre-Bet Checklist", "📓 Bet Log"])

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — 72-hour game dashboard
# ════════════════════════════════════════════════════════════════════════════════
with tab_dash:
    st.subheader("Upcoming Games — Next 72 Hours")
    if st.button("🔄 Refresh Schedule"):
        st.cache_data.clear()
        st.rerun()

    games = fetch_games_72h()
    if not games:
        st.warning("No upcoming games found or API unavailable.")
    else:
        # Group by date
        from itertools import groupby
        from operator import itemgetter

        for date_str, day_games in groupby(games, key=lambda g: g["game_datetime_et"].strftime("%A, %B %-d")):
            day_list = list(day_games)
            st.markdown(f"### 📅 {date_str}  —  {len(day_list)} game{'s' if len(day_list)!=1 else ''}")
            for g in day_list:
                gk  = game_key(g)
                log = bet_log.get(gk, {})
                away = abbrev(g["away_name"])
                home = abbrev(g["home_name"])
                dt   = g["game_datetime_et"]
                away_prob = g.get("away_probable_pitcher","TBD")
                home_prob = g.get("home_probable_pitcher","TBD")

                market   = log.get("market", "—")
                stake    = log.get("stake",  "—")
                price    = log.get("price",  "—")
                fair     = log.get("fair",   "—")
                pin_cls  = log.get("pin_close","TBD")
                clv      = log.get("clv",    "TBD")
                notes    = log.get("notes",  "")
                decision = log.get("decision","—")

                tag_color = "tag-over" if "over" in decision.lower() else \
                            "tag-under" if "under" in decision.lower() else "tag-pass"

                st.markdown(f"""
<div class="bet-card">
  <h4>⚾ {away} @ {home} &nbsp;·&nbsp; {dt.strftime('%-I:%M %p ET')}</h4>
  <div class="field-label">Probable Pitchers</div>
  <div class="field-value">✈ {g['away_name']}: <b>{away_prob}</b> &nbsp;·&nbsp; 🏠 {g['home_name']}: <b>{home_prob}</b></div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px;">
    <div><div class="field-label">Market</div><div class="field-value">{market}</div></div>
    <div><div class="field-label">Stake</div><div class="field-value">{stake}</div></div>
    <div><div class="field-label">Price</div><div class="field-value">{price}</div></div>
    <div><div class="field-label">No-Vig Fair</div><div class="field-value">{fair}</div></div>
  </div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px;">
    <div><div class="field-label">Pinnacle Close</div><div class="field-value">{pin_cls}</div></div>
    <div><div class="field-label">CLV</div><div class="field-value">{clv}</div></div>
    <div><div class="field-label">Decision</div><div class="field-value"><span class="{tag_color}">{decision}</span></div></div>
  </div>
  {'<div class="field-label">Notes</div><div class="field-value" style="font-style:italic;color:#cba6f7;">' + notes + '</div>' if notes else ''}
</div>
""", unsafe_allow_html=True)

                with st.expander(f"✏️ Edit bet data — {away} @ {home}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        mkt  = st.text_input("Market (e.g. F5 Under 4.5)", value=log.get("market",""), key=f"mkt_{gk}")
                        pr   = st.text_input("Price (e.g. -115)", value=log.get("price",""), key=f"pr_{gk}")
                        fv   = st.text_input("No-vig fair value", value=log.get("fair",""), key=f"fv_{gk}")
                        dec  = st.selectbox("Decision", ["—","Over","Under","Pass","F5 Over","F5 Under"],
                                            index=["—","Over","Under","Pass","F5 Over","F5 Under"].index(log.get("decision","—"))
                                            if log.get("decision","—") in ["—","Over","Under","Pass","F5 Over","F5 Under"] else 0,
                                            key=f"dec_{gk}")
                    with c2:
                        stk  = st.text_input("Stake ($)", value=log.get("stake",""), key=f"stk_{gk}")
                        pin  = st.text_input("Pinnacle close (post-game)", value=log.get("pin_close",""), key=f"pin_{gk}")
                        clv_in = st.text_input("CLV (post-game)", value=log.get("clv",""), key=f"clv_{gk}")
                    nt = st.text_area("Notes", value=log.get("notes",""), height=80, key=f"nt_{gk}",
                                      placeholder="Bullpen-day trigger, wind, F5 divergence, etc.")
                    if st.button("💾 Save", key=f"save_{gk}"):
                        bet_log[gk] = {
                            "market": mkt, "price": pr, "fair": fv,
                            "decision": dec, "stake": stk,
                            "pin_close": pin, "clv": clv_in, "notes": nt,
                            "game_label": game_label(g),
                        }
                        save_data(bet_log)
                        st.success("Saved!")
                        st.rerun()

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — Pre-Bet Checklist
# ════════════════════════════════════════════════════════════════════════════════
with tab_check:
    st.subheader("Pre-Bet Checklist & Run Adjuster")

    games = fetch_games_72h()
    if not games:
        st.warning("No upcoming games found.")
    else:
        game_options = {game_label(g): g for g in games}
        selected_label = st.selectbox("Select Game", list(game_options.keys()))
        sel_game = game_options[selected_label]
        gk = game_key(sel_game)

        st.markdown("---")

        # ── Tier 1 ──
        st.markdown("#### 🔴 Tier 1 — Deal-Breakers")
        t1_checks = {}
        for code, question in CHECKLIST_T1:
            cols = st.columns([0.8, 0.2])
            with cols[0]:
                st.markdown(f"<div style='font-size:.85rem;padding:4px 0;'><b>{code}</b> {question}</div>",
                            unsafe_allow_html=True)
            with cols[1]:
                t1_checks[code] = st.checkbox("✓", key=f"t1_{gk}_{code}", label_visibility="collapsed")

        t1_pass = all(t1_checks.values())
        t1_score = sum(t1_checks.values())
        if t1_pass:
            st.markdown("<div class='tier-ok'>✅ Tier 1 CLEAR — proceed to Tier 2</div>", unsafe_allow_html=True)
        else:
            fails = [c for c, v in t1_checks.items() if not v]
            st.markdown(f"<div class='tier-pass'>🚫 Tier 1 FAIL — {len(fails)} red flags: {', '.join(fails)}</div>",
                        unsafe_allow_html=True)

        st.markdown("---")
        # ── Tier 2 ──
        st.markdown("#### 🟡 Tier 2 — Run-Adjustment Factors")
        t2_checks = {}
        for code, question in CHECKLIST_T2:
            cols = st.columns([0.8, 0.2])
            with cols[0]:
                st.markdown(f"<div style='font-size:.85rem;padding:4px 0;'><b>{code}</b> {question}</div>",
                            unsafe_allow_html=True)
            with cols[1]:
                t2_checks[code] = st.checkbox("✓", key=f"t2_{gk}_{code}", label_visibility="collapsed")
        t2_pct = sum(t2_checks.values()) / len(t2_checks) * 100
        st.markdown(f"<div class='tier-{'ok' if t2_pct>=75 else 'warn'}'>Tier 2: {t2_pct:.0f}% complete</div>",
                    unsafe_allow_html=True)

        st.markdown("---")
        # ── Tier 3 ──
        st.markdown("#### 🟢 Tier 3 — Market & Regression Signals")
        t3_checks = {}
        for code, question in CHECKLIST_T3:
            cols = st.columns([0.8, 0.2])
            with cols[0]:
                st.markdown(f"<div style='font-size:.85rem;padding:4px 0;'><b>{code}</b> {question}</div>",
                            unsafe_allow_html=True)
            with cols[1]:
                t3_checks[code] = st.checkbox("✓", key=f"t3_{gk}_{code}", label_visibility="collapsed")

        st.markdown("---")
        # ── Run Adjuster ──
        st.markdown("#### 🎯 Run Adjuster — Select Active Factors")
        base_line = st.number_input("Base Line (e.g. 8.5)", value=8.5, step=0.5, key=f"bl_{gk}")
        active_factors = []
        cols_f = st.columns(2)
        factor_items = list(RUN_ADJ_FACTORS.items())
        for i, (key, (desc, weight)) in enumerate(factor_items):
            col = cols_f[i % 2]
            with col:
                on = st.checkbox(f"{'▲' if weight>0 else '▼'} {key}: {desc} ({'+' if weight>0 else ''}{weight})",
                                  key=f"rf_{gk}_{key}")
                if on:
                    active_factors.append((key, weight))

        total_adj = sum(w for _, w in active_factors)
        adj_line  = base_line + total_adj
        direction = "OVER" if total_adj > 0.15 else ("UNDER" if total_adj < -0.15 else "NEUTRAL")
        dir_class = "score-pos" if direction=="OVER" else ("score-neg" if direction=="UNDER" else "score-neu")

        st.markdown(f"""
<div class="score-box">
  <div class="field-label">Base Line</div>
  <div class="field-value">{base_line}</div>
  <div class="field-label">Total Adjustment</div>
  <div class="field-value">{'+' if total_adj>=0 else ''}{total_adj:.2f} runs</div>
  <div class="field-label">Adjusted Fair Line</div>
  <div class="score-num {dir_class}">{adj_line:.1f}</div>
  <div class="field-label" style="margin-top:4px;">Signal</div>
  <div class="field-value"><b>{direction}</b></div>
</div>
""", unsafe_allow_html=True)

        st.markdown("---")
        # ── Kelly Sizer ──
        st.markdown("#### 💰 Quarter-Kelly Stake Calculator")
        bk = st.number_input("Bankroll ($)", value=6500.0, step=100.0, key=f"bk_{gk}")
        edge_input = st.selectbox("Estimated Edge", list(KELLY_TABLE.keys()), index=2, key=f"edge_{gk}")
        price_input = st.number_input("Bet Price (American odds, e.g. -115)", value=-115, step=5, key=f"odds_{gk}")
        edge_val = KELLY_TABLE[edge_input]
        recommended = kelly_stake(bk, edge_val, price_input)
        st.success(f"Quarter-Kelly Recommended Stake: **${recommended:,.2f}**")

        # ── Bet Card Output ──
        st.markdown("---")
        st.markdown("#### 📋 Bet Card Template")
        away = abbrev(sel_game["away_name"])
        home = abbrev(sel_game["home_name"])
        dt_et = sel_game["game_datetime_et"]
        log = bet_log.get(gk, {})

        card_text = f"""Date: {dt_et.strftime('%Y-%m-%d')}
Game: {away} @ {home} {dt_et.strftime('%-I:%M %p ET')}
Market: {log.get('market', 'F5 Under [LINE TBD]')}
Stake: ${recommended:,.2f} (quarter-Kelly)
Price: {log.get('price', '[TBD]')}
No-vig fair: {log.get('fair', 'TBD post-bet')}
Pinnacle close: {log.get('pin_close', 'TBD (log post-game)')}
CLV: {log.get('clv', 'TBD')}
Base line: {base_line} | Adj: {'+' if total_adj>=0 else ''}{total_adj:.2f} → Fair {adj_line:.1f}
Signal: {direction}
Active factors: {', '.join([k for k,_ in active_factors]) if active_factors else 'None'}
Notes: {log.get('notes', '')}
T1 pass: {'YES' if t1_pass else 'NO — ' + str(sum(1 for v in t1_checks.values() if not v)) + ' flags'}
T2 complete: {t2_pct:.0f}%"""

        st.code(card_text, language="text")

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — Bet Log
# ════════════════════════════════════════════════════════════════════════════════
with tab_log:
    st.subheader("📓 Bet Log")
    if not bet_log:
        st.info("No bets logged yet. Use the Games tab to add bet data.")
    else:
        for gk, data in sorted(bet_log.items(), reverse=True):
            label = data.get("game_label", f"Game {gk}")
            dec   = data.get("decision", "—")
            clv   = data.get("clv", "—")
            notes = data.get("notes", "")
            tag_color = "tag-over" if "over" in dec.lower() else \
                        "tag-under" if "under" in dec.lower() else "tag-pass"
            st.markdown(f"""
<div class="bet-card">
  <h4>⚾ {label}</h4>
  <div style="display:flex;gap:12px;flex-wrap:wrap;">
    <div><div class="field-label">Market</div><div class="field-value">{data.get('market','—')}</div></div>
    <div><div class="field-label">Price</div><div class="field-value">{data.get('price','—')}</div></div>
    <div><div class="field-label">Stake</div><div class="field-value">{data.get('stake','—')}</div></div>
    <div><div class="field-label">Fair</div><div class="field-value">{data.get('fair','—')}</div></div>
    <div><div class="field-label">CLV</div><div class="field-value">{clv}</div></div>
    <div><div class="field-label">Decision</div><div class="field-value"><span class="{tag_color}">{dec}</span></div></div>
  </div>
  {'<div class="field-label" style="margin-top:6px;">Notes</div><div class="field-value" style="font-style:italic;color:#cba6f7;">' + notes + '</div>' if notes else ''}
</div>
""", unsafe_allow_html=True)

        if st.button("🗑️ Clear All Bet Log Data"):
            bet_log.clear()
            save_data(bet_log)
            st.success("Cleared.")
            st.rerun()
