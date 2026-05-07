import os
import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import statsapi
import streamlit as st
import pytz
from pybaseball import batting_stats, pitching_stats, schedule_and_record

st.set_page_config(page_title="MLB Totals Bet Tracker", page_icon="⚾", layout="wide")

ET = pytz.timezone("America/New_York")
DATA_FILE = "bet_log.json"
SPORT_KEY = "baseball_mlb"

st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 2rem;}
.bet-card {border:1px solid #2d3748;border-radius:12px;padding:14px;margin-bottom:12px;background:#111827;}
.small-label {font-size:.78rem;color:#9ca3af;text-transform:uppercase;letter-spacing:.03em;}
.big-value {font-size:1rem;color:#f3f4f6;font-weight:600;}
.muted {color:#cbd5e1;}
.good {color:#34d399;font-weight:700;}
.bad {color:#f87171;font-weight:700;}
.warn {color:#fbbf24;font-weight:700;}
.tag {display:inline-block;padding:3px 8px;border-radius:999px;font-size:.78rem;font-weight:700;}
.tag-over {background:#064e3b;color:#d1fae5;}
.tag-under {background:#7f1d1d;color:#fee2e2;}
.tag-pass {background:#374151;color:#e5e7eb;}
</style>
""", unsafe_allow_html=True)

TEAM_TO_ABBR = {
    "Arizona Diamondbacks":"ARI","Atlanta Braves":"ATL","Baltimore Orioles":"BAL",
    "Boston Red Sox":"BOS","Chicago Cubs":"CHC","Chicago White Sox":"CWS",
    "Cincinnati Reds":"CIN","Cleveland Guardians":"CLE","Colorado Rockies":"COL",
    "Detroit Tigers":"DET","Houston Astros":"HOU","Kansas City Royals":"KC",
    "Los Angeles Angels":"LAA","Los Angeles Dodgers":"LAD","Miami Marlins":"MIA",
    "Milwaukee Brewers":"MIL","Minnesota Twins":"MIN","New York Mets":"NYM",
    "New York Yankees":"NYY","Athletics":"ATH","Oakland Athletics":"OAK",
    "Philadelphia Phillies":"PHI","Pittsburgh Pirates":"PIT","San Diego Padres":"SD",
    "San Francisco Giants":"SF","Seattle Mariners":"SEA","St. Louis Cardinals":"STL",
    "Tampa Bay Rays":"TB","Texas Rangers":"TEX","Toronto Blue Jays":"TOR",
    "Washington Nationals":"WSH"
}
BALLPARK_COORDS = {
    "Arizona Diamondbacks": (33.4453, -112.0667), "Atlanta Braves": (33.8908, -84.4677),
    "Baltimore Orioles": (39.2839, -76.6217), "Boston Red Sox": (42.3467, -71.0972),
    "Chicago Cubs": (41.9484, -87.6553), "Chicago White Sox": (41.8300, -87.6339),
    "Cincinnati Reds": (39.0974, -84.5061), "Cleveland Guardians": (41.4962, -81.6852),
    "Colorado Rockies": (39.7559, -104.9942), "Detroit Tigers": (42.3390, -83.0485),
    "Houston Astros": (29.7573, -95.3555), "Kansas City Royals": (39.0517, -94.4803),
    "Los Angeles Angels": (33.8003, -117.8827), "Los Angeles Dodgers": (34.0739, -118.2400),
    "Miami Marlins": (25.7781, -80.2197), "Milwaukee Brewers": (43.0280, -87.9712),
    "Minnesota Twins": (44.9817, -93.2776), "New York Mets": (40.7571, -73.8458),
    "New York Yankees": (40.8296, -73.9262), "Athletics": (38.2000, -121.4900),
    "Oakland Athletics": (37.7516, -122.2005), "Philadelphia Phillies": (39.9061, -75.1665),
    "Pittsburgh Pirates": (40.4469, -80.0057), "San Diego Padres": (32.7073, -117.1566),
    "San Francisco Giants": (37.7786, -122.3893), "Seattle Mariners": (47.5914, -122.3325),
    "St. Louis Cardinals": (38.6226, -90.1928), "Tampa Bay Rays": (27.7682, -82.6534),
    "Texas Rangers": (32.7513, -97.0825), "Toronto Blue Jays": (43.6414, -79.3894),
    "Washington Nationals": (38.8730, -77.0074)
}


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def team_abbr(name):
    return TEAM_TO_ABBR.get(name, (name or "")[:3].upper())


def american_to_decimal(odds):
    if odds is None:
        return None
    return 1 + (odds / 100 if odds > 0 else 100 / abs(odds))


def implied_prob_from_american(odds):
    if odds is None:
        return None
    return (100 / (odds + 100)) if odds > 0 else (abs(odds) / (abs(odds) + 100))


def no_vig_fair_probs(over_price, under_price):
    po = implied_prob_from_american(over_price)
    pu = implied_prob_from_american(under_price)
    if po is None or pu is None or po + pu == 0:
        return None, None
    total = po + pu
    return po / total, pu / total


def prob_to_american(p):
    if p is None or p <= 0 or p >= 1:
        return None
    return int(round(-(p / (1 - p)) * 100)) if p >= 0.5 else int(round(((1 - p) / p) * 100))


def quarter_kelly(bankroll, fair_prob, offered_odds):
    dec = american_to_decimal(offered_odds)
    if not dec or fair_prob is None:
        return 0.0
    b = dec - 1
    p = fair_prob
    q = 1 - p
    k = ((b * p) - q) / b if b > 0 else 0
    return max(0.0, bankroll * (k / 4))


@st.cache_data(ttl=900)
def fetch_schedule_72h():
    now_et = datetime.now(ET)
    end_et = now_et + timedelta(hours=72)
    games = statsapi.schedule(start_date=now_et.strftime("%m/%d/%Y"), end_date=end_et.strftime("%m/%d/%Y"))
    rows = []
    for g in games:
        if g.get("game_type") != "R":
            continue
        try:
            dt = datetime.fromisoformat(g["game_datetime"].replace("Z", "+00:00")).astimezone(ET)
        except Exception:
            continue
        if dt < now_et:
            continue
        rows.append({
            "game_id": g.get("game_id"),
            "home_team": g.get("home_name"),
            "away_team": g.get("away_name"),
            "home_pitcher": g.get("home_probable_pitcher") or "TBD",
            "away_pitcher": g.get("away_probable_pitcher") or "TBD",
            "game_datetime_et": dt,
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def fetch_odds(api_key, regions="us", markets="totals", bookmakers=""):
    if not api_key:
        return pd.DataFrame()
    params = {"apiKey": api_key, "regions": regions, "markets": markets, "oddsFormat": "american"}
    if bookmakers.strip():
        params["bookmakers"] = bookmakers.strip()
    r = requests.get(f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds", params=params, timeout=20)
    r.raise_for_status()
    rows = []
    for event in r.json():
        best_over = best_under = None
        total_point = None
        pinnacle_over = pinnacle_under = None
        for bk in event.get("bookmakers", []):
            for market in bk.get("markets", []):
                if market.get("key") != "totals":
                    continue
                over = next((o for o in market.get("outcomes", []) if o.get("name") == "Over"), None)
                under = next((o for o in market.get("outcomes", []) if o.get("name") == "Under"), None)
                if not over or not under:
                    continue
                if total_point is None:
                    total_point = over.get("point")
                if best_over is None or (over.get("price") or -9999) > (best_over.get("price") or -9999):
                    best_over = {"price": over.get("price"), "book": bk.get("title")}
                if best_under is None or (under.get("price") or -9999) > (best_under.get("price") or -9999):
                    best_under = {"price": under.get("price"), "book": bk.get("title")}
                if bk.get("key") == "pinnacle":
                    pinnacle_over = over.get("price")
                    pinnacle_under = under.get("price")
        rows.append({
            "event_id": event.get("id"),
            "home_team": event.get("home_team"),
            "away_team": event.get("away_team"),
            "commence_time_et": datetime.fromisoformat(event.get("commence_time").replace("Z", "+00:00")).astimezone(ET) if event.get("commence_time") else None,
            "market_total": total_point,
            "over_price": best_over.get("price") if best_over else None,
            "under_price": best_under.get("price") if best_under else None,
            "best_over_book": best_over.get("book") if best_over else None,
            "best_under_book": best_under.get("book") if best_under else None,
            "pinnacle_over": pinnacle_over,
            "pinnacle_under": pinnacle_under,
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=1800)
def fetch_weather_for_games(home_teams):
    rows = []
    for team in home_teams:
        coords = BALLPARK_COORDS.get(team)
        if not coords:
            rows.append({"home_team": team, "temp_f": None, "wind_mph": None, "wind_dir": None, "weather_note": "Ballpark coords unavailable"})
            continue
        lat, lon = coords
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m,windspeed_10m,winddirection_10m,precipitation_probability",
                "temperature_unit": "fahrenheit",
                "windspeed_unit": "mph",
                "forecast_days": 3,
                "timezone": "America/New_York",
            }
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            js = r.json()
            hourly = js.get("hourly", {})
            if not hourly or not hourly.get("time"):
                rows.append({"home_team": team, "temp_f": None, "wind_mph": None, "wind_dir": None, "weather_note": "No weather data"})
                continue
            rows.append({
                "home_team": team,
                "temp_f": hourly.get("temperature_2m", [None])[0],
                "wind_mph": hourly.get("windspeed_10m", [None])[0],
                "wind_dir": hourly.get("winddirection_10m", [None])[0],
                "precip_pct": hourly.get("precipitation_probability", [None])[0],
                "weather_note": "Auto-pulled via Open-Meteo"
            })
        except Exception:
            rows.append({"home_team": team, "temp_f": None, "wind_mph": None, "wind_dir": None, "precip_pct": None, "weather_note": "Weather pull failed"})
    return pd.DataFrame(rows)


@st.cache_data(ttl=14400)
def fetch_team_metrics(season):
    bat = batting_stats(season, season)
    pit = pitching_stats(season, season)
    bat = bat[[c for c in ["Team", "Name", "PA", "wRC+", "K%", "BB%", "ISO", "wOBA"] if c in bat.columns]]
    pit = pit[[c for c in ["Team", "Name", "IP", "ERA", "xERA", "FIP", "WHIP", "K/9", "BB/9"] if c in pit.columns]]
    team_bat = bat.groupby("Team", as_index=False).agg({"PA":"sum", "wRC+":"mean", "K%":"mean", "BB%":"mean", "ISO":"mean", "wOBA":"mean"}) if not bat.empty else pd.DataFrame()
    team_pit = pit.groupby("Team", as_index=False).agg({"IP":"sum", "ERA":"mean", "xERA":"mean", "FIP":"mean", "WHIP":"mean", "K/9":"mean", "BB/9":"mean"}) if not pit.empty else pd.DataFrame()
    return team_bat, team_pit


@st.cache_data(ttl=7200)
def bullpen_fatigue_score(team_abbr_code, season):
    try:
        df = schedule_and_record(season, team_abbr_code)
        if df is None or df.empty or "Date" not in df.columns:
            return None, "No schedule data"
        recent = df.tail(5).copy()
        games_3 = min(len(recent.tail(3)), 3)
        games_5 = min(len(recent), 5)
        score = round((games_3 * 0.6 + games_5 * 0.2), 2)
        note = f"Proxy fatigue from last {games_5} team games"
        return score, note
    except Exception:
        return None, "Bullpen proxy unavailable"


@st.cache_data(ttl=43200)
def fetch_umpire_placeholder():
    return {"source": "UmpScorecards not directly integrated", "note": "Auto-pull pending custom scraper/API"}


def merge_all(schedule_df, odds_df, weather_df):
    if schedule_df.empty and odds_df.empty:
        return pd.DataFrame()
    merged = schedule_df.merge(odds_df, on=["home_team", "away_team"], how="left") if not odds_df.empty else schedule_df.copy()
    merged = merged.merge(weather_df, on="home_team", how="left") if not weather_df.empty else merged
    merged["display_time"] = merged["game_datetime_et"].combine_first(merged.get("commence_time_et"))
    return merged.sort_values("display_time")


def recommendation_from_market(over_price, under_price):
    fair_over, fair_under = no_vig_fair_probs(over_price, under_price)
    if fair_over is None or fair_under is None:
        return "PASS"
    if fair_under > 0.515:
        return "UNDER"
    if fair_over > 0.515:
        return "OVER"
    return "PASS"


def weather_edge(temp_f, wind_mph):
    adj = 0.0
    notes = []
    if temp_f is not None:
        if temp_f >= 88:
            adj += 0.15
            notes.append("Hot weather over lean")
        elif temp_f <= 50:
            adj -= 0.15
            notes.append("Cold weather under lean")
    if wind_mph is not None:
        if wind_mph >= 12:
            notes.append("Meaningful wind; direction review still manual")
    return adj, "; ".join(notes) if notes else "Weather neutral"


st.title("⚾ MLB Totals Bet Tracker")
st.caption("Auto-pulls schedule, totals odds, weather, team metrics, bullpen proxy, and stores close/CLV fields.")

with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Odds API Key", type="password")
    regions = st.text_input("Odds regions", value="us")
    bookmakers = st.text_input("Bookmakers (optional)", value="")
    bankroll = st.number_input("Bankroll ($)", min_value=100.0, value=6500.0, step=100.0)
    season = st.number_input("Season", min_value=2024, max_value=2026, value=2026, step=1)
    st.caption("For Streamlit Cloud, move the API key into Secrets later.")

bet_log = load_data()

schedule_df = fetch_schedule_72h()
odds_df = fetch_odds(api_key, regions=regions, bookmakers=bookmakers) if api_key else pd.DataFrame()
weather_df = fetch_weather_for_games(schedule_df["home_team"].dropna().unique().tolist()) if not schedule_df.empty else pd.DataFrame()
team_bat, team_pit = fetch_team_metrics(int(season))
ump_info = fetch_umpire_placeholder()
merged = merge_all(schedule_df, odds_df, weather_df)

if merged.empty:
    st.warning("No games loaded yet. Add your Odds API key and confirm games are on the board.")
else:
    st.subheader("Upcoming games")
    for _, row in merged.iterrows():
        dt = row.get("display_time")
        date_txt = dt.strftime("%Y-%m-%d") if pd.notna(dt) else datetime.now(ET).strftime("%Y-%m-%d")
        time_txt = dt.strftime("%-I:%M %p ET") if pd.notna(dt) else "TBD"
        away = row.get("away_team")
        home = row.get("home_team")
        away_abbr = team_abbr(away)
        home_abbr = team_abbr(home)
        game_key = f"{date_txt}_{away}_{home}"

        over_price = row.get("over_price")
        under_price = row.get("under_price")
        market_total = row.get("market_total")
        signal = recommendation_from_market(over_price, under_price)
        fair_over, fair_under = no_vig_fair_probs(over_price, under_price)
        chosen_prob = fair_under if signal == "UNDER" else fair_over if signal == "OVER" else None
        chosen_price = under_price if signal == "UNDER" else over_price if signal == "OVER" else None
        stake = quarter_kelly(bankroll, chosen_prob, chosen_price) if chosen_price else 0.0

        home_bat = team_bat[team_bat["Team"] == home_abbr] if not team_bat.empty else pd.DataFrame()
        away_bat = team_bat[team_bat["Team"] == away_abbr] if not team_bat.empty else pd.DataFrame()
        home_pit = team_pit[team_pit["Team"] == home_abbr] if not team_pit.empty else pd.DataFrame()
        away_pit = team_pit[team_pit["Team"] == away_abbr] if not team_pit.empty else pd.DataFrame()

        home_wrc = float(home_bat["wRC+"].iloc[0]) if not home_bat.empty and pd.notna(home_bat["wRC+"].iloc[0]) else None
        away_wrc = float(away_bat["wRC+"].iloc[0]) if not away_bat.empty and pd.notna(away_bat["wRC+"].iloc[0]) else None
        home_xera = float(home_pit["xERA"].iloc[0]) if not home_pit.empty and pd.notna(home_pit["xERA"].iloc[0]) else None
        away_xera = float(away_pit["xERA"].iloc[0]) if not away_pit.empty and pd.notna(away_pit["xERA"].iloc[0]) else None

        home_pen_score, home_pen_note = bullpen_fatigue_score(home_abbr, int(season))
        away_pen_score, away_pen_note = bullpen_fatigue_score(away_abbr, int(season))
        wx_adj, wx_note = weather_edge(row.get("temp_f"), row.get("wind_mph"))

        saved = bet_log.get(game_key, {})
        pinnacle_close = saved.get("pinnacle_close", row.get("pinnacle_under") if signal == "UNDER" else row.get("pinnacle_over"))
        clv = saved.get("clv", "TBD")
        tag_class = "tag-under" if signal == "UNDER" else "tag-over" if signal == "OVER" else "tag-pass"

        st.markdown(f"""
<div class="bet-card">
  <div class="small-label">Date</div><div class="big-value">{date_txt}</div>
  <div class="small-label" style="margin-top:8px;">Game</div><div class="big-value">{away_abbr} @ {home_abbr} {time_txt}</div>
  <div class="small-label" style="margin-top:8px;">Probable Pitchers</div><div class="muted">{row.get('away_pitcher','TBD')} vs {row.get('home_pitcher','TBD')}</div>
  <div class="small-label" style="margin-top:8px;">Market / Signal</div><div class="big-value">Total {market_total if pd.notna(market_total) else '[TBD]'} · <span class="tag {tag_class}">{signal}</span></div>
</div>
""", unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Over", over_price if pd.notna(over_price) else "TBD")
        c2.metric("Under", under_price if pd.notna(under_price) else "TBD")
        c3.metric("Pinnacle ref", pinnacle_close if pinnacle_close is not None else "TBD")
        c4.metric("Stake", f"${stake:,.2f}")

        c5, c6, c7 = st.columns(3)
        c5.metric("Weather", f"{row.get('temp_f')}°F / {row.get('wind_mph')} mph" if pd.notna(row.get('temp_f')) else "TBD")
        c6.metric("Home wRC+", f"{home_wrc:.1f}" if home_wrc is not None else "TBD")
        c7.metric("Away wRC+", f"{away_wrc:.1f}" if away_wrc is not None else "TBD")

        st.caption(f"Weather note: {wx_note} | Umpire: {ump_info['note']} | Home bullpen: {home_pen_note} | Away bullpen: {away_pen_note}")
        st.caption(f"Pitching xERA — {away_abbr}: {away_xera if away_xera is not None else 'TBD'} | {home_abbr}: {home_xera if home_xera is not None else 'TBD'}")

        with st.expander(f"Output card — {away_abbr} @ {home_abbr}"):
            manual_market = st.text_input("Market", value=saved.get("market", f"Total {market_total}" if pd.notna(market_total) else "Total [TBD]"), key=f"market_{game_key}")
            notes_default = saved.get("notes", wx_note)
            notes = st.text_area("Notes", value=notes_default, key=f"notes_{game_key}", height=120)
            pin_input = st.text_input("Pinnacle close", value=str(saved.get("pinnacle_close", pinnacle_close if pinnacle_close is not None else "TBD (post-close)")), key=f"pin_{game_key}")

            auto_clv = "TBD"
            try:
                open_price = float(chosen_price) if chosen_price is not None else None
                close_price = float(pin_input)
                if open_price is not None:
                    auto_clv = round(close_price - open_price, 2)
            except Exception:
                auto_clv = saved.get("clv", "TBD")

            output_card = f"""Date: {date_txt}
Game: {away_abbr} @ {home_abbr} {time_txt}
Market: {manual_market}
Stake: ${stake:,.2f} (quarter-Kelly)
Price: {chosen_price if chosen_price is not None else 'TBD'}
No-vig fair: Over {prob_to_american(fair_over) if fair_over is not None else 'TBD'} / Under {prob_to_american(fair_under) if fair_under is not None else 'TBD'}
Pinnacle close: {pin_input}
CLV: {auto_clv}
Weather: {row.get('temp_f') if pd.notna(row.get('temp_f')) else 'TBD'}F, wind {row.get('wind_mph') if pd.notna(row.get('wind_mph')) else 'TBD'} mph
Umpire: {ump_info['note']}
Bullpen fatigue: {away_abbr} {away_pen_score if away_pen_score is not None else 'TBD'} / {home_abbr} {home_pen_score if home_pen_score is not None else 'TBD'}
Lineup quality: {away_abbr} wRC+ {away_wrc if away_wrc is not None else 'TBD'} / {home_abbr} wRC+ {home_wrc if home_wrc is not None else 'TBD'}
Notes: {notes if notes else '—'}"""
            st.code(output_card, language="text")

            if st.button("Save", key=f"save_{game_key}"):
                bet_log[game_key] = {
                    "date": date_txt,
                    "game": f"{away_abbr} @ {home_abbr} {time_txt}",
                    "market": manual_market,
                    "price": chosen_price if chosen_price is not None else "TBD",
                    "fair": f"Over {prob_to_american(fair_over) if fair_over is not None else 'TBD'} / Under {prob_to_american(fair_under) if fair_under is not None else 'TBD'}",
                    "pinnacle_close": pin_input,
                    "clv": auto_clv,
                    "notes": notes,
                    "signal": signal,
                    "stake": f"${stake:,.2f}",
                }
                save_data(bet_log)
                st.success("Saved")

    if bet_log:
        st.subheader("Saved bet cards")
        for _, v in bet_log.items():
            sig = v.get("signal", "PASS")
            tag_class = "tag-under" if sig == "UNDER" else "tag-over" if sig == "OVER" else "tag-pass"
            st.markdown(f"""
<div class="bet-card">
  <div class="small-label">Game</div><div class="big-value">{v.get('date','')} — {v.get('game','')}</div>
  <div class="small-label" style="margin-top:8px;">Signal</div><div class="big-value"><span class="tag {tag_class}">{sig}</span></div>
  <div class="small-label" style="margin-top:8px;">Market / Stake</div><div class="muted">{v.get('market','')} | {v.get('stake','')}</div>
  <div class="small-label" style="margin-top:8px;">Close / CLV</div><div class="muted">{v.get('pinnacle_close','')} | {v.get('clv','')}</div>
  <div class="small-label" style="margin-top:8px;">Notes</div><div class="muted">{v.get('notes','')}</div>
</div>
""", unsafe_allow_html=True)
