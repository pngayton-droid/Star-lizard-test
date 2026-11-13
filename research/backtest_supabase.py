"""Export historical league data from Supabase and walk-forward test independently."""
import csv
import os
import tempfile
from supabase import create_client
from research.independent_pricing import load, walk_forward, probabilities, estimate
from research.opponent_strength import predict as strength_predict
import math

def main():
    db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
    columns="match_date,home_team,away_team,home_goals,away_goals,home_xg,away_xg,competition_id"
    rows=[];offset=0
    while True:
        batch=(db.table("historical_xg").select(columns)
               .order("match_date").range(offset,offset+999).execute().data or [])
        rows.extend(batch)
        if len(batch)<1000:break
        offset+=1000
    print(f"Fetched {len(rows)} records")
    with tempfile.NamedTemporaryFile(mode="w+",suffix=".csv",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=["date","home_team","away_team","home_goals","away_goals","home_xg","away_xg"])
        writer.writeheader()
        # Fit each league separately; no information from another competition enters the model.
        for league in sorted(set(r["competition_id"] for r in rows if r["competition_id"] is not None)):
            f.seek(0);f.truncate();writer.writeheader()
            for r in rows:
                if r["competition_id"]!=league:continue
                writer.writerow({"date":r["match_date"],**{k:r.get(k) for k in writer.fieldnames if k!="date"}})
            f.flush()
            matches=load(f.name)
            predictions=walk_forward(matches,minimum_train=300)
            if not predictions:
                print(f"{league}: insufficient history ({len(matches)} matches)")
                continue
            n=len(predictions)
            loss=sum(-math.log(max(1e-12,p[o])) for _,p,o,_,_ in predictions)/n
            brier=sum(sum((v-(k==o))**2 for k,v in enumerate(p)) for _,p,o,_,_ in predictions)/n
            home=sum(p[0] for _,p,_,_,_ in predictions)/n
            draw=sum(p[1] for _,p,_,_,_ in predictions)/n
            actual_draw=sum(o==1 for _,_,o,_,_ in predictions)/n
            # Same walk-forward predictions; assess low-score adjustment without peeking at future results.
            poisson_loss=sum(-math.log(max(1e-12,probabilities(lh,la,rho=0)[o])) for _,_,o,lh,la in predictions)/n
            actual_home=sum(o==0 for _,_,o,_,_ in predictions)/n
            actual_away=sum(o==2 for _,_,o,_,_ in predictions)/n
            # Paired holdout: identical fixtures and strictly earlier-day training.
            # Limit to the latest 60 evaluable fixtures per league for a fast research check.
            sample=predictions[-60:]
            baseline_total=adjusted_total=0.
            for m,p,o,_,_ in sample:
                prior_matches=[old for old in matches if old["date"]<m["date"]]
                sh,sa=strength_predict(prior_matches,m["home_team"],m["away_team"],m["date"])
                adjusted=probabilities(sh,sa)
                baseline_total-=math.log(max(1e-12,p[o]))
                adjusted_total-=math.log(max(1e-12,adjusted[o]))
            print(f"{league}: paired_n={len(sample)}, baseline_logloss={baseline_total/len(sample):.4f}, opponent_adjusted_logloss={adjusted_total/len(sample):.4f}")
            print(f"{league}: n={n}, logloss={loss:.4f}, poisson_logloss={poisson_loss:.4f}, brier={brier:.4f}, "
                  f"home_pred={home:.3f}, home_actual={actual_home:.3f}, draw_pred={draw:.3f}, draw_actual={actual_draw:.3f}, away_actual={actual_away:.3f}")
if __name__=="__main__":
    main()
