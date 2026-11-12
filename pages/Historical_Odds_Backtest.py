"""Date-safe historical model-vs-Bet365 backtest. No TheStatsAPI requests."""
from collections import defaultdict
from datetime import date
import math
import pandas as pd
import streamlit as st
from supabase import create_client
from starlizard_experimental_pricing import estimate, probabilities
from starlizard_backtest_opponents import OpponentHistory
from starlizard_venue_baselines import VenueBaseline
from starlizard_team_strength import SequentialTeamStrength
from starlizard_calibration import fit_calibration, apply_calibration, reliability, brier as calibration_brier

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
    venue_baselines = VenueBaseline()
    team_strength = SequentialTeamStrength()
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
            strength_rates = team_strength.predict(league, home, away)
            if len(hh) >= 5 and len(aa) >= 5:
                home_df = pd.DataFrame(hh)
                away_df = pd.DataFrame(aa)
                rates = estimate(home_df, away_df)
                if rates:
                    probs = probabilities(rates[0], rates[1])
                    adjusted_rates = estimate(pd.DataFrame(hh_adjusted), pd.DataFrame(aa_adjusted))
                    adjusted_probs = probabilities(adjusted_rates[0], adjusted_rates[1]) if adjusted_rates else None
                    home_prior, away_prior = venue_baselines.get(league)
                    # Apply separate, strictly historical priors to venue attack/defence inputs.
                    # Identical neutral priors reproduce the existing baseline when data are sparse.
                    def venue_rate(df_attack, df_defence, prior_value, strength=8):
                        a, d = df_attack["xGF"].mean(), df_defence["xGA"].mean()
                        na, nd = len(df_attack), len(df_defence)
                        return max(.15, min(4., ((a * na + prior_value * strength) / (na + strength)
                                                + (d * nd + prior_value * strength) / (nd + strength)) / 2))
                    venue_home_rate = venue_rate(pd.DataFrame(hh_adjusted), pd.DataFrame(aa_adjusted), home_prior)
                    venue_away_rate = venue_rate(pd.DataFrame(aa_adjusted), pd.DataFrame(hh_adjusted), away_prior)
                    venue_probs = probabilities(venue_home_rate, venue_away_rate)
                    strength_probs = probabilities(*strength_rates) if strength_rates else None
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
                                       "Favourite": fav, "Band": band, "Result": outcome, "Home goals": r["home_goals"], "Away goals": r["away_goals"],
                                       "Home model": probs["Home win"], "Draw model": probs["Draw"],
                                       "Away model": probs["Away win"],
                                       "Home adjusted": adjusted_probs["Home win"] if adjusted_probs else None,
                                       "Draw adjusted": adjusted_probs["Draw"] if adjusted_probs else None,
                                       "Away adjusted": adjusted_probs["Away win"] if adjusted_probs else None,
                                       "Home venue": venue_probs["Home win"], "Draw venue": venue_probs["Draw"],
                                       "Away venue": venue_probs["Away win"],
                                       "Home strength": strength_probs["Home win"] if strength_probs else None,
                                       "Draw strength": strength_probs["Draw"] if strength_probs else None,
                                       "Away strength": strength_probs["Away win"] if strength_probs else None,
                                       "Home expected goals": rates[0], "Away expected goals": rates[1],
                                       "Home adjusted xG": adjusted_rates[0] if adjusted_rates else None,
                                       "Away adjusted xG": adjusted_rates[1] if adjusted_rates else None,
                                       "Home venue xG": venue_home_rate, "Away venue xG": venue_away_rate,
                                       "Home strength xG": strength_rates[0] if strength_rates else None,
                                       "Away strength xG": strength_rates[1] if strength_rates else None,
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
            venue_baselines.record(league, hx, ax)
            team_strength.record(league, home, away, hx, ax)
    return pd.DataFrame(output)

sample = st.select_slider("Previous home/away fixtures per team", options=[5, 10, 15, 20, 25], value=20)
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
        train = results[results["Date"] < split].copy()
        fit = fit_calibration(train, "adjusted")
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
            venue_matrix = test[["Home venue", "Draw venue", "Away venue"]].to_numpy(dtype=float)
            venue_brier = calibration_brier(venue_matrix, y)
            st.metric("Venue-specific historical priors Brier score", f"{venue_brier:.4f}")
            st.caption(f"Versus adjusted xG: {venue_brier - adjusted_brier:+.4f}; negative is better. Priors use only earlier league and global matches.")
            strength_valid = test[["Home strength", "Draw strength", "Away strength"]].notna().all(axis=1)
            strength_count = int(strength_valid.sum())
            if strength_count:
                strength_frame = test.loc[strength_valid]
                strength_matrix = strength_frame[["Home strength", "Draw strength", "Away strength"]].to_numpy(dtype=float)
                strength_y = strength_frame["Result"].map({"Home win": 0, "Draw": 1, "Away win": 2}).to_numpy()
                strength_brier = calibration_brier(strength_matrix, strength_y)
                st.metric("Sequential team-strength Brier score", f"{strength_brier:.4f}")
                st.caption(f"{strength_count:,} held-out fixtures with prior league history. "
                           "EWMA attack/defence xG and league home advantage; "
                           "strictly earlier dates only. No market odds in predictions.")
                if strength_count != len(test):
                    st.caption("Not all fixtures qualify; compare models on the same eligible subset.")
                strength_market = market_matrix[strength_valid.to_numpy()]
                strength_venue = venue_matrix[strength_valid.to_numpy()]
                st.dataframe(pd.DataFrame([
                    {"Model": "Sequential team strength", "Brier": strength_brier},
                    {"Model": "Venue-specific xG (same fixtures)", "Brier": calibration_brier(strength_venue, strength_y)},
                    {"Model": "Bet365 no-vig (same fixtures)", "Brier": calibration_brier(strength_market, strength_y)}
                ]), hide_index=True, use_container_width=True)
            else:
                st.warning("No qualifying fixtures for team-strength comparison.")
            calibrated_matrix = apply_calibration(test, fit, "adjusted")
            calibrated_brier = calibration_brier(calibrated_matrix, y)
            st.metric("Train-calibrated opponent xG Brier score", f"{calibrated_brier:.4f}")
            st.caption(
                f"Calibration trained on {fit['train_size']:,} earlier matches only; "
                f"shrinkage to historical home/draw/away frequencies: {fit['alpha']:.0%}. "
                "No Bet365 prices or test results are inputs to calibration."
            )
            if calibrated_brier < adjusted_brier and calibrated_brier < market_brier:
                st.success("Calibrated xG beats both benchmarks on this held-out subset. Independent replication is still required.")
            elif calibrated_brier < adjusted_brier:
                st.info("Calibration improves adjusted xG on this held-out subset, but has not beaten Bet365.")
            else:
                st.warning("Calibration has not improved the adjusted model on this held-out subset.")
            with st.expander("Probability calibration by outcome and probability band"):
                st.caption("Positive error means the outcome happened more often than predicted.")
                st.dataframe(reliability(test, calibrated_matrix), hide_index=True, use_container_width=True)
            test["Home calibrated"] = calibrated_matrix[:, 0]
            test["Draw calibrated"] = calibrated_matrix[:, 1]
            test["Away calibrated"] = calibrated_matrix[:, 2]
            st.markdown("### 🔬 Pricing engine diagnostics")
            st.caption("All diagnostics below use held-out match outcomes. They describe errors; they do not tune the model.")
            diagnostic_rows = []
            for key, outcome in (("Home", "Home win"), ("Draw", "Draw"), ("Away", "Away win")):
                actual = float((test["Result"] == outcome).mean())
                diagnostic_rows.append({
                    "Outcome": outcome,
                    "Actual frequency": actual,
                    "Basic predicted": float(test[f"{key} model"].mean()),
                    "Adjusted predicted": float(test[f"{key} adjusted"].mean()),
                    "Bet365 no-vig predicted": float(market_matrix[:, ["Home", "Draw", "Away"].index(key)].mean()),
                    "Adjusted error (predicted − actual)": float(test[f"{key} adjusted"].mean() - actual),
                })
            st.dataframe(pd.DataFrame(diagnostic_rows).style.format({
                "Actual frequency": "{:.1%}", "Basic predicted": "{:.1%}",
                "Adjusted predicted": "{:.1%}", "Bet365 no-vig predicted": "{:.1%}",
                "Adjusted error (predicted − actual)": "{:+.1%}"
            }), hide_index=True, use_container_width=True)
            st.markdown("#### Error by favourite strength")
            strength_rows = []
            for group_name, group_frame in test.groupby("Band", observed=True):
                idx = test.index.get_indexer(group_frame.index)
                observed = y[idx]
                adjusted = adjusted_matrix[idx]
                baseline = market_matrix[idx]
                strength_rows.append({
                    "Favourite odds band": group_name, "Matches": len(group_frame),
                    "Adjusted Brier": calibration_brier(adjusted, observed),
                    "Bet365 Brier": calibration_brier(baseline, observed),
                    "Gap (model − market)": calibration_brier(adjusted, observed) - calibration_brier(baseline, observed),
                })
            st.dataframe(pd.DataFrame(strength_rows).sort_values("Favourite odds band"), hide_index=True, use_container_width=True)
            st.markdown("#### Goal expectation diagnostics")
            st.caption("Expected goals are estimated from prior xG. Actual goals are held-out outcomes, not inputs to predictions.")
            goal_rows = []
            for side in ("Home", "Away"):
                actual_goals = test[f"{side} goals"].astype(float)
                for model_name, expected_col in (("Basic", f"{side} expected goals"), ("Adjusted", f"{side} adjusted xG"), ("Venue-specific", f"{side} venue xG"), ("Team strength", f"{side} strength xG")):
                    expected_goals = test[expected_col].astype(float)
                    goal_rows.append({
                        "Side": side, "Model": model_name,
                        "Actual goals per match": float(actual_goals.mean()),
                        "Expected goals per match": float(expected_goals.mean()),
                        "Mean prediction bias": float((expected_goals - actual_goals).mean()),
                        "Mean absolute error": float((expected_goals - actual_goals).abs().mean()),
                    })
            st.dataframe(pd.DataFrame(goal_rows), hide_index=True, use_container_width=True)
            st.markdown("#### Prediction reliability")
            st.dataframe(reliability(test, adjusted_matrix), hide_index=True, use_container_width=True)
            st.download_button("Download full diagnostic predictions CSV", test.to_csv(index=False).encode("utf-8"),
                               file_name="starlizard_full_diagnostics.csv", mime="text/csv")
            strategy = st.radio("Model used for value selections", ["Basic xG", "Opponent-adjusted xG", "Venue-specific historical priors", "Sequential team strength", "Train-calibrated opponent xG"], horizontal=True)

            threshold = st.slider("Minimum estimated model edge", 0.00, 0.25, 0.05, 0.01)
            bets = []
            for _, r in test.iterrows():
                for name in outcome_names:
                    key = name.split()[0]
                    p = (r[f"{key} strength"] if strategy == "Sequential team strength"
                         else r[f"{key} venue"] if strategy == "Venue-specific historical priors"
                         else r[f"{key} calibrated"] if strategy == "Train-calibrated opponent xG"
                         else r[f"{key} adjusted"] if strategy == "Opponent-adjusted xG"
                         else r[f"{key} model"])
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
