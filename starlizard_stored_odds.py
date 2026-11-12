"""Stored historical bookmaker prices. Supabase only; no paid odds API calls."""
import pandas as pd
import streamlit as st

BOOKS = ("Bet365", "Betfair Exchange", "Pinnacle", "BetMGM UK", "Paddy Power")
MARKETS = {
    "Match result": ("match_odds", ("home", "draw", "away")),
    "Both teams score": ("btts", ("yes", "no")),
    "Draw no bet": ("draw_no_bet", ("home", "away")),
    "Double chance": ("double_chance", ()),
    "Total goals": ("total_goals", ()),
    "Match corners": ("match_corners", ()),
    "Total cards": ("total_cards", ()),
    "Asian handicap": ("asian_handicap", ()),
    "First-half result": ("first_half_result", ()),
}

def _flatten(node, prefix=()):
    if not isinstance(node, dict):
        return []
    if "last_seen" in node or "opening" in node:
        return [{
            "Selection": " / ".join(map(str, prefix)),
            "Opening": node.get("opening"),
            "Last seen": node.get("last_seen"),
        }]
    out = []
    for k, v in node.items():
        out.extend(_flatten(v, prefix + (k,)))
    return out

@st.cache_data(ttl=600, show_spinner=False)
def stored_odds(match_id):
    from supabase import create_client
    db = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SECRET_KEY"])
    response = (db.table("historical_match_odds")
                .select("fetch_status,bookmaker_names,odds_payload")
                .eq("match_id", str(match_id)).limit(1).execute())
    return (response.data or [None])[0]

def render_historical_odds(matches):
    """Show stored bookmaker prices alongside a selected historical fixture."""
    options = {}
    for r in matches:
        mid = r.get("match_id")
        if mid:
            label = f"{r.get('match_date', '')} · {r.get('home_team', '?')} v {r.get('away_team', '?')} [{mid}]"
            options[label] = str(mid)
    st.subheader("📊 Historical bookmaker odds")
    st.caption("Read directly from Supabase — no TheStatsAPI requests. Historical reference prices, NOT current betting offers.")
    if not options:
        st.info("No historical fixtures available.")
        return
    choice = st.selectbox("Historical match", list(options), key="stored_odds_match")
    if not choice:
        return
    try:
        record = stored_odds(options[choice])
    except Exception as exc:
        st.warning(f"Stored odds unavailable ({type(exc).__name__}).")
        return
    if not record or record.get("fetch_status") != "collected":
        st.info("No collected bookmaker odds for this match.")
        return
    payload = record.get("odds_payload") or {}
    data = payload.get("data") or {}
    books = data.get("bookmakers") or []
    names = [b.get("bookmaker") for b in books if isinstance(b, dict) and b.get("bookmaker")]
    if not names:
        st.info("No bookmaker selections were returned.")
        return
    preferred = sorted(names, key=lambda n: (BOOKS.index(n) if n in BOOKS else len(BOOKS), n))
    bookmaker = st.selectbox("Bookmaker", preferred, key="stored_odds_book")
    entry = next((b for b in books if b.get("bookmaker") == bookmaker), {})
    markets = entry.get("markets") or {}
    available = [m for m, (key, _) in MARKETS.items() if key in markets]
    if not available:
        st.info("No recognised odds markets in this record.")
        return
    market = st.selectbox("Market", available, key="stored_odds_market")
    key, _ = MARKETS[market]
    rows = _flatten(markets[key])
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No selections found.")
    if key == "match_odds":
        last = markets[key]
        def price(side):
            try:
                v = float(last.get(side, {}).get("opening") or last.get(side, {}).get("last_seen"))
                return v if v > 1 else None
            except (ValueError, TypeError):
                return None
        home, away = price("home"), price("away")
        if home and away:
            fav = "Home favourite" if home < away else "Away favourite" if away < home else "Level prices"
            st.info(f"Pre-match market classification: {fav} · home {home:.2f} / away {away:.2f}. Uses opening quotes when available, otherwise last-seen historical prices; latter are not necessarily true pre-match opening prices.")
    st.caption("Opening = earliest recorded quote where available. Last seen = latest recorded quote; intended as a pre-kickoff reference, but exact snapshot time is not verified. Missing prices remain blank.")
