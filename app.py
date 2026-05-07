import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import statsapi
import pybaseball as pyb
from scipy.stats import norm

st.set_page_config(page_title="MLB Totals Agent 2026", layout="centered")

st.title("🧠 MLB Totals Agent 2026")
st.caption("Stable Per-Game Projections • Numeric Model")

GAME_DATE = st.date_input("Game Date", datetime.now().date())
FILTER_TEAM = st.text_input("Filter by team (optional)", "")

# Global Adjustments (apply to all games)
st.subheader("📋 Global Adjustments")
adj = 0.0
c1, c2 = st.columns(2)
with c1:
    if st.checkbox("Hitter-Friendly Park", value=False, key="global_park"): adj += 0.10
    if st.checkbox("Warm Temp (>75°F)", value=False, key="global_temp"): adj += 0.07
    if st.checkbox("Strong Wind Out", value=False, key="global_wind_strong"): adj += 0.15
    if st.checkbox("Mild Wind Out", value=False, key="global_wind_mild"): adj += 0.08
with c2:
    if st.checkbox("Both Lineups Full Strength", value=True, key="global_lineup"): adj += 0.10
    if st.checkbox("Strong Middle Order", value=False, key="global_middle"): adj += 0.10
    if st.checkbox("Both Bullpens Thin", value=False, key="global_bullpen"): adj += 0.15

if st.button("🚀 Run Full Analysis", type="primary"):
    with st.spinner("Analyzing slate..."):
        games = statsapi.schedule(date=GAME_DATE.isoformat())
        
        try:
            pitching_df = pyb.pitching_stats(GAME_DATE.year, qual=10)
        except:
            pitching_df = pd.DataFrame()
        
        for g in games:
            away = g['away_name']
            home = g['home_name']
            if FILTER_TEAM and FILTER_TEAM.upper() not in (away + home).upper():
                continue
                
            st.subheader(f"{away} @ {home}")
            away_sp = g.get('away_probable_pitcher', 'TBD')
            home_sp = g.get('home_probable_pitcher', 'TBD')
            st.caption(f"SP: {away_sp} vs {home_sp}")
            
            # Pitcher quality variation
            base = 4.65
            def get_lambda(sp_name):
                if not sp_name or pitching_df.empty:
                    return base
                row = pitching_df[pitching_df['Name'].str.contains(sp_name.split()[-1], na=False, case=False)]
                if row.empty:
                    return base
                p_plus = float(row.get('Pitching+', 100).iloc[0])
                s_plus = float(row.get('Stuff+', 100).iloc[0])
                return base * (100 / p_plus) * (100 / s_plus)**0.3
            
            away_lambda = get_lambda(away_sp)
            home_lambda = get_lambda(home_sp)
            
            projected = 8.5 + adj + (away_lambda + home_lambda - 9.3)
            prob_over = 1 - norm.cdf(8.5 + 0.5, projected, 3.0)
            edge = prob_over - 0.50
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Projected Total", f"{projected:.2f}")
            col2.metric("P(Over 8.5)", f"{prob_over:.1%}")
            col3.metric("Edge", f"{edge*100:+.1f}%", 
                       delta="✅ BET OVER" if edge > 0.05 else "❌ PASS")
            
            with st.expander("Details"):
                st.write(f"Adjustment: **{adj:+.2f}** | Pitching: {away_lambda:.2f} / {home_lambda:.2f}")
            
            st.divider()

st.info("Adjustments above now affect all games. Pitcher quality creates variation.")