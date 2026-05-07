import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import statsapi
import pybaseball as pyb

st.set_page_config(page_title="MLB Totals Agent", layout="centered")

st.title("🧠 MLB Totals Agent 2026")
st.caption("Expert PDF Checklist + pybaseball + Poisson Projection")

GAME_DATE = st.date_input("Game Date", datetime.now().date())
FILTER_TEAM = st.text_input("Filter by team (optional)", "")

if st.button("🚀 Run Full Analysis", type="primary"):
    with st.spinner("Fetching data from FanGraphs, Savant & MLB..."):
        games = statsapi.schedule(date=GAME_DATE.isoformat())
        
        pitching_df = pyb.pitching_stats(GAME_DATE.year, qual=10)
        
        for g in games:
            away = g['away_name']
            home = g['home_name']
            
            if FILTER_TEAM and FILTER_TEAM.upper() not in (away + home).upper():
                continue
                
            st.subheader(f"{away} @ {home}")
            
            # Pull probable pitchers
            away_sp = g.get('away_probable_pitcher')
            home_sp = g.get('home_probable_pitcher')
            
            st.write(f"**SP:** {away_sp} vs {home_sp}")
            
            # === Enhanced pybaseball Projection ===
            base = 4.65
            
            def get_lambda(sp_name):
                if not sp_name:
                    return base
                row = pitching_df[pitching_df['Name'].str.contains(sp_name.split()[-1], na=False, case=False)]
                if row.empty:
                    return base
                pitching_plus = float(row['Pitching+'].iloc[0]) if 'Pitching+' in row.columns else 100
                stuff_plus = float(row['Stuff+'].iloc[0]) if 'Stuff+' in row.columns else 100
                return base * (100 / pitching_plus) * (100 / stuff_plus)**0.3
            
            away_lambda = get_lambda(away_sp)
            home_lambda = get_lambda(home_sp)
            
            # PDF multipliers
            park_factor = 1.02
            wind_factor = 1.00  # Will add real weather next
            
            away_lambda *= park_factor * wind_factor
            home_lambda *= park_factor * wind_factor
            
            # Monte Carlo
            n_sims = 15000
            sims = np.random.poisson([away_lambda, home_lambda], (n_sims, 2))
            total_sims = sims.sum(axis=1)
            
            proj_total = total_sims.mean()
            over_prob = (total_sims >= 8.5).mean()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Projected Total", f"{proj_total:.2f}")
            col2.metric("P(Over 8.5)", f"{over_prob:.1%}")
            col3.metric("λ", f"{away_lambda:.2f} / {home_lambda:.2f}")
            
            with st.expander("📋 PDF Tier 1-2 Checklist"):
                st.write("• Starter Stuff+/Pitching+ ✓ (pulled)")
                st.write("• Bullpen rest: Pending")
                st.write("• Park × Wind: Pending real API")
                st.write("• ABS / Defense: Pending")
                st.write("• Lineup wRC+: Pending")
            
            st.divider()

st.success("✅ pybaseball Integrated!")
st.info("Next: Add real weather/wind + full Tier 2 + live odds")