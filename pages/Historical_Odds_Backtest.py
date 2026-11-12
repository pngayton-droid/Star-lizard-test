"""Date-safe historical model-vs-Bet365 backtest. No TheStatsAPI requests."""
from collections import defaultdict
from datetime import date
import math
import pandas as pd
import streamlit as st
from supabase import create_client
from starlizard_experimental_pricing import estimate, probabilities
from starlizard_backtest_opponents import OpponentHistory

st.set_page_config(page_title="PRO STARLIZARD | Odds Backtest", page_icon="📈", layout="wide")
st.title("📈 Historical odds backtest")
st.caption("Stored Bet365 last-seen prices against strictly prior-match xG predictions. No paid API requests.")
st.warning("Last-seen quotes are historical snapshots, not verified executable closing odds. This is a research backtest, not evidence of a tradable edge.")

@st.cache_data(ttl=3600, show_spinner="Reading stored historical prices...")
def load_rows():
    db = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SECRET_KEY"])
    rows = []
    for start in range(0, 20000, 1000):
        batch = (db.table("starlizard_backtest_1x2")
                 .select("match_id,match_date,competition_id,home_team,away_team,home_xg,away_xg,home_goals,away_goals,home_price,draw_price,away_price,home_open,away_open")
                 .order("match_date").order("match_id")
                 .range(start, start + 999).execute()).data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
    return rows

def valid(x):
    try:
        f = float(x)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None

def calculate(rows, n):
    # Match dates processed in groups: no fixture on a given date may train another on that date.
    history = defaultdict(list)
    opponents = OpponentHistory()
    output = []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for day, group in df.sort_values(["match_date", "match_id"]).groupby("match_date", sort=True):
        pending = []
        for r in group.to_dict("records"):
            league = r["competition_id"]
            home = r["home_team"]
            away = r["away_team"]
            hh = history[(league, home, "home")][-n:]
            hh_adjusted = history[(league, home, "home_adj")][-n:]
            aa = history[(league, away, "away")][-n:]
            aa_adjusted = history[(league, away, "away_adj")][-n:]
            if len(hh) >= 5 and len(aa) >= 5:
                home_df = pd.DataFrame(hh)
                away_df = pd.DataFrame(aa)
                rates = estimate(home_df, away_df)
                if rates:
                    probs = probabilities(rates[0], rates[1])
                    adjusted_rates = estimate(pd.DataFrame(hh_adjusted), pd.DataFrame(aa_adjusted))
                    adjusted_probs = probabilities(adjusted_rates[0], adjusted_rates[1]) if adjusted_rates else None
                    hp, dp, ap = (valid(r.get(k)) for k in ("home_price", "draw_price", "away_price"))
                    if all(p is not None and p > 1 for p in (hp, dp, ap)):
                        outcome = ("Home win" if r["home_goals"] > r["away_goals"] else
                                   "Away win" if r["home_goals"] < r["away_goals"] else "Draw")
                        market = {"Home win": hp, "Draw": dp, "Away win": ap}
                        fav = "Home" if hp < ap else "Away" if ap < hp else "Equal"
                        band = ("<1.50" if min(hp, ap) < 1.50 else
                                "1.50–1.99" if min(hp, ap) < 2 else
                                "2.00–2.99" if min(hp, ap) < 3 else "3.00+")
                        output.append({"Date": day, "League": league, "Match": f"{home} v {away}",
                                       "Favourite": fav, "Band": band, "Result": outcome,
                                       "Home model": probs["Home win"], "Draw model": probs["Draw"],
                                       "Away model": probs["Away win"],
                                       "Home adjusted": adjusted_probs["Home win"] if adjusted_probs else None,
                                       "Draw adjusted": adjusted_probs["Draw"] if adjusted_probs else None,
                                       "Away adjusted": adjusted_probs["Away win"] if adjusted_probs else None,
                                       "Home odds": hp, "Draw odds": dp, "Away odds": ap})
            hx, ax = valid(r.get("home_xg")), valid(r.get("away_xg"))
            if hx is not None and ax is not None and 0 <= hx < 12 and 0 <= ax < 12:
                home_attack, home_defence, home_ok = opponents.factors(league, away)
                away_attack, away_defence, away_ok = opponents.factors(league, home)
                pending.append((league, home, away, hx, ax,
                                hx * home_attack, ax * home_defence,
                                ax * away_attack, hx * away_defence))
        for league, home, away, hx, ax, hadj_for, hadj_against, aadj_for, aadj_against in pending:
            history[(league, home, "home")].append({"xGF": hx, "xGA": ax})
            history[(league, away, "away")].append({"xGF": ax, "xGA": hx})
            history[(league, home, "home_adj")].append({"xGF": hadj_for, "xGA": hadj_against})
            history[(league, away, "away_adj")].append({"xGF": aadj_for, "xGA": aadj_against})
            opponents.record(league, home, away, hx, ax)
    return pd.DataFrame(output)

sample = st.select_slider("Previous home/away fixtures per team", options=[5, 10, 15, 20, 25], value=10)
if st.button("Run historical backtest", type="primary"):
    try:
        rows = load_rows()
        st.session_state["odds_backtest_results"] = calculate(rows, sample)
        st.session_state["odds_backtest_sample"] = sample
        st.session_state["odds_backtest_source_count"] = len(rows)
    except Exception as exc:
        st.error(f"Backtest could not complete ({type(exc).__name__}): {exc}")

results = st.session_state.get("odds_backtest_results")
if results is not None:
    if st.session_state.get("odds_backtest_sample") != sample:
        st.info("Sample setting changed. Run the backtest again.")
    elif results.empty:
        st.warning("No qualifying historical fixtures. Check historical coverage.")
    else:
        st.caption(f"{len(results):,} eligible predictions from {st.session_state['odds_backtest_source_count']:,} stored match rows.")
        # Time split on match dates, not a random split; no tuning on the test segment.
        dates = sorted(results["Date"].unique())
        split = dates[int(len(dates) * 0.7)]
        st.caption(f"Chronological 70/30 split at {split}. No parameters are fitted on the test set; displayed evaluation is on the later dates only.")
        test = results[results["Date"] >= split].copy()
        league = st.selectbox("Competition", ["All"] + sorted(test["League"].unique().tolist()))
        if league != "All":
            test = test[test["League"] == league]
        band = st.selectbox("Pre-match favourite odds band", ["All", "<1.50", "1.50–1.99", "2.00–2.99", "3.00+"])
        if band != "All":
            test = test[test["Band"] == band]
        st.metric("Out-of-sample matches", f"{len(test):,}")
        if not test.empty:
            outcome_names = ["Home win", "Draw", "Away win"]
            model_matrix = test[[f"{k.split()[0]} model" for k in outcome_names]].to_numpy()
            y = test["Result"].map({name: i for i, name in enumerate(outcome_names)}).to_numpy()
            import numpy as np
            brier = float(np.mean(np.sum((model_matrix - np.eye(3)[y]) ** 2, axis=1)))
            st.metric("Multiclass Brier score (lower better)", f"{brier:.4f}")
            margin = sum(1 / test[f"{k.split()[0]} odds"] for k in outcome_names)
            market_matrix = np.column_stack([1 / test[f"{k.split()[0]} odds"] / margin for k in outcome_names])
            market_brier = float(np.mean(np.sum((market_matrix - np.eye(3)[y]) ** 2, axis=1)))
            st.metric("Bookmaker no-vig Brier score", f"{market_brier:.4f}")
            adjusted_matrix = test[["Home adjusted", "Draw adjusted", "Away adjusted"]].to_numpy(dtype=float)
            if np.isfinite(adjusted_matrix).all():
                adjusted_brier = float(np.mean(np.sum((adjusted_matrix - np.eye(3)[y]) ** 2, axis=1)))
                st.metric("Opponent-adjusted Brier score", f"{adjusted_brier:.4f}")
                st.caption(f"Against basic xG: {adjusted_brier - brier:+.4f} (negative means improvement).")
            else:
                st.info("Some adjusted probabilities unavailable for this subset.")
            strategy = st.radio("Model used for value selections", ["Basic xG", "Opponent-adjusted xG"], horizontal=True)

            threshold = st.slider("Minimum estimated model edge", 0.00, 0.25, 0.05, 0.01)
            bets = []
            for _, r in test.iterrows():
                for name in outcome_names:
                    key = name.split()[0]
                    p = r[f"{key} adjusted"] if strategy == "Opponent-adjusted xG" else r[f"{key} model"]
                    odds = r[f"{key} odds"]
                    if pd.isna(p):
                        continue
                    if p * odds - 1 >= threshold:
                        bets.append({"Date": r["Date"], "Match": r["Match"], "Favourite": r["Favourite"],
                                     "Band": r["Band"], "Selection": name, "Odds": odds,
                                     "Estimated EV": p * odds - 1,
                                     "Profit": odds - 1 if r["Result"] == name else -1})
            if bets:
                bets_df = pd.DataFrame(bets)
                st.metric("Selections (flat 1-unit stakes)", f"{len(bets_df):,}")
                st.metric("Historical flat-stake ROI", f"{bets_df['Profit'].mean():+.1%}")
                st.caption("Multiple selections can arise from one match. Selection threshold is exploratory and must not be tuned against this same test set.")
                st.dataframe(bets_df.tail(200), hide_index=True, use_container_width=True)
            else:
                st.info("No selections at the chosen edge threshold.")
            st.dataframe(test.tail(100), hide_index=True, use_container_width=True)
        st.caption("Opponent-adjusted version uses sequential league/team xG histories with the same shrinkage and factor limits as the existing opponent adjustment module. It is a causal historical approximation, not a fully calibrated model. Date-based splitting is used; do not optimise the edge threshold on the held-out period.")
