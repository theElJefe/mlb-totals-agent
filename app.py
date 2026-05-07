"""Streamlit app to display MLB games within the next 72 hours.

This script leverages Major League Baseball's public StatsAPI to pull the
up‑to‑date schedule and basic game information for the upcoming 72 hours
(three days) relative to when the app is run.  It then converts the
scheduled start times into Eastern Time (ET) and constructs a simple
table of each matchup.  The table includes placeholder columns for
market and betting information so that users following the MLB Totals
Pre‑Bet Checklist can record their own numbers.  Actual closing lines
and no‑vig fair prices are not computed here – those values depend on
the sportsbook and the user's own modelling – but the columns are
present to maintain the structure shown in the example.

The resulting dataframe is displayed using Streamlit.  Users can save
the table to a CSV file for record keeping or further analysis.  If
Streamlit is not available in the runtime environment, running this
script directly will simply print the dataframe to the console.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from typing import Dict, List

try:
    # zoneinfo is available in Python ≥3.9 and provides IANA time zone
    # definitions out of the box.  If you are running this code on an
    # older Python release, install the backports.zoneinfo package.
    from zoneinfo import ZoneInfo  # type: ignore[import]
except ImportError:
    ZoneInfo = None  # type: ignore

import requests
import pandas as pd

def fetch_team_abbreviation(team_id: int, cache: Dict[int, str]) -> str:
    """Retrieve the official team abbreviation for a given team ID.

    The MLB StatsAPI returns team objects with only an ID and full name.
    To construct a concise matchup string (e.g. "TEX @ NYY"), we need
    each club's three‑letter abbreviation.  This helper queries the
    `teams/{team_id}` endpoint once per team and caches the result to
    minimise network overhead.

    Args:
        team_id: The numeric team identifier provided by the schedule.
        cache: A dictionary used to store previously fetched abbreviations.

    Returns:
        A string abbreviation such as "LAD" or "BOS".
    """
    if team_id in cache:
        return cache[team_id]
    try:
        response = requests.get(f"https://statsapi.mlb.com/api/v1/teams/{team_id}")
        response.raise_for_status()
        data = response.json()
        abbr = data["teams"][0]["abbreviation"]
    except Exception:
        # Fall back to an empty string if the API call fails.  An empty
        # abbreviation will result in the full team name being used
        # instead of a code in the final table.
        abbr = ""
    cache[team_id] = abbr
    return abbr


def collect_games_within_hours(next_hours: int = 72) -> pd.DataFrame:
    """Collect MLB games scheduled within a rolling window of hours.

    This function queries the MLB StatsAPI for each date in the window
    starting from the current date/time until `next_hours` ahead.  It
    constructs a dataframe summarising the matchup, start time in ET,
    current game status, scores (if available) and a set of blank
    columns corresponding to the user's betting record.  Games that
    begin outside of the specified window are skipped.

    Args:
        next_hours: Number of hours ahead of the current time to
            include.  Defaults to 72 (three days).

    Returns:
        A pandas DataFrame where each row corresponds to a scheduled
        MLB game within the window.
    """
    # Determine the time range for our query in UTC.  The StatsAPI
    # returns times in UTC, so we keep everything in UTC until we
    # convert to Eastern Time at the end.
    now_utc = datetime.utcnow()
    end_utc = now_utc + timedelta(hours=next_hours)

    # Convert the UTC times to date boundaries.  We'll query the
    # schedule endpoint once per calendar date and then filter games by
    # their precise start time.
    start_date = now_utc.date()
    end_date = end_utc.date()

    # Prepare a cache for team abbreviations to reduce API calls.
    abbr_cache: Dict[int, str] = {}

    # Collect rows in a list; we'll convert to a DataFrame at the end.
    rows: List[Dict[str, object]] = []

    # Iterate over each date in the inclusive range.  pandas.date_range
    # makes it easy to generate a sequence of dates.  We convert to
    # Python datetime.date objects for formatting.
    for date in pd.date_range(start=start_date, end=end_date, freq="D"):
        iso_date = date.date().isoformat()
        url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={iso_date}"
        try:
            schedule_resp = requests.get(url)
            schedule_resp.raise_for_status()
            schedule_data = schedule_resp.json()
        except Exception:
            # Skip this date if the API call fails.
            continue
        # The API returns a list of dates; sometimes it can be empty if
        # there are no games scheduled (e.g., off days).  Continue if so.
        if not schedule_data.get("dates"):
            continue
        for game in schedule_data["dates"][0].get("games", []):
            # Parse the game's scheduled start time.  The StatsAPI
            # includes the `gameDate` field as an ISO 8601 string with
            # trailing 'Z' to denote UTC.  Replace 'Z' with '+00:00'
            # for compatibility with datetime.fromisoformat.
            game_datetime_utc = datetime.fromisoformat(
                game["gameDate"].replace("Z", "+00:00")
            )
            # Only consider games that start within our window.
            if game_datetime_utc < now_utc or game_datetime_utc > end_utc:
                continue

            # Convert the start time to Eastern Time.  Use zoneinfo when
            # available; otherwise default to UTC to avoid crashing on
            # systems lacking timezone support.
            if ZoneInfo is not None:
                et = game_datetime_utc.astimezone(ZoneInfo("America/New_York"))
            else:
                et = game_datetime_utc

            # Fetch team abbreviations.
            home = game["teams"]["home"]["team"]
            away = game["teams"]["away"]["team"]
            home_abbr = fetch_team_abbreviation(home["id"], abbr_cache) or home["name"]
            away_abbr = fetch_team_abbreviation(away["id"], abbr_cache) or away["name"]

            # Game status and scores (may be None if game hasn't started).
            status = game["status"].get("detailedState", "")
            away_score = game["teams"]["away"].get("score")
            home_score = game["teams"]["home"].get("score")

            # Construct a row matching the requested template.  Betting
            # fields are left blank for the user to fill in manually.
            row = {
                "Date": et.date().isoformat(),
                "Game": f"{away_abbr} @ {home_abbr} {et.strftime('%I:%M %p').lstrip('0')} ET",
                "Market": "",
                "Stake": "",
                "Price": "",
                "No‑vig fair": "",
                "Pinnacle close": "",
                "CLV": "",
                "Notes": "",
                "Status": status,
                "Away Score": away_score,
                "Home Score": home_score,
            }
            rows.append(row)

    # Convert list of dicts into a DataFrame.  The ordering of columns
    # here controls their display order in Streamlit.  Include the
    # betting columns first to mirror the sample, followed by status and
    # scores for reference.
    columns = [
        "Date",
        "Game",
        "Market",
        "Stake",
        "Price",
        "No‑vig fair",
        "Pinnacle close",
        "CLV",
        "Notes",
        "Status",
        "Away Score",
        "Home Score",
    ]
    return pd.DataFrame(rows, columns=columns)


def main() -> None:
    """Entry point for the Streamlit application and CLI fallback."""
    df = collect_games_within_hours(72)
    try:
        import streamlit as st  # lazy import inside try/catch
        st.title("MLB Games Within the Next 72 Hours")
        st.write(
            "This table lists Major League Baseball games scheduled within the next "
            "72 hours from the moment you run the app.  The start times are shown "
            "in Eastern Time (ET).  Use the blank columns to record your market "
            "selection, stake, price, no‑vig fair value, Pinnacle close, CLV and "
            "any notes from your pre‑bet checklist.  Scores will populate as games "
            "finish."
        )
        # Display the dataframe.  Allow horizontal scrolling for readability.
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
        )
        # Offer a download button for the user to save the dataframe.
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download table as CSV",
            data=csv,
            file_name="mlb_games_72h.csv",
            mime="text/csv",
        )
    except ImportError:
        # When Streamlit is not installed, simply print the table.
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()