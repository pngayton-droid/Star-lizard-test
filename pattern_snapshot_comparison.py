"""Compare exploratory scan snapshots by stable segment identity."""
import pandas as pd

IDENTITY=["market","segment","value"]
METRICS=["train_n","train_rate","train_lift","holdout_n","holdout_rate","holdout_lift","fdr_q","screen_flag"]

def compare_scans(old, new):
    """Return segment-level changes; comparisons are descriptive, not validation."""
    if old is None: old=pd.DataFrame()
    if new is None: new=pd.DataFrame()
    if old.empty and new.empty:
        return pd.DataFrame()
    for frame in (old,new):
        if not frame.empty and (any(c not in frame for c in IDENTITY) or frame.duplicated(IDENTITY).any()):
            raise ValueError("Invalid or duplicate segment identity")
    left=old.reindex(columns=IDENTITY+METRICS).copy()
    right=new.reindex(columns=IDENTITY+METRICS).copy()
    result=left.merge(right,on=IDENTITY,how="outer",suffixes=("_previous","_current"),indicator=True,validate="one_to_one")
    for col in ["holdout_lift","holdout_rate","holdout_n","train_n","fdr_q"]:
        for suffix in ["_previous","_current"]:
            result[col+suffix]=pd.to_numeric(result[col+suffix],errors="coerce")
    result["lift_change_pp"]=((result.holdout_lift_current-result.holdout_lift_previous)*100).round(2)
    old_flag=result["screen_flag_previous"].fillna(False).astype(bool)
    new_flag=result["screen_flag_current"].fillna(False).astype(bool)
    def classify(row):
        if row["_merge"]=="left_only": return "No longer eligible"
        if row["_merge"]=="right_only": return "New segment"
        if bool(row["screen_flag_current"]) and not bool(row["screen_flag_previous"]): return "New flag"
        if bool(row["screen_flag_previous"]) and not bool(row["screen_flag_current"]): return "Flag lost"
        delta=row["lift_change_pp"]
        if pd.isna(delta): return "Unchanged / unknown"
        if abs(delta)<0.5: return "Stable"
        # Stronger/weaker means magnitude of holdout difference, not profitability.
        prev=row["holdout_lift_previous"]
        curr=row["holdout_lift_current"]
        if pd.isna(prev) or pd.isna(curr): return "Unchanged / unknown"
        return "Larger deviation" if abs(curr)>abs(prev) else "Smaller deviation"
    result["change_status"]=result.apply(classify,axis=1)
    return result.drop(columns=["_merge"]).sort_values(IDENTITY).reset_index(drop=True)
