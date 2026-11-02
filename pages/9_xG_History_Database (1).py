"""Pro Star Lizard: portable historical xG store and incremental API updater."""
import os
import time
from datetime import date
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Star Lizard | xG History Store", layout="centered")
st.title("Pro Star Lizard | xG History Store")
st.caption("Reuse exported match data; fetch only missing matches. Download the updated CSV to keep it between app sessions.")
BASE = "https://api.thestatsapi.com/api"
COLS = ["Match ID", "Date", "Home", "Away", "Home xG", "Away xG"]
if "xg_store" not in st.session_state:
    st.session_state.xg_store = pd.DataFrame(columns=COLS)
if "xg_last_call" not in st.session_state:
    st.session_state.xg_last_call = 0.0

def normalise(frame):
    df = frame.copy()
    for col in COLS:
        if col not in df.columns:
            df[col] = ""
    for col in ("Home xG", "Away xG"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["Date", "Home", "Away", "Home xG", "Away xG"])
    df = df[(df["Home xG"] >= 0) & (df["Away xG"] >= 0)]
    df["Match ID"] = df["Match ID"].fillna("").astype(str)
    # Prefer the API's match ID; fall back to date + home + away for old exports.
    df["_key"] = df.apply(
        lambda r: r["Match ID"] if r["Match ID"].startswith("mt_")
        else "|".join([str(r["Date"]), str(r["Home"]).strip().lower(), str(r["Away"]).strip().lower()]), axis=1
    )
    return df.drop_duplicates("_key", keep="last").drop(columns="_key")[COLS].sort_values("Date", ascending=False)

def merge(frame):
    st.session_state.xg_store = normalise(pd.concat([st.session_state.xg_store, frame], ignore_index=True))

st.subheader("1. Load an existing history")
uploaded = st.file_uploader("Upload previous xG CSV (including the 96-match export)", type="csv")
if uploaded is not None:
    try:
        incoming = pd.read_csv(uploaded)
        if not {"Date", "Home", "Away", "Home xG", "Away xG"}.issubset(incoming.columns):
            st.error("CSV needs Date, Home, Away, Home xG and Away xG columns.")
        elif st.button("Merge uploaded history"):
            before = len(st.session_state.xg_store)
            merge(incoming)
            st.success(f"History updated: {before} → {len(st.session_state.xg_store)} unique records.")
    except Exception as exc:
        st.error(f"Cannot read CSV: {exc}")

df = st.session_state.xg_store
st.metric("Stored matches in this session", len(df))
if len(df):
    st.write(f"{len(set(df['Home']).union(set(df['Away'])))} teams represented")
    st.dataframe(df.head(12), use_container_width=True, hide_index=True)

st.subheader("2. Fetch new matches only")
st.caption("This initial updater refreshes Newcastle and Everton. Additional leagues can be added after the storage workflow is tested.")
key = st.secrets.get("STATS_API_KEY", os.environ.get("STATS_API_KEY", ""))
home_id = st.text_input("First team ID", "tm_7938")
away_id = st.text_input("Second team ID", "tm_8091")
count = st.slider("Latest matches to check per team", 5, 30, 20)
cutoff = st.date_input("Completed by", value=date.today())
if st.button("Refresh missing xG records", type="primary"):
    if not key:
        st.error("STATS_API_KEY missing from Streamlit secrets.")
        st.stop()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {key}", "Accept": "application/json"})
    def api(path, params=None):
        for attempt in range(4):
            delay = 1.8 - (time.monotonic() - st.session_state.xg_last_call)
            if delay > 0:
                time.sleep(delay)
            st.session_state.xg_last_call = time.monotonic()
            try:
                resp = session.get(BASE + path, params=params, timeout=35)
            except requests.RequestException as exc:
                if attempt == 3:
                    return None, str(exc)
                time.sleep(5 * (attempt + 1))
                continue
            if resp.status_code == 200:
                try:
                    return resp.json().get("data"), None
                except ValueError:
                    return None, "Invalid API response"
            if resp.status_code == 429 and attempt < 3:
                try:
                    retry_after = float(resp.headers.get("Retry-After", 0))
                except ValueError:
                    retry_after = 0
                wait = min(120, max(retry_after, [15, 30, 60][attempt]))
                st.info(f"API rate limit; waiting {wait:.0f} seconds.")
                time.sleep(wait)
                continue
            return None, f"HTTP {resp.status_code}: {resp.text[:120]}"
        return None, "Retries exhausted"
    all_matches = {}
    for tid in (home_id.strip(), away_id.strip()):
        data, err = api("/football/matches", {
            "team_id": tid, "status": "finished", "date_to": cutoff.isoformat(),
            "per_page": count, "page": 1, "sort": "-utc_date",
        })
        if err:
            st.warning(f"{tid}: {err}")
        elif isinstance(data, list):
            all_matches.update({m["id"]: m for m in data if isinstance(m, dict) and m.get("id")})
    existing_ids = set(st.session_state.xg_store["Match ID"].astype(str))
    existing_fallback = set(zip(
        st.session_state.xg_store["Date"].astype(str),
        st.session_state.xg_store["Home"].astype(str).str.lower(),
        st.session_state.xg_store["Away"].astype(str).str.lower(),
    ))
    pending = []
    for mid, match in all_matches.items():
        h, a = match.get("home_team") or {}, match.get("away_team") or {}
        d = str(match.get("utc_date", ""))[:10]
        fallback = (d, str(h.get("name", "")).lower(), str(a.get("name", "")).lower())
        if mid not in existing_ids and fallback not in existing_fallback:
            pending.append((mid, match))
    st.write(f"Discovered {len(all_matches)} unique matches; {len(pending)} need detailed xG requests.")
    new_rows, errors = [], []
    progress = st.progress(0)
    for i, (mid, match) in enumerate(pending):
        data, err = api(f"/football/matches/{mid}/stats")
        if err:
            errors.append(f"{mid}: {err}")
        elif isinstance(data, dict):
            def xg(side):
                for section in data.values():
                    if isinstance(section, dict):
                        val = section.get("expected_goals")
                        if isinstance(val, dict):
                            all_period = val.get("all")
                            if isinstance(all_period, dict):
                                try:
                                    return float(all_period[side])
                                except (KeyError, TypeError, ValueError):
                                    pass
                return None
            hx, ax = xg("home"), xg("away")
            if hx is not None and ax is not None:
                new_rows.append({
                    "Match ID": mid, "Date": str(match.get("utc_date", ""))[:10],
                    "Home": (match.get("home_team") or {}).get("name", ""),
                    "Away": (match.get("away_team") or {}).get("name", ""),
                    "Home xG": hx, "Away xG": ax,
                })
            else:
                errors.append(f"{mid}: xG missing")
        progress.progress((i+1)/len(pending))
    if new_rows:
        merge(pd.DataFrame(new_rows))
    st.success(f"Added {len(new_rows)} xG records. Total: {len(st.session_state.xg_store)}.")
    if errors:
        st.warning(f"{len(errors)} records could not be added. Retry later; missing values were not treated as zero.")
        with st.expander("Details"):
            st.write(errors[:30])

st.subheader("3. Save your history")
st.warning("Streamlit session storage is temporary. Download the CSV after refreshing and upload it next time. This is not yet a permanent cloud database.")
st.download_button(
    "Download updated xG history CSV",
    st.session_state.xg_store.to_csv(index=False).encode("utf-8"),
    file_name="starlizard_xg_history_master.csv",
    mime="text/csv",
    disabled=st.session_state.xg_store.empty,
)
st.caption("Next stage: permanent database plus time-split backtesting and league-wide scheduled updates.")
