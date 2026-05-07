# -*- coding: utf-8 -*-
"""
MLB Totals Analyzer - pybaseball edition
=========================================
A Streamlit app that pulls Statcast, FanGraphs, and Baseball Reference data
via pybaseball to support pre-game total-runs (Over/Under) analysis.

This is a standalone analytical view - it does NOT replace the Pre-Bet
Checklist. Use it as a parallel data source to compare against your
existing checklist workflow.

Author: Joint Cyber Solutions / Jeff Hartsfield
License: MIT
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta
import plotly.express as px
import plotly.graph_objects as go

# pybaseball imports - lazy-loaded inside functions where possible
# to keep cold-start time reasonable on Streamlit Cloud
import pybaseball as pyb
from pybaseball import (
    statcast,
    statcast_pitcher,
    statcast_batter,
    playerid_lookup,
    pitching_stats,
    batting_stats,
    team_batting,
    team_pitching,
    schedule_and_record,
)

# Enable pybaseball's local cache to reduce repeated scraping
pyb.cache.enable()

# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="MLB Totals Analyzer",
    page_icon="baseball",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("MLB Totals Analyzer - pybaseball edition")
st.caption(
    "A parallel analytical view for total-runs evaluation. "
    "Run alongside the Pre-Bet Checklist, not in place of it."
)

# ============================================================================
# PARK FACTOR REFERENCE (static - Statcast 3-year rolling, manually maintained)
# Source: baseballsavant.mlb.com/leaderboard/statcast-park-factors
# Update this table at the start of each season.
# ============================================================================

PARK_FACTORS = {
    # team_abbr: (runs_factor, hr_factor, marine_layer_flag)
    "COL": (1.13, 1.18, False),  # Coors - altitude king
    "CIN": (1.07, 1.21, False),
    "BOS": (1.06, 1.04, False),
    "PHI": (1.04, 1.10, False),
    "TEX": (1.03, 1.05, False),
    "KCR": (1.03, 0.93, False),
    "ATL": (1.02, 1.04, False),
    "ARI": (1.01, 1.05, False),
    "TOR": (1.01, 1.06, False),
    "BAL": (1.00, 1.07, False),
    "MIN": (1.00, 1.01, False),
    "HOU": (1.00, 1.04, False),
    "WSH": (0.99, 0.97, False),
    "CHW": (0.99, 1.07, False),
    "STL": (0.99, 0.92, False),
    "NYY": (0.99, 1.10, False),
    "MIL": (0.99, 1.05, False),
    "TBR": (0.98, 0.95, False),
    "ATH": (0.98, 0.92, True),   # Sutter Health Park - interim, but West Coast
    "CHC": (0.97, 1.02, False),
    "NYM": (0.97, 1.00, False),
    "LAD": (0.96, 0.98, False),  # marginal marine layer effect at night
    "DET": (0.96, 0.91, False),
    "CLE": (0.95, 0.94, False),
    "MIA": (0.94, 0.85, False),
    "LAA": (0.94, 0.97, True),   # Angel Stadium - directional marine effect
    "SEA": (0.93, 0.92, True),   # T-Mobile Park
    "PIT": (0.93, 0.86, False),
    "SFG": (0.92, 0.83, True),   # Oracle Park - confirmed marine layer
    "SDP": (0.92, 0.88, True),   # Petco Park - confirmed marine layer
}

TEAM_NAME_MAP = {
    "ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves", "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox", "CHC": "Chicago Cubs", "CHW": "Chicago White Sox",
    "CIN": "Cincinnati Reds", "CLE": "Cleveland Guardians", "COL": "Colorado Rockies",
    "DET": "Detroit Tigers", "HOU": "Houston Astros", "KCR": "Kansas City Royals",
    "LAA": "Los Angeles Angels", "LAD": "Los Angeles Dodgers", "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers", "MIN": "Minnesota Twins", "NYM": "New York Mets",
    "NYY": "New York Yankees", "ATH": "Athletics", "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates", "SDP": "San Diego Padres", "SFG": "San Francisco Giants",
    "SEA": "Seattle Mariners", "STL": "St. Louis Cardinals", "TBR": "Tampa Bay Rays",
    "TEX": "Texas Rangers", "TOR": "Toronto Blue Jays", "WSH": "Washington Nationals",
}

# ============================================================================
# CACHED DATA PULLS
# ============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def get_pitching_leaderboard(season: int) -> pd.DataFrame:
    """Season-level pitching stats from FanGraphs. Cached 1h."""
    df = pitching_stats(season, qual=10)
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def get_batting_leaderboard(season: int) -> pd.DataFrame:
    """Season-level batting stats from FanGraphs. Cached 1h."""
    df = batting_stats(season, qual=30)
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def get_team_batting(season: int) -> pd.DataFrame:
    """Team-level batting from FanGraphs. Cached 1h."""
    return team_batting(season)

@st.cache_data(ttl=3600, show_spinner=False)
def get_team_pitching(season: int) -> pd.DataFrame:
    """Team-level pitching from FanGraphs. Cached 1h."""
    return team_pitching(season)

@st.cache_data(ttl=900, show_spinner=False)
def get_pitcher_id(last: str, first: str):
    """Look up MLBAM player ID. Returns int or None."""
    df = playerid_lookup(last.strip(), first.strip())
    if df.empty:
        return None
    # Take the most recently active player matching the name
    df = df.sort_values("mlb_played_last", ascending=False)
    pid = df.iloc[0]["key_mlbam"]
    return int(pid) if pd.notna(pid) else None

@st.cache_data(ttl=900, show_spinner=False)
def get_pitcher_recent_statcast(pid: int, days: int = 21) -> pd.DataFrame:
    """Pitch-level Statcast data for a pitcher's last N days."""
    end = date.today()
    start = end - timedelta(days=days)
    df = statcast_pitcher(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), pid)
    return df

# ============================================================================
# ANALYTICAL HELPERS - checklist-aligned scoring
# ============================================================================

def score_pitcher_quality(row):
    """
    T1 pitcher quality signal. Returns (run_adjustment, narrative).
    Negative = under lean; positive = over lean.
    Aligned with checklist Tier 1 deal-breaker weights.
    """
    xera = row.get("xERA", row.get("ERA", 4.20))
    siera = row.get("SIERA", xera)
    k_pct = row.get("K%", 22.0)
    bb_pct = row.get("BB%", 8.0)

    # Composite: weight xERA heavily, SIERA secondary, K-BB% as tiebreaker
    composite = 0.6 * xera + 0.4 * siera

    if composite <= 3.00:
        return -0.25, "Elite (xERA/SIERA composite {:.2f}) -> strong under signal".format(composite)
    elif composite <= 3.50:
        return -0.15, "Above-average ({:.2f}) -> moderate under signal".format(composite)
    elif composite <= 4.00:
        return -0.05, "League average ({:.2f}) -> slight under".format(composite)
    elif composite <= 4.50:
        return +0.10, "Below average ({:.2f}) -> moderate over signal".format(composite)
    else:
        return +0.20, "Poor ({:.2f}) -> strong over signal".format(composite)


def score_park(team_abbr: str, is_night: bool):
    """T2 park + marine layer signal."""
    if team_abbr not in PARK_FACTORS:
        return 0.0, "Unknown park for {} - neutral".format(team_abbr)

    runs_pf, hr_pf, marine = PARK_FACTORS[team_abbr]
    base_adj = (runs_pf - 1.00) * 8.5  # scale runs factor to typical 8.5 total

    narrative_parts = ["Run factor {:.2f}, HR factor {:.2f}".format(runs_pf, hr_pf)]

    marine_adj = 0.0
    if marine and is_night:
        marine_adj = -0.12
        narrative_parts.append("Marine layer flagged at night - additional under pressure (-0.12)")
    elif marine and not is_night:
        narrative_parts.append("Marine layer park but day game - no additional adjustment")

    total = base_adj + marine_adj
    return total, " | ".join(narrative_parts)


def score_team_offense(team_row):
    """T2 team offensive quality."""
    wrc_plus = team_row.get("wRC+", 100)
    woba = team_row.get("wOBA", 0.310)
    babip = team_row.get("BABIP", 0.290)

    if wrc_plus >= 115:
        adj = +0.10
        tone = "Strong offense"
    elif wrc_plus >= 105:
        adj = +0.05
        tone = "Above-average offense"
    elif wrc_plus >= 95:
        adj = 0.0
        tone = "League-average offense"
    elif wrc_plus >= 85:
        adj = -0.05
        tone = "Below-average offense"
    else:
        adj = -0.10
        tone = "Weak offense"

    # BABIP regression flag (T3)
    babip_note = ""
    if babip < 0.275:
        babip_note = " | BABIP {:.3f} - positive regression risk (mild over flag)".format(babip)
    elif babip > 0.315:
        babip_note = " | BABIP {:.3f} - negative regression risk (mild under flag)".format(babip)

    return adj, "{} (wRC+ {:.0f}, wOBA {:.3f}){}".format(tone, wrc_plus, woba, babip_note)


def detect_form_trend(pitcher_df: pd.DataFrame):
    """
    L21d trend check on pitcher Statcast data.
    Looks at velocity and whiff trends - proxy for the checklist 2.1.5-2.1.10 cluster.
    """
    if pitcher_df.empty:
        return 0.0, "No recent Statcast data available"

    # Velocity trend: split into halves and compare
    pitcher_df = pitcher_df.sort_values("game_date").reset_index(drop=True)
    midpoint = len(pitcher_df) // 2
    if midpoint < 10:
        return 0.0, "Insufficient pitch sample for trend"

    early = pitcher_df.iloc[:midpoint]
    late = pitcher_df.iloc[midpoint:]

    early_velo = early["release_speed"].mean()
    late_velo = late["release_speed"].mean()
    velo_delta = late_velo - early_velo

    notes = ["Velocity trend: {:.1f} -> {:.1f} mph (delta {:+.2f})".format(early_velo, late_velo, velo_delta)]

    adj = 0.0
    if velo_delta <= -0.8:
        adj += 0.08
        notes.append("Significant velocity decline -> mild over lean")
    elif velo_delta >= 0.5:
        adj -= 0.05
        notes.append("Velocity ticking up -> mild under lean")

    # Whiff trend (description == 'swinging_strike')
    if "description" in pitcher_df.columns:
        early_whiff = (early["description"] == "swinging_strike").mean()
        late_whiff = (late["description"] == "swinging_strike").mean()
        whiff_delta = late_whiff - early_whiff
        notes.append("Whiff%: {:.1f} -> {:.1f} (delta {:+.1f}pp)".format(
            early_whiff * 100, late_whiff * 100, whiff_delta * 100))
        if whiff_delta <= -0.03:
            adj += 0.05
            notes.append("Whiff rate falling -> mild over lean")

    return adj, " | ".join(notes)


# ============================================================================
# SIDEBAR - Game Configuration
# ============================================================================

with st.sidebar:
    st.header("Game Setup")

    season = st.number_input(
        "Season",
        min_value=2020,
        max_value=date.today().year,
        value=date.today().year,
        step=1,
    )

    away_team = st.selectbox(
        "Away team",
        options=sorted(TEAM_NAME_MAP.keys()),
        index=sorted(TEAM_NAME_MAP.keys()).index("STL"),
        format_func=lambda x: "{} - {}".format(x, TEAM_NAME_MAP[x]),
    )
    home_team = st.selectbox(
        "Home team",
        options=sorted(TEAM_NAME_MAP.keys()),
        index=sorted(TEAM_NAME_MAP.keys()).index("SDP"),
        format_func=lambda x: "{} - {}".format(x, TEAM_NAME_MAP[x]),
    )

    st.divider()
    st.subheader("Starting pitchers")

    away_p_first = st.text_input("Away SP first name", value="Matthew")
    away_p_last = st.text_input("Away SP last name", value="Liberatore")
    home_p_first = st.text_input("Home SP first name", value="Michael")
    home_p_last = st.text_input("Home SP last name", value="King")

    st.divider()

    posted_total = st.number_input(
        "Posted total (O/U line)",
        min_value=5.0,
        max_value=15.0,
        value=8.0,
        step=0.5,
    )

    is_night = st.checkbox("Night game", value=True)

    run_btn = st.button("Run analysis", type="primary", use_container_width=True)

    st.divider()
    with st.expander("About this app"):
        st.markdown(
            "Pulls live data via pybaseball from Baseball Savant, FanGraphs, "
            "and Baseball Reference. Cache TTL: 15-60 min depending on endpoint. "
            "First load may take 30-60s as caches warm up."
        )

# ============================================================================
# MAIN ANALYSIS FLOW
# ============================================================================

if run_btn:
    if away_team == home_team:
        st.error("Away and home team can't be the same.")
        st.stop()

    progress = st.progress(0, text="Pulling team-level pitching stats...")

    # ---- Team data ----
    try:
        team_pit = get_team_pitching(season)
        progress.progress(15, text="Pulling team-level batting stats...")
        team_bat = get_team_batting(season)
    except Exception as e:
        st.error("Team data fetch failed: {}".format(e))
        st.stop()

    progress.progress(30, text="Looking up starting pitchers...")

    # ---- Pitcher IDs ----
    away_pid = get_pitcher_id(away_p_last, away_p_first)
    home_pid = get_pitcher_id(home_p_last, home_p_first)

    if not away_pid:
        st.warning("Could not find MLBAM ID for {} {} - pitcher signal will be neutral.".format(
            away_p_first, away_p_last))
    if not home_pid:
        st.warning("Could not find MLBAM ID for {} {} - pitcher signal will be neutral.".format(
            home_p_first, home_p_last))

    progress.progress(45, text="Pulling FanGraphs pitcher leaderboard...")

    # ---- Pitcher season stats ----
    try:
        pit_lb = get_pitching_leaderboard(season)
    except Exception as e:
        st.warning("FanGraphs pitcher leaderboard unavailable: {}".format(e))
        pit_lb = pd.DataFrame()

    def find_pitcher_row(lb: pd.DataFrame, first: str, last: str):
        if lb.empty:
            return None
        full = "{} {}".format(first, last).lower()
        match = lb[lb["Name"].str.lower() == full]
        if match.empty:
            match = lb[lb["Name"].str.lower().str.contains(last.lower())]
        return match.iloc[0] if not match.empty else None

    away_p_row = find_pitcher_row(pit_lb, away_p_first, away_p_last)
    home_p_row = find_pitcher_row(pit_lb, home_p_first, home_p_last)

    progress.progress(60, text="Pulling recent Statcast pitch data...")

    # ---- Recent pitch-level data (last 21 days) ----
    away_statcast = get_pitcher_recent_statcast(away_pid) if away_pid else pd.DataFrame()
    home_statcast = get_pitcher_recent_statcast(home_pid) if home_pid else pd.DataFrame()

    progress.progress(80, text="Computing signals...")

    # ---- Compute signals ----
    signals = []

    # Pitcher quality (T1)
    for label, row in [("{} {}".format(away_p_first, away_p_last), away_p_row),
                       ("{} {}".format(home_p_first, home_p_last), home_p_row)]:
        if row is not None:
            adj, narrative = score_pitcher_quality(row)
            signals.append({
                "Tier": "T1",
                "Factor": "{} quality".format(label),
                "Adjustment": adj,
                "Notes": narrative,
            })
        else:
            signals.append({
                "Tier": "T1",
                "Factor": "{} quality".format(label),
                "Adjustment": 0.0,
                "Notes": "No FanGraphs data - neutral",
            })

    # Pitcher form trend (T2)
    for label, df in [("{} {}".format(away_p_first, away_p_last), away_statcast),
                      ("{} {}".format(home_p_first, home_p_last), home_statcast)]:
        adj, narrative = detect_form_trend(df)
        signals.append({
            "Tier": "T2",
            "Factor": "{} L21d form".format(label),
            "Adjustment": adj,
            "Notes": narrative,
        })

    # Park + marine layer (T2)
    park_adj, park_note = score_park(home_team, is_night)
    signals.append({
        "Tier": "T2",
        "Factor": "{} park factor".format(home_team),
        "Adjustment": park_adj,
        "Notes": park_note,
    })

    # Team offense (T2)
    def find_team_row(team_df: pd.DataFrame, abbr: str):
        if team_df.empty:
            return None
        candidates = [abbr, TEAM_NAME_MAP.get(abbr, "")]
        for c in candidates:
            if not c:
                continue
            match = team_df[team_df["Team"].astype(str).str.contains(c, case=False, na=False)]
            if not match.empty:
                return match.iloc[0]
        return None

    away_team_row = find_team_row(team_bat, away_team)
    home_team_row = find_team_row(team_bat, home_team)

    if away_team_row is not None:
        adj, narrative = score_team_offense(away_team_row)
        signals.append({
            "Tier": "T2",
            "Factor": "{} offense".format(away_team),
            "Adjustment": adj,
            "Notes": narrative,
        })
    if home_team_row is not None:
        adj, narrative = score_team_offense(home_team_row)
        signals.append({
            "Tier": "T2",
            "Factor": "{} offense".format(home_team),
            "Adjustment": adj,
            "Notes": narrative,
        })

    progress.progress(100, text="Done.")
    progress.empty()

    # ========================================================================
    # RESULTS DISPLAY
    # ========================================================================

    sig_df = pd.DataFrame(signals)
    total_adj = sig_df["Adjustment"].sum()

    # Baseline expected total: blend of league avg and team-specific scoring
    league_avg_total = 8.6  # 2024-2025 league avg ~4.3 R/G per team
    expected_total = league_avg_total + total_adj

    edge = expected_total - posted_total

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Posted total", "{:.1f}".format(posted_total))
    col2.metric("Model expected", "{:.2f}".format(expected_total), "{:+.2f} adj".format(total_adj))
    col3.metric("Edge vs line", "{:+.2f}".format(edge))

    if abs(edge) < 0.30:
        verdict = "NO PLAY"
        verdict_help = "Edge under 0.30 runs - inside model noise"
    elif edge >= 0.30:
        verdict = "OVER lean"
        verdict_help = "Model implies +{:.2f} runs vs posted line".format(edge)
    else:
        verdict = "UNDER lean"
        verdict_help = "Model implies {:.2f} runs vs posted line".format(edge)

    col4.metric("Verdict", verdict, help=verdict_help)

    st.divider()

    # Signal breakdown
    st.subheader("Signal breakdown")
    st.dataframe(
        sig_df.style.format({"Adjustment": "{:+.2f}"}).background_gradient(
            subset=["Adjustment"], cmap="RdYlGn_r", vmin=-0.30, vmax=0.30
        ),
        use_container_width=True,
        hide_index=True,
    )

    # Visual
    fig = px.bar(
        sig_df,
        x="Adjustment",
        y="Factor",
        color="Adjustment",
        color_continuous_scale="RdYlGn_r",
        color_continuous_midpoint=0,
        orientation="h",
        title="Run adjustments by factor (negative = under, positive = over)",
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---- Raw pitcher detail (expanders) ----
    st.subheader("Pitcher detail")
    pcol1, pcol2 = st.columns(2)

    with pcol1:
        with st.expander("{} {} - season stats".format(away_p_first, away_p_last), expanded=False):
            if away_p_row is not None:
                st.dataframe(away_p_row.to_frame(name="Value"))
            else:
                st.info("No leaderboard row found.")
        with st.expander("{} {} - recent Statcast (L21d)".format(away_p_first, away_p_last)):
            if not away_statcast.empty:
                summary = away_statcast.groupby("pitch_type").agg(
                    pitches=("release_speed", "count"),
                    avg_velo=("release_speed", "mean"),
                    avg_spin=("release_spin_rate", "mean"),
                ).round(1)
                st.dataframe(summary)
                st.caption("Total pitches in window: {}".format(len(away_statcast)))
            else:
                st.info("No Statcast data in window.")

    with pcol2:
        with st.expander("{} {} - season stats".format(home_p_first, home_p_last), expanded=False):
            if home_p_row is not None:
                st.dataframe(home_p_row.to_frame(name="Value"))
            else:
                st.info("No leaderboard row found.")
        with st.expander("{} {} - recent Statcast (L21d)".format(home_p_first, home_p_last)):
            if not home_statcast.empty:
                summary = home_statcast.groupby("pitch_type").agg(
                    pitches=("release_speed", "count"),
                    avg_velo=("release_speed", "mean"),
                    avg_spin=("release_spin_rate", "mean"),
                ).round(1)
                st.dataframe(summary)
                st.caption("Total pitches in window: {}".format(len(home_statcast)))
            else:
                st.info("No Statcast data in window.")

    st.divider()

    # ---- Honesty section ----
    with st.expander("Caveats - read before betting"):
        st.markdown("""
        - **This is not a replacement for the Pre-Bet Checklist.** It's a parallel data view.
          The model is intentionally simple to keep behavior auditable.
        - **Park factors are static** - update PARK_FACTORS at season start. They are
          Statcast 3-year rolling factors, not single-season noise.
        - **No bullpen, weather, ump, or lineup data** is integrated yet. Those remain
          checklist responsibilities for now.
        - **Marine layer flag is binary** - true marine-layer effect varies by onshore-flow
          conditions on the day. Cross-reference with weather.gov coastal forecast.
        - **Edge < 0.30 runs is noise.** A "0.4-run edge" is not a green light; it's a
          modest signal that should align with checklist conclusions before you bet.
        - **CLV is the only honest scoreboard.** Track no-vig Pinnacle close vs. your bet
          number across 200+ wagers - short-term P&L is variance.
        """)

else:
    st.info("Configure the game in the sidebar and click Run analysis to begin.")

    with st.expander("What this app does"):
        st.markdown("""
        This app is a **second analytical view** designed to run in parallel with the
        Pre-Bet Checklist (Tiers 1-4). It pulls live data via the pybaseball library
        from three sources:

        - **Baseball Savant** (Statcast pitch-level data, expected stats)
        - **FanGraphs** (xERA, SIERA, wRC+, BABIP, K%, BB%, leaderboards)
        - **Baseball Reference** (schedule and record)

        It computes a small set of run adjustments aligned with checklist weights:
        - T1: Starting pitcher quality (xERA/SIERA composite)
        - T2: Pitcher L21d form trend (Statcast velocity + whiff)
        - T2: Park factor + marine layer flag (Petco, Oracle, T-Mobile, Angel Stadium)
        - T2: Team offense (wRC+, wOBA, BABIP regression)

        The output is an **expected total**, an **edge vs. the posted line**, and a
        per-factor signal breakdown you can compare against your checklist conclusions
        before integrating.
        """)