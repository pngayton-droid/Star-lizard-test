"""Export historical league data from Supabase and walk-forward test independently."""
import csv
import os
import tempfile
from supabase import create_client
from research.independent_pricing import load, walk_forward
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
        for league in sorted(set(r["competition_id"] for r in rows)):
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
            print(f"{league}: n={n}, logloss={loss:.4f}, brier={brier:.4f}, "
                  f"home_pred={home:.3f}, draw_pred={draw:.3f}, draw_actual={actual_draw:.3f}")
if __name__=="__main__":
    main()
