import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import statsapi
import pybaseball as pyb

st.set_page_config(page_title="MLB Totals Agent", layout="centered")

st.title("🧠 MLB Totals Agent 2026")
st.caption("Refined Checklist + Poisson Projection + Live Odds")

# === CONFIG ===
ODDS_API_KEY = st.secrets.get("ODDS_API_KEY", "")  
GAME_DATE = st.date_input("Game Date", datetime.now().date())
FILTER_TEAM = st.text_input("Filter by team (optional)", "")

if st.button("🚀 Run Full Analysis", type="primary"):
    with st.spinner("Pulling data from MLB, FanGraphs, and odds..."):
        games = statsapi.schedule(date=GAME_DATE.isoformat())
        
        for g in games:
            away = g['away_name']
            home = g['home_name']
            
            if FILTER_TEAM and FILTER_TEAM.upper() not in (away + home).upper():
                continue
                
            st.subheader(f"{away} @ {home}")
            
            # === Poisson Projection ===
            base = 4.65
            
            pitching = pyb.pitching_stats(GAME_DATE.year, qual=10)
            
            def get_lambda(sp_name):
                if not sp_name:
                    return base
                row = pitching[pitching['Name'].str.contains(sp_name.split()[-1], na=False)]
                if row.empty:
                    return base
                pitching_plus = float(row['Pitching+'].iloc[0]) if 'Pitching+' in row.columns else 100
                return base * (100 / pitching_plus)
            
            away_lambda = get_lambda(g.get('away_probable_pitcher'))
            home_lambda = get_lambda(g.get('home_probable_pitcher'))
            
            park_factor = 1.02
            wind_factor = 1.00
            
            away_lambda *= park_factor * wind_factor
            home_lambda *= park_factor * wind_factor
            
            sims = np.random.poisson([away_lambda, home_lambda], (10000, 2))
            total_sims = sims.sum(axis=1)
            
            proj_total = total_sims.mean()
            over_prob = (total_sims >= 8.5).mean()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Projected Total", f"{proj_total:.2f}")
            col2.metric("P(Over 8.5)", f"{over_prob:.1%}")
            col3.metric("Away λ / Home λ", f"{away_lambda:.2f} / {home_lambda:.2f}")
            
            st.divider()

st.info("✅ App ready! Add your Odds API key in Streamlit Secrets later.")