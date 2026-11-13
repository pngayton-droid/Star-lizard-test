import os,math
from datetime import date
import numpy as np
from supabase import create_client
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
rows=[]
for start in range(0,5000,500):
 b=db.table("historical_xg").select("match_date,home_team,away_team,home_xg,away_xg").eq("competition_id","comp_8814").lt("match_date","2026-11-20").not_.is_("home_xg","null").not_.is_("away_xg","null").order("match_date",desc=True).range(start,start+499).execute().data or []
 rows+=b
 if len(b)<500:break
teams=sorted(set(r["home_team"] for r in rows)|set(r["away_team"] for r in rows))
idx={t:i for i,t in enumerate(teams)};n=len(teams)
X=[];Y=[];W=[]
for r in rows:
 age=max(0,(date(2026,11,20)-date.fromisoformat(r["match_date"][:10])).days)
 w=2**(-age/180)
 h,a=idx[r["home_team"]],idx[r["away_team"]]
 for att,defn,home,xg in [(h,a,1,r["home_xg"]),(a,h,0,r["away_xg"])]:
  v=np.zeros(2+2*n);v[0]=1;v[1]=home;v[2+att]=1;v[2+n+defn]=-1
  X.append(v);Y.append(math.log(max(0,float(xg))+.15));W.append(w)
X=np.asarray(X);Y=np.asarray(Y);sw=np.sqrt(np.asarray(W));ridge=10
P=np.eye(X.shape[1])*ridge;P[0,0]=.001;P[1,1]=ridge*2
beta=np.linalg.solve((X*sw[:,None]).T@(X*sw[:,None])+P,(X*sw[:,None]).T@(Y*sw))
def price(home,away):
 h,a=idx[home],idx[away]
 x=max(.15,math.exp(beta[0]+beta[1]+beta[2+h]-beta[2+n+a])-.15)
 y=max(.15,math.exp(beta[0]+beta[2+a]-beta[2+n+h])-.15)
 p=[0.,0.,0.];rho=-.08
 for i in range(13):
  for j in range(13):
   tau=1.
   if i==j==0:tau=1-x*y*rho
   elif i==0 and j==1:tau=1+x*rho
   elif i==1 and j==0:tau=1+y*rho
   elif i==j==1:tau=1-rho
   z=max(0,tau)*math.exp(-x-y)*x**i*y**j/math.factorial(i)/math.factorial(j)
   p[0 if i>j else 1 if i==j else 2]+=z
 p=[v/sum(p) for v in p]
 return x,y,*[1/v for v in p]
fixtures=[("Athletic Club","Espanyol"),("Deportivo Alavés","Deportivo La Coruña"),("Rayo Vallecano","Valencia"),("Sevilla","Real Betis"),("Real Madrid","Celta Vigo"),("Barcelona","Villarreal"),("Racing de Santander","Real Sociedad"),("Osasuna","Málaga"),("Getafe","Atlético Madrid"),("Levante UD","Elche")]
print("TRAINING_MATCHES",len(rows),"TEAMS",n,flush=True)
for h,a in fixtures:
 print(h,"v",a, " | ".join(f"{v:.3f}" for v in price(h,a)),flush=True)
