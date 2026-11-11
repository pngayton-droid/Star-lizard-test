"""Shared read-only archive data client for PRO STARLIZARD.
Never embed credentials in the repository. Call from Streamlit server only.
"""
import os
import requests
import pandas as pd

class ArchiveDataError(RuntimeError):
    pass

def _credentials():
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SECRET_KEY")
    except Exception:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        raise ArchiveDataError("Missing private Supabase server credentials")
    return url.rstrip("/"), key

def fetch_view(view_name, columns="*", max_rows=20000):
    """Read a whitelisted view with stable keyset ordering; no writes."""
    allowed = {
        "archive_verified_match_research": "understat_id",
        "archive_first_second_half_goal": "understat_id",
    }
    if view_name not in allowed:
        raise ValueError("View not permitted")
    url, key = _credentials()
    headers = {"apikey": key, "Authorization": "Bearer " + key}
    rows = []
    last_id = None
    while len(rows) < max_rows:
        params = {"select": columns, "order": allowed[view_name] + ".asc",
                  "limit": min(1000, max_rows - len(rows))}
        if last_id is not None:
            params[allowed[view_name]] = "gt." + str(last_id)
        try:
            r = requests.get(url + "/rest/v1/" + view_name, headers=headers, params=params, timeout=45)
            r.raise_for_status()
            batch = r.json()
        except (requests.RequestException, ValueError) as exc:
            raise ArchiveDataError("Archive read failed") from exc
        if not batch:
            break
        rows.extend(batch)
        next_id = batch[-1][allowed[view_name]]
        if next_id == last_id:
            raise ArchiveDataError("Archive pagination did not advance")
        last_id = next_id
        if len(batch) < params["limit"]:
            break
    if len(rows) >= max_rows:
        raise ArchiveDataError("Safety limit reached; increase max_rows for complete analysis")
    return pd.DataFrame(rows)

def load_coverage():
    """Small aggregated view; one request avoids non-unique season-year pagination."""
    url, key = _credentials()
    try:
        r = requests.get(url + "/rest/v1/archive_data_coverage",
            headers={"apikey": key, "Authorization": "Bearer " + key},
            params={"select": "*", "limit": 1000}, timeout=45)
        r.raise_for_status()
        return pd.DataFrame(r.json())
    except (requests.RequestException, ValueError) as exc:
        raise ArchiveDataError("Archive coverage read failed") from exc

def load_research():
    """Return one row per verified cross-source match."""
    frame = fetch_view("archive_verified_match_research")
    if not frame.empty:
        frame = frame.drop_duplicates(subset=["understat_id"])
    return frame

def load_first_goals():
    """First recorded verified goal strictly after minute 45; timing provisional."""
    return fetch_view("archive_first_second_half_goal")
