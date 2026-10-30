"""Independent pre-match Poisson baseline; experimental, not a validated betting edge."""
import argparse, math
from collections import defaultdict, deque
import pandas as pd
import numpy as np

MAX_GOALS=12

def probabilities(lh,la):
    h=np.array([math.exp(-lh)*lh**k/math.factorial(k) for k in range(MAX_GOALS+1)])
    a=np.array([math.exp(-la)*la**k/math.factorial(k) for k in range(MAX_GOALS+1)])
    h[-1]+=1-h.sum(); a[-1]+=1-a.sum()
    grid=np.outer(h,a)
    return {'home':float(np.tril(grid,-1).sum()),'draw':float(np.trace(grid)),'away':float(np.triu(grid,1).sum()),
            'over25':float(sum(grid[i,j] for i in range(MAX_GOALS+1) for j in range(MAX_GOALS+1) if i+j>=3)),
            'btts':float(grid[1:,1:].sum()), 'scores':grid}

def fair(p): return round(1/p,3) if p>0 else None

def load(path):
    df=pd.read_csv(path,low_memory=False,encoding='utf-8-sig')
    df.columns=[c.replace('ï»¿','').strip() for c in df.columns]
    if sum(c=='Div' for c in df.columns)>1:
        divisions=df.loc[:,df.columns=='Div'].bfill(axis=1).iloc[:,0]
        df=df.loc[:,df.columns!='Div'].copy()
        df.insert(0,'Div',divisions)
    df['date']=pd.to_datetime(df['Date'],dayfirst=True,errors='coerce')
    for c in ('FTHG','FTAG'):df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.dropna(subset=['date','Div','HomeTeam','AwayTeam','FTHG','FTAG'])
    df=df[df['date']<=pd.Timestamp('2026-10-30')]
    df=df[(df.FTHG>=0)&(df.FTAG>=0)].sort_values(['date','HomeTeam','AwayTeam']).reset_index(drop=True)
    return df

class Model:
    def __init__(self,n=25,prior=8):
        self.n=n;self.prior=prior;self.team=defaultdict(lambda:{'hgf':deque(maxlen=n),'hga':deque(maxlen=n),'agf':deque(maxlen=n),'aga':deque(maxlen=n)})
        self.league=defaultdict(lambda:{'hg':deque(maxlen=400),'ag':deque(maxlen=400)})
    def predict(self,league,home,away):
        l=self.league[league]; nh=len(l['hg'])
        if nh<60:return None
        hg=(sum(l['hg'])+1.45*40)/(nh+40);ag=(sum(l['ag'])+1.15*40)/(nh+40)
        t1=self.team[(league,home)];t2=self.team[(league,away)]
        if min(len(t1['hgf']),len(t2['aga']))<4:return None
        def shrunk(vals,mean):return (sum(vals)+self.prior*mean)/(len(vals)+self.prior)
        ha=shrunk(t1['hgf'],hg)/hg; ad=shrunk(t2['aga'],hg)/hg
        aa=shrunk(t2['agf'],ag)/ag; hd=shrunk(t1['hga'],ag)/ag
        lh=float(np.clip(hg*ha*ad,.15,4.5));la=float(np.clip(ag*aa*hd,.15,4.5))
        return lh,la,probabilities(lh,la)
    def update(self,league,home,away,gh,ga):
        t1=self.team[(league,home)];t2=self.team[(league,away)]
        t1['hgf'].append(gh);t1['hga'].append(ga);t2['agf'].append(ga);t2['aga'].append(gh)
        self.league[league]['hg'].append(gh);self.league[league]['ag'].append(ga)

def run(csv,out,cutoff):
    df=load(csv); model=Model();records=[];cut=pd.Timestamp(cutoff)
    # Group same-date matches to prevent same-day result leakage.
    for date,day in df.groupby('date',sort=True):
        pending=[]
        for _,r in day.iterrows():
            league=str(r['Div']);home=str(r.HomeTeam);away=str(r.AwayTeam);gh=int(r.FTHG);ga=int(r.FTAG)
            pred=model.predict(league,home,away)
            if date>=cut and pred is not None:
                lh,la,p=pred
                row={'date':date.date().isoformat(),'league':league,'home_team':home,'away_team':away,'home_goals':gh,'away_goals':ga,'lambda_home':lh,'lambda_away':la}
                for k in ('home','draw','away','over25','btts'):
                    row['p_'+k]=p[k];row['fair_'+k]=fair(p[k])
                row['outcome']=('home' if gh>ga else 'away' if ga>gh else 'draw')
                row['actual_over25']=int(gh+ga>=3);row['actual_btts']=int(gh>0 and ga>0)
                records.append(row)
            pending.append((league,home,away,gh,ga))
        for args in pending:model.update(*args)
    results=pd.DataFrame(records);results.to_csv(out,index=False)
    if len(results):
        bs=np.mean(sum((results['p_'+k]-(results.outcome==k).astype(int))**2 for k in ('home','draw','away')))
        ll=-np.log(np.maximum([results.iloc[i]['p_'+o] for i,o in enumerate(results.outcome)],1e-12)).mean()
        print(f'Out-of-sample predictions: {len(results)} | 1X2 multiclass Brier: {bs:.5f} | log loss: {ll:.5f}')
        print('Note: not compared with a market baseline; no profitability claim.')
    else:print('No eligible predictions; check cutoff/data coverage')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--csv',required=True);ap.add_argument('--out',default='predictions.csv');ap.add_argument('--cutoff',default='2024-08-01');args=ap.parse_args();run(args.csv,args.out,args.cutoff)
