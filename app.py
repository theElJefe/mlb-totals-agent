import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import statsapi
import pybaseball as pyb

st.set_page_config(page_title="MLB Totals Agent", layout="centered")

st.title("🧠 MLB Totals Agent 2026")
st.caption("Expert Checklist + pybaseball + Poisson")

GAME_DATE = st.date_input("Game Date", datetime.now().date())
FILTER_TEAM = st.text_input("Filter by team (optional)", "")

if st.button("🚀 Run Full Analysis", type="primary"):
    with st.spinner("Fetching data..."):
        games = statsapi.schedule(date=GAME_DATE.isoformat())
        
        # Safe pybaseball call with fallback
        try:
            pitching_df = pyb.pitching_stats(GAME_DATE.year, qual=10)
            st.success("✅ FanGraphs data loaded")
        except Exception as e:
            pitching_df = pd.DataFrame()
            st.warning("⚠️ FanGraphs data unavailable (future date or temp issue). Using defaults.")
        
        for g in games:
            away = g['away_name']
            home = g['home_name']
            
            if FILTER_TEAM and FILTER_TEAM.upper() not in (away + home).upper():
                continue
                
            st.subheader(f"{away} @ {home}")
            away_sp = g.get('away_probable_pitcher')
            home_sp = g.get('home_probable_pitcher')
            st.write(f"**SP:** {away_sp} vs {home_sp}")
            
            # Safe lambda calculation
            base = 4.65
            def get_lambda(sp_name):
                if not sp_name or pitching_df.empty:
                    return base
                row = pitching_df[pitching_df['Name'].str.contains(sp_name.split()[-1], na=False, case=False)]
                if row.empty:
                    return base
                pitching_plus = float(row['Pitching+'].iloc[0]) if 'Pitching+' in row.columns else 100
                stuff_plus = float(row['Stuff+'].iloc[0]) if 'Stuff+' in row.columns else 100
                return base * (100 / pitching_plus) * (100 / stuff_plus)**0.3
            
            away_lambda = get_lambda(away_sp)
            home_lambda = get_lambda(home_sp)
            
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
            
            with st.expander("📋 PDF Checklist Summary"):
                st.write("• Pitching+ / Stuff+ : Loaded via pybaseball")
                st.write("• Other factors (Wind, Bullpen, ABS, etc.): Coming in next upgrade")
            
            st.divider()

st.info("App running with error handling. Use real past dates (e.g. 2025) for best data.")