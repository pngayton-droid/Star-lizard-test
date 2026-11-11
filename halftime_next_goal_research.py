"""Read-only next-goal research with explicit three-way outcomes.

2026-11-11 audit: all 1,337 NULL outcomes among trailing-at-HT matches
correspond to no second-half goals; counts reconcile when penalty_scored,
goal and own_goal are included. First-scorer attribution agrees for all 5,611 labelled cases; the separate
17-suspect VAR audit and prospective validation remain outstanding.
"""
import requests
import streamlit as st
from archive_data_engine import _credentials

@st.cache_data(ttl=300,max_entries=1,show_spinner=False)
def next_goal_rows():
    url,key=_credentials()
    headers={"apikey":key,"Authorization":"Bearer "+key}
    result=[]
    for offset in range(0,12000,1000):
        params={"select":"match_id,match_date,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg,trailing_side,trailing_team_scored_first",
                "trailing_side":"not.is.null",
                "order":"match_date.asc,match_id.asc","limit":1000,"offset":offset}
        response=requests.get(url+"/rest/v1/starlizard_next_goal_research",
            headers=headers,params=params,timeout=30)
        response.raise_for_status()
        batch=response.json()
        result.extend(batch)
        if len(batch)<1000:return result
    raise RuntimeError("Labelled next-goal query exceeded safe pagination cap")

def trailing_first_summary(rows,min_xg=0.2,deficit=1,side="both"):
    if side not in ("both","home","away"):raise ValueError("Invalid side")
    if deficit<1 or min_xg<0:raise ValueError("Invalid filter")
    selected=[]
    for row in rows:
        if row.get("trailing_team_scored_first") is None:continue
        trailing=row.get("trailing_side")
        if trailing not in ("home","away") or (side!="both" and side!=trailing):continue
        try:
            h,a=int(row["home_ht_goals"]),int(row["away_ht_goals"])
            if abs(h-a)!=deficit or (h>a and trailing!="away") or (a>h and trailing!="home"):continue
            xg=float(row["home_ht_xg"] if trailing=="home" else row["away_ht_xg"])
        except (TypeError,ValueError,KeyError):continue
        if xg>=min_xg:selected.append(row)
    n=len(selected)
    wins=sum(row["trailing_team_scored_first"] is True for row in selected)
    return {"n":n,"hits":wins,"rate":wins/n if n else None}

def trailing_three_way_summary(rows,min_xg=0.2,deficit=1,side="both"):
    """Observed trailing-first / leader-first / no-goal, never an odds quote."""
    if side not in ("both","home","away"):raise ValueError("Invalid side")
    if deficit<1 or min_xg<0:raise ValueError("Invalid filter")
    selected=[]
    for row in rows:
        trailing=row.get("trailing_side")
        if trailing not in ("home","away") or (side!="both" and side!=trailing):continue
        try:
            h,a=int(row["home_ht_goals"]),int(row["away_ht_goals"])
            if abs(h-a)!=deficit or (h>a and trailing!="away") or (a>h and trailing!="home"):continue
            xg=float(row["home_ht_xg"] if trailing=="home" else row["away_ht_xg"])
        except (TypeError,ValueError,KeyError):continue
        if xg>=min_xg:selected.append(row)
    n=len(selected)
    trailing_first=sum(r["trailing_team_scored_first"] is True for r in selected)
    leader_first=sum(r["trailing_team_scored_first"] is False for r in selected)
    no_goal=n-trailing_first-leader_first
    return {"n":n,"trailing_first":trailing_first,"leader_first":leader_first,
            "no_goal":no_goal,"trailing_rate":trailing_first/n if n else None,
            "leader_rate":leader_first/n if n else None,
            "no_goal_rate":no_goal/n if n else None}

# Backwards-compatible alias for existing imports.
labelled_next_goal_rows=next_goal_rows

def trailing_three_way_holdout(rows,min_xg=0.2,deficit=1,side="both",train_fraction=0.7):
    """Chronological descriptive split; no future match enters training.

    Splits distinct match dates, keeping all matches on one date together.
    This is a stability check, not a prospective betting backtest.
    """
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between zero and one")
    if side not in ("both","home","away") or deficit<1 or min_xg<0:
        raise ValueError("Invalid research filter")
    dated=[r for r in rows if r.get("match_date") and r.get("trailing_side") in ("home","away")]
    # Select the cutoff from the actual research population, not unrelated
    # matches or a different xG/deficit cohort.
    qualifying=[]
    for r in dated:
        if side!="both" and r["trailing_side"]!=side:continue
        try:
            h,a=int(r["home_ht_goals"]),int(r["away_ht_goals"])
            xg=float(r["home_ht_xg"] if r["trailing_side"]=="home" else r["away_ht_xg"])
        except (KeyError,TypeError,ValueError):continue
        if abs(h-a)==deficit and xg>=min_xg and ((h<a and r["trailing_side"]=="home") or (a<h and r["trailing_side"]=="away")):
            qualifying.append(r)
    dates=sorted({str(r["match_date"])[:10] for r in qualifying})
    if len(dates)<2:
        return {"status":"Insufficient distinct match dates","train":None,"later":None}
    cutoff_index=max(1,min(len(dates)-1,int(len(dates)*train_fraction)))
    cutoff=dates[cutoff_index]
    train=[r for r in dated if str(r["match_date"])[:10]<cutoff]
    later=[r for r in dated if str(r["match_date"])[:10]>=cutoff]
    return {"status":"ok","cutoff":cutoff,
            "train":trailing_three_way_summary(train,min_xg,deficit,side),
            "later":trailing_three_way_summary(later,min_xg,deficit,side)}

def three_way_holdout_scores(rows,min_xg=0.2,deficit=1,side="both",train_fraction=0.7,smoothing=1.0):
    """Evaluate frozen earlier-period three-way rates on later match outcomes.

    Uses additive smoothing and returns multiclass Brier score and log loss.
    These scores describe historical calibration; they do not imply betting ROI.
    """
    import math
    if smoothing<=0:raise ValueError("smoothing must be positive")
    split=trailing_three_way_holdout(rows,min_xg,deficit,side,train_fraction)
    if split["status"]!="ok":return {"status":split["status"]}
    train,later=split["train"],split["later"]
    if train["n"]<30 or later["n"]<30:
        return {"status":"Insufficient qualifying matches","train_n":train["n"],"later_n":later["n"]}
    keys=("trailing_first","leader_first","no_goal")
    probabilities={k:(train[k]+smoothing)/(train["n"]+3*smoothing) for k in keys}
    later_rates={k:later[k]/later["n"] for k in keys}
    brier=sum(later_rates[k]*sum((probabilities[j]-(1.0 if j==k else 0.0))**2 for j in keys) for k in keys)
    logloss=-sum(later_rates[k]*math.log(probabilities[k]) for k in keys)
    # Compare against an honest unconditional three-way prior trained only
    # on earlier dates, not on the later evaluation period.
    train_all=trailing_three_way_summary(
        [r for r in rows if r.get("match_date") and str(r["match_date"])[:10]<split["cutoff"]],
        min_xg=0.0,deficit=deficit,side="both")
    if train_all["n"]<30:
        return {"status":"Insufficient baseline matches","train_n":train["n"],"later_n":later["n"]}
    baseline_probs={k:(train_all[k]+smoothing)/(train_all["n"]+3*smoothing) for k in keys}
    baseline_brier=sum(later_rates[k]*sum((baseline_probs[j]-(1.0 if j==k else 0.0))**2 for j in keys) for k in keys)
    baseline_logloss=-sum(later_rates[k]*math.log(baseline_probs[k]) for k in keys)
    return {"status":"ok","cutoff":split["cutoff"],"train_n":train["n"],
            "later_n":later["n"],"earlier_probabilities":probabilities,
            "later_rates":later_rates,"brier":brier,"log_loss":logloss,
            "baseline_n":train_all["n"],"baseline_brier":baseline_brier,
            "baseline_log_loss":baseline_logloss,
            "brier_improvement":baseline_brier-brier,
            "log_loss_improvement":baseline_logloss-logloss}
