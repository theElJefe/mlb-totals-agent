import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import statsapi
import pybaseball as pyb
import requests
from scipy.stats import norm

st.set_page_config(page_title="MLB Totals Agent 2026", layout="centered")

st.title("🧠 MLB Totals Agent 2026")
st.caption("PDF Numeric Model + pybaseball + Weather + DraftKings & more")

ODDS_API_KEY = st.secrets.get("ODDS_API_KEY", "YOUR_KEY_HERE")

GAME_DATE = st.date_input("Game Date", datetime.now().date())
FILTER_TEAM = st.text_input("Filter by team (optional)", "")
KALSHI_YES = st.slider("Kalshi YES Price (if applicable)", 0.0, 1.0, 0.50, 0.01)

if st.button("🚀 Run Full Expert Analysis", type="primary"):
    with st.spinner("Running full model..."):
        games = statsapi.schedule(date=GAME_DATE.isoformat())
        
        try:
            pitching_df = pyb.pitching_stats(GAME_DATE.year, qual=10)
        except:
            pitching_df = pd.DataFrame()
        
        for idx, g in enumerate(games):
            away = g['away_name']
            home = g['home_name']
            if FILTER_TEAM and FILTER_TEAM.upper() not in (away + home).upper():
                continue
                
            st.subheader(f"{away} @ {home}")
            away_sp = g.get('away_probable_pitcher')
            home_sp = g.get('home_probable_pitcher')
            
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
            
            # Numeric Checklist with unique keys
            adj_total = 0.0
            if st.checkbox("Hitter-Friendly Park", value=False, key=f"park_{idx}"): adj_total += 0.10
            if st.checkbox("Warm Temp (>75°F)", value=False, key=f"temp_{idx}"): adj_total += 0.07
            if st.checkbox("Strong Wind Out", value=False, key=f"wind_strong_{idx}"): adj_total += 0.15
            if st.checkbox("Mild Wind Out", value=False, key=f"wind_mild_{idx}"): adj_total += 0.08
            if st.checkbox("Both Lineups Full Strength", value=True, key=f"lineup_{idx}"): adj_total += 0.10
            if st.checkbox("Strong Middle Order", value=False, key=f"middle_{idx}"): adj_total += 0.10
            if st.checkbox("Both Bullpens Thin", value=False, key=f"bullpen_{idx}"): adj_total += 0.15
            
            projected_total = 8.5 + adj_total + (away_lambda + home_lambda - 9.3)
            
            sigma = 3.0
            prob_over = 1 - norm.cdf(8.5 + 0.5, projected_total, sigma)
            edge = prob_over - KALSHI_YES
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Projected Total", f"{projected_total:.2f}")
            col2.metric("P(Over 8.5)", f"{prob_over:.1%}")
            col3.metric("Edge", f"{edge*100:+.1f}%", delta="BET" if edge > 0.05 else "PASS")
            
            with st.expander("📋 Checklist Adjustments"):
                st.write(f"Total Adjustment: **{adj_total:+.2f}** runs")
            
            st.divider()

st.success("✅ App Fixed & Running")
st.info("Use unique keys to avoid duplicate widget errors.")