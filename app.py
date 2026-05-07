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
st.caption("PDF Numeric Model + pybaseball + Weather + Live Books (DraftKings etc.)")

# === CONFIG ===
ODDS_API_KEY = st.secrets.get("ODDS_API_KEY", "YOUR_KEY_HERE")  # Add in Streamlit Secrets
GAME_DATE = st.date_input("Game Date", datetime.now().date())
FILTER_TEAM = st.text_input("Filter by team (optional)", "")
KALSHI_YES = st.slider("Kalshi YES Price (if applicable)", 0.0, 1.0, 0.50, 0.01)

def get_live_totals(home, away):
    if not ODDS_API_KEY or ODDS_API_KEY == "YOUR_KEY_HERE":
        return None
    try:
        url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "totals",
            "oddsFormat": "american",
            "date": GAME_DATE.isoformat()
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            for event in resp.json():
                if home in event.get('home_team', '') or away in event.get('away_team', ''):
                    for book in event.get('bookmakers', []):
                        if book['key'] in ['draftkings', 'fanduel', 'betmgm', 'caesars']:
                            for market in book['markets']:
                                if market['key'] == 'totals':
                                    for outcome in market['outcomes']:
                                        if outcome['name'] == 'Over':
                                            return {
                                                'book': book['title'],
                                                'total': outcome['point'],
                                                'price': outcome['price']
                                            }
        return None
    except:
        return None

if st.button("🚀 Run Full Expert Analysis", type="primary"):
    with st.spinner("Pulling pybaseball + Weather + Live Odds..."):
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
            away_sp = g.get('away_probable_pitcher')
            home_sp = g.get('home_probable_pitcher')
            
            # pybaseball + Numeric Model
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
            
            # Checklist Adjustments (Numeric Model)
            adj_total = 0.0
            if st.checkbox("Hitter-Friendly Park", value=False): adj_total += 0.10
            if st.checkbox("Warm Temp (>75°F)", value=False): adj_total += 0.07
            if st.checkbox("Strong Wind Out", value=False): adj_total += 0.15
            if st.checkbox("Mild Wind Out", value=False): adj_total += 0.08
            if st.checkbox("Both Lineups Full", value=True): adj_total += 0.10
            if st.checkbox("Strong Middle Order", value=False): adj_total += 0.10
            if st.checkbox("Both Bullpens Thin", value=False): adj_total += 0.15
            
            projected_total = 8.5 + adj_total + (away_lambda + home_lambda - 9.3)
            
            # Monte Carlo + Normal Prob
            sigma = 3.0
            prob_over = 1 - norm.cdf(8.5 + 0.5, projected_total, sigma)
            
            # Live Odds
            live_odds = get_live_totals(home, away)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("**Projected Total**", f"{projected_total:.2f}")
            col2.metric("Prob Over 8.5", f"{prob_over:.1%}")
            col3.metric("Edge vs Kalshi", f"{(prob_over - KALSHI_YES)*100:+.1f}%")
            
            if live_odds:
                st.success(f"**{live_odds['book']} Total:** {live_odds['total']} @ {live_odds['price']}")
            
            with st.expander("📋 Full PDF + Numeric Checklist"):
                st.write("Adjustments applied above")
            
            st.divider()

st.info("✅ DraftKings + other books via The Odds API. Add your key in Secrets for live odds.")