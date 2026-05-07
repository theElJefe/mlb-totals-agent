import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import statsapi
import pybaseball as pyb
from scipy.stats import norm

st.set_page_config(page_title="MLB Totals Agent 2026", layout="centered")

st.title("🧠 MLB Totals Agent 2026")
st.caption("Per-Game Pitcher-Driven Projections")

GAME_DATE = st.date_input("Game Date", datetime.now().date())
FILTER_TEAM = st.text_input("Filter by team (optional)", "")

if st.button("🚀 Run Full Analysis", type="primary"):
    with st.spinner("Fetching data and calculating..."):
        games = statsapi.schedule(date=GAME_DATE.isoformat())
        
        try:
            pitching_df = pyb.pitching_stats(GAME_DATE.year, qual=10)
            st.success(f"Loaded {len(pitching_df)} pitchers")
        except:
            pitching_df = pd.DataFrame()
            st.warning("Using default pitching values")
        
        for g in games:
            away = g['away_name']
            home = g['home_name']
            if FILTER_TEAM and FILTER_TEAM.upper() not in (away + home).upper():
                continue
                
            st.subheader(f"{away} @ {home}")
            away_sp = g.get('away_probable_pitcher', 'TBD')
            home_sp = g.get('home_probable_pitcher', 'TBD')
            st.caption(f"SP: {away_sp} vs {home_sp}")
            
            # Stronger pitcher impact
            base = 4.65
            def get_lambda(sp_name):
                if not sp_name or pitching_df.empty:
                    return base
                row = pitching_df[pitching_df['Name'].str.contains(sp_name.split()[-1], na=False, case=False)]
                if row.empty:
                    return base
                p_plus = float(row.get('Pitching+', 100).iloc[0])
                s_plus = float(row.get('Stuff+', 100).iloc[0])
                # Stronger weighting
                return base * (100 / p_plus)**0.6 * (100 / s_plus)**0.4
            
            away_lambda = get_lambda(away_sp)
            home_lambda = get_lambda(home_sp)
            
            projected = (away_lambda + home_lambda)
            prob_over = 1 - norm.cdf(8.5, projected, 3.0)
            edge = prob_over - 0.50
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Projected Total", f"{projected:.2f}")
            col2.metric("P(Over 8.5)", f"{prob_over:.1%}")
            col3.metric("Edge", f"{edge*100:+.1f}%", 
                       delta="✅ BET OVER" if edge > 0.05 else "❌ PASS")
            
            with st.expander("Pitching Details"):
                st.write(f"Away λ: {away_lambda:.2f} | Home λ: {home_lambda:.2f}")
            
            st.divider()

st.info("Projected totals should now vary based on starting pitchers.")