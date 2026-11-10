
"""PRO STARLIZARD V5.4 — halftime-first, read-only, team-strength experiment."""
import os
import math
from collections import defaultdict, deque
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st
from supabase import create_client
from starlizard_pricing_engine import load_historical_xg, fit_ratings, price_fixture, asian_market
from starlizard_unified_pricing import (load_table, build_matches, comparable_matches,
    price_market, home_scores_second_half, away_scores_second_half,
    home_wins_second_half, over_goals, market_over)

st.set_page_config(page_title="PRO STARLIZARD", page_icon="🦎", layout="wide", initial_sidebar_state="collapsed")
st.markdown('<style>.block-container{max-width:1050px;padding:.8rem .6rem 2rem}h1{font-size:1.5rem!important}h2,h3{font-size:1.1rem!important}</style>', unsafe_allow_html=True)
LEAGUES = {"comp_3039":"Premier League", "comp_8321":"Championship", "comp_4643":"Bundesliga", "comp_0256":"Ligue 1", "comp_8531":"Belgian Pro League"}
OUTCOMES = ("home", "away", "none")

def league_label(cid):
    return f"{LEAGUES[cid]} ({cid})" if cid in LEAGUES else str(cid)

@st.cache_resource
def database():
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SECRET_KEY")
    if not url or not key:
        raise RuntimeError("Supabase credentials missing")
    return create_client(url, key)

@st.cache_resource(ttl=3600, show_spinner=False)
def historical_data():
    db = database()
    xg = load_table(db, "historical_xg", "match_id,match_date,competition_id,home_team,away_team,home_ht_goals,away_ht_goals,home_goals,away_goals,home_ht_xg,away_ht_xg,home_xg,away_xg")
    events = load_table(db, "historical_match_events", "match_id,stats_data,timeline_data")
    matches, rejected = build_matches(xg, events)
    meta = {str(r['match_id']):r for r in xg if r.get('match_id')}
    timelines = {str(r['match_id']):r.get('timeline_data') for r in events if r.get('match_id')}
    return matches, rejected, meta, timelines

@st.cache_data(ttl=3600)
def catalogue():
    rows = load_table(database(), "historical_xg", "match_id,competition_id,home_team,away_team")
    leagues = defaultdict(set)
    for r in rows:
        cid, h, a = str(r.get('competition_id') or ''), str(r.get('home_team') or ''), str(r.get('away_team') or '')
        if cid and h and a and h != a:
            leagues[cid].update((h,a))
    return {cid:sorted(teams) for cid,teams in sorted(leagues.items())}

@st.cache_resource(ttl=3600)
def ratings_for(cid, cutoff, half_life, ridge):
    return fit_ratings(load_historical_xg(database(),cid,cutoff),cid,cutoff,half_life_days=half_life,ridge=ridge,minimum_matches=60)

def nonnegative_int(value):
    if isinstance(value,bool): return None
    try:
        n=float(value)
        return int(n) if math.isfinite(n) and n>=0 and n.is_integer() else None
    except (TypeError,ValueError): return None

def parse_goal_sequence(match, meta, timeline):
    if not isinstance(timeline,dict) or timeline.get('coverage')!='full': return None
    events=timeline.get('events')
    if not isinstance(events,list) or not all(isinstance(e,dict) for e in events): return None
    home,away=str(meta.get('home_team') or ''),str(meta.get('away_team') or '')
    if not home or not away or home==away: return None
    counts={'first_half':[0,0],'second_half':[0,0]}
    second=[]
    for e in events:
        kind=e.get('type')
        if kind not in ('goal','penalty_scored','own_goal'): continue
        period=e.get('period')
        team=e.get('team')
        name=team.get('name') if isinstance(team,dict) else None
        if period not in counts or name not in (home,away): return None
        side=0 if name==home else 1
        if kind=='own_goal': side=1-side
        minute=nonnegative_int(e.get('minute'))
        extra=nonnegative_int(e.get('extra_time') if e.get('extra_time') is not None else 0)
        if minute is None or extra is None: return None
        counts[period][side]+=1
        if period=='second_half': second.append((minute,extra,side))
    if counts['first_half'] != [match.ht_home,match.ht_away]: return None
    if counts['second_half'] != [match.ft_home-match.ht_home,match.ft_away-match.ht_away]: return None
    if not second: return 'none'
    second.sort()
    if any(e[:2]==second[0][:2] and e[2]!=second[0][2] for e in second[1:]): return None
    return 'home' if second[0][2]==0 else 'away'

@st.cache_resource(ttl=3600,show_spinner=False)
def verified_history():
    matches,_,meta,timelines=historical_data()
    records=[]
    for m in matches:
        mid=str(m.match_id); r=meta.get(mid,{})
        outcome=parse_goal_sequence(m,r,timelines.get(mid))
        if outcome not in OUTCOMES: continue
        when=pd.to_datetime(r.get('match_date'),errors='coerce',utc=True)
        if pd.isna(when): continue
        try: hx,ax=float(m.ht_xg_home),float(m.ht_xg_away)
        except (TypeError,ValueError): continue
        if not all(math.isfinite(x) and x>=0 for x in (hx,ax)): continue
        records.append(dict(date=when,match_id=mid,competition_id=str(r.get('competition_id') or ''),home=str(r.get('home_team') or ''),away=str(r.get('away_team') or ''),hh=int(m.ht_home),ah=int(m.ht_away),hx=hx,ax=ax,outcome=outcome))
    return pd.DataFrame(records).sort_values(['date','match_id']).reset_index(drop=True) if records else pd.DataFrame()

@st.cache_resource(ttl=3600,show_spinner=False)
def strength_history():
    """Pregame strength proxy: last 8 prior xG-for and xG-against matches, league-relative.
    Matches on the same calendar day are processed together to prevent same-day leakage.
    Unknown teams have neutral 1.0 strength and a known=False flag.
    """
    _,_,meta,_=historical_data()
    raw=[]
    for mid,r in meta.items():
        try:
            dt=pd.to_datetime(r.get('match_date'),errors='coerce',utc=True)
            hgf,agf=float(r['home_xg']),float(r['away_xg'])
            if pd.isna(dt) or not all(math.isfinite(x) and x>=0 for x in (hgf,agf)): continue
            cid=str(r.get('competition_id') or ''); h=str(r.get('home_team') or ''); a=str(r.get('away_team') or '')
            if not cid or not h or not a or h==a: continue
            raw.append((dt.normalize(),mid,cid,h,a,hgf,agf))
        except (ValueError,TypeError,KeyError): continue
    raw.sort(key=lambda r:(r[0],r[1]))
    teams=defaultdict(lambda:deque(maxlen=8))
    league=defaultdict(lambda:deque(maxlen=300))
    results={}
    pos=0
    while pos<len(raw):
        end=pos+1
        while end<len(raw) and raw[end][0]==raw[pos][0]: end+=1
        for day,mid,cid,h,a,hgf,agf in raw[pos:end]:
            home_hist=teams[(cid,h)]; away_hist=teams[(cid,a)]
            lhist=league[cid]
            known=len(home_hist)>=4 and len(away_hist)>=4 and len(lhist)>=20
            if known:
                league_avg=max(.25,float(np.mean(lhist)))
                def score(hist):
                    gf=np.mean([x[0] for x in hist]); ga=np.mean([x[1] for x in hist])
                    # Shrink each attack and defence toward league average.
                    attack=(gf*len(hist)+league_avg*4)/(len(hist)+4)
                    defence=(ga*len(hist)+league_avg*4)/(len(hist)+4)
                    return attack,defence
                hat,hde=score(home_hist); aat,ade=score(away_hist)
                # Expected attacking matchup; normalized by league scoring level.
                hs=float(np.clip(hat*ade/(league_avg**2),.25,4))
                ass=float(np.clip(aat*hde/(league_avg**2),.25,4))
                balance=float(np.clip(math.log(hs/ass),-2,2))
            else: balance=0.0
            results[mid]=(balance,known)
        for day,mid,cid,h,a,hgf,agf in raw[pos:end]:
            teams[(cid,h)].append((hgf,agf)); teams[(cid,a)].append((agf,hgf))
            league[cid].extend((hgf,agf))
        pos=end
    return results

def smoothed_probabilities(frame):
    counts=frame['outcome'].value_counts(); n=len(frame)
    return {k:(int(counts.get(k,0))+1)/(n+3) for k in OUTCOMES}

def prediction_scores(probs,actual):
    return sum((probs[k]-int(k==actual))**2 for k in OUTCOMES),-math.log(max(probs[actual],1e-12))

def run_halftime_test(limit=200,tolerance=.30):
    hist=verified_history()
    if len(hist)<200: return pd.DataFrame(),len(hist),0,0
    strengths=strength_history()
    hist=hist.copy()
    hist['strength']=[strengths.get(mid,(0.0,False))[0] for mid in hist.match_id]
    hist['strength_known']=[strengths.get(mid,(0.0,False))[1] for mid in hist.match_id]
    testing=hist.iloc[int(len(hist)*.80):].tail(limit)
    groups={key:g for key,g in hist.groupby(['hh','ah'])}
    results=[]; excluded=defaultdict(int)
    for target in testing.itertuples(index=False):
        group=groups.get((target.hh,target.ah))
        if group is None: excluded['No score group']+=1; continue
        prior=group[group.date<target.date]
        if len(prior)<100: excluded['Fewer than 100 score comparables']+=1; continue
        similar=prior[(prior.hx-target.hx).abs()<=tolerance]
        similar=similar[(similar.ax-target.ax).abs()<=tolerance]
        if len(similar)<30: excluded['Fewer than 30 xG comparables']+=1; continue
        base=smoothed_probabilities(prior); xg=smoothed_probabilities(similar)
        # Strength-based third model only when target strength is known and
        # at least 20 comparable historical matches have known strength.
        # Smooth via distance-weighted neighbours, and shrink toward xG model.
        third=None; strength_n=0
        if target.strength_known:
            known=similar[similar.strength_known]
            if len(known)>=20:
                distances=np.abs(known.strength.to_numpy(float)-target.strength)
                weights=np.exp(-distances/.50)
                strength_n=len(known)
                weighted={k:float(weights[(known.outcome==k).to_numpy()].sum()) for k in OUTCOMES}
                total=float(weights.sum())
                # 30 equivalent observations of prior xG distribution.
                third={k:(weighted[k]+30*xg[k])/(total+30) for k in OUTCOMES}
        b0,l0=prediction_scores(base,target.outcome)
        b1,l1=prediction_scores(xg,target.outcome)
        b2,l2=prediction_scores(third,target.outcome) if third is not None else (float('nan'),float('nan'))
        trailing='home' if target.hh<target.ah else 'away' if target.ah<target.hh else None
        txg=target.hx if trailing=='home' else target.ax if trailing=='away' else None
        row={'Date':target.date.date().isoformat(),'Match ID':target.match_id,'HT score':f'{target.hh}-{target.ah}',
            'Actual':target.outcome,'Baseline Brier':b0,'STARLIZARD xG Brier':b1,'Strength Brier':b2,
            'Baseline log loss':l0,'STARLIZARD xG log loss':l1,'Strength log loss':l2,
            'Strength available':third is not None,'Strength index':target.strength if target.strength_known else np.nan,
            'Strength comparable N':strength_n,'Trailing xG flag':bool(trailing and txg>=.20),
            'Trailing scored next':target.outcome==trailing if trailing else None,
            'Baseline N':len(prior),'STARLIZARD N':len(similar)}
        for prefix,p in [('Baseline',base),('xG',xg),('Strength',third)]:
            for k in OUTCOMES: row[f'{prefix} {k}']=p[k] if p else np.nan
        results.append(row)
    return pd.DataFrame(results),len(hist),len(testing),dict(excluded)

def show_halftime_backtest():
    st.divider(); st.subheader('🧪 Halftime next-goal backtest')
    st.caption('Chronological out-of-sample comparison: score only, score + HT xG, and score + HT xG + pre-match team strength. Lower Brier and log loss are better.')
    limit=st.selectbox('Maximum recent matches to test',[200,500,1000],index=0,key='ht_limit')
    tolerance=st.selectbox('HT xG comparison tolerance',[.20,.30,.40,.50],index=1,key='ht_tol')
    if st.button('Run halftime backtest',type='primary',key='run_ht'):
        try:
            with st.spinner('Testing historical predictions...'):
                frame,n,considered,excluded=run_halftime_test(limit,tolerance)
            st.session_state['ht_result']=(frame,n,considered,excluded)
        except Exception as exc: st.error(f'Halftime backtest failed: {exc}')
    if 'ht_result' not in st.session_state: return
    frame,n,considered,excluded=st.session_state['ht_result']
    st.caption(f'{n:,} verified goal sequences; {considered:,} held-out matches considered.')
    if frame.empty: st.warning('No qualifying predictions.'); return
    st.success(f'{len(frame):,} out-of-sample predictions')
    rows=[]
    for label,b,l in [('HT score baseline','Baseline Brier','Baseline log loss'),('HT score + xG','STARLIZARD xG Brier','STARLIZARD xG log loss'),('HT score + xG + strength','Strength Brier','Strength log loss')]:
        part=frame.dropna(subset=[b,l])
        rows.append({'Method':label,'N':len(part),'Brier':round(part[b].mean(),4) if len(part) else None,'Log loss':round(part[l].mean(),4) if len(part) else None})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
    # Apples-to-apples comparison on the subset where strength is available.
    common=frame[frame['Strength available']]
    if len(common):
        st.markdown('**Fair comparison: same matches for all three methods**')
        st.caption(f'{len(common):,} matches with usable pre-match strength.')
        st.dataframe(pd.DataFrame([{'Method':label,'Brier':round(common[b].mean(),4),'Log loss':round(common[l].mean(),4)} for label,b,l in [('Score only','Baseline Brier','Baseline log loss'),('Score + xG','STARLIZARD xG Brier','STARLIZARD xG log loss'),('Score + xG + strength','Strength Brier','Strength log loss')]]),hide_index=True,width='stretch')
    if excluded:
        st.markdown('**Excluded matches**')
        st.dataframe(pd.DataFrame([{'Reason':k,'Matches':v} for k,v in excluded.items()]),hide_index=True,width='stretch')
    flagged=frame[frame['Trailing xG flag']]
    st.markdown('**Trailing-team HT xG ≥ 0.20**')
    if len(flagged):
        st.write(f'Flagged matches: {len(flagged)}')
        st.write(f'Trailing team scored next: {flagged["Trailing scored next"].astype(float).mean():.1%}')
        st.write(f'Baseline Brier: {flagged["Baseline Brier"].mean():.4f}')
        st.write(f'HT xG Brier: {flagged["STARLIZARD xG Brier"].mean():.4f}')
        if flagged['Strength available'].any():
            f=flagged[flagged['Strength available']]
            st.write(f'Strength Brier: {f["Strength Brier"].mean():.4f} ({len(f)} matches)')
    st.download_button('Download halftime backtest results',frame.to_csv(index=False),file_name='starlizard_halftime_v54.csv',mime='text/csv')
    st.caption('Experimental accuracy comparison, not betting ROI. Strength is a lagged xG-based proxy, not bookmaker odds or a fully calibrated team rating.')

def show_market_group(sample,heading,markets):
    st.markdown(f'**{heading}**'); rows=[]
    for name,predicate in markets:
        try:
            r=price_market(sample,predicate)
            rows.append({'Market':name,'Probability':f'{r["probability"]:.1%}' if r else '—','Fair odds':f'{r["fair_odds"]:.2f}' if r and r.get('fair_odds') else '—','N':r['sample'] if r else 0})
        except (ValueError,KeyError,TypeError): rows.append({'Market':name,'Probability':'—','Fair odds':'—','N':0})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')

def show_halftime_markets(sample):
    show_market_group(sample,'⚽ Second-half goals',[('Home scores 2H',home_scores_second_half),('Away scores 2H',away_scores_second_half),('Home wins 2H',home_wins_second_half),('Over 0.5 goals 2H',over_goals(.5)),('Over 1.5 goals 2H',over_goals(1.5)),('Over 2.5 goals 2H',over_goals(2.5))])
    show_market_group(sample,'🚩 Corners',[(f'Over {line:.1f} corners 2H',market_over('corners','second_half',line)) for line in (3.5,4.5,5.5)]+[(f'Over {line:.1f} corners FT',market_over('corners','all',line)) for line in (8.5,9.5)])
    show_market_group(sample,'🟨 Yellow cards',[(f'Over {line:.1f} yellows 2H',market_over('yellows','second_half',line)) for line in (1.5,2.5,3.5)]+[(f'Over {line:.1f} yellows FT',market_over('yellows','all',line)) for line in (3.5,4.5)])

@st.cache_data(ttl=3600)
def prematch_test_data():
    rows=load_table(database(),'historical_xg','match_id,competition_id,match_date,home_team,away_team,home_xg,away_xg,home_goals,away_goals')
    df=pd.DataFrame(rows)
    if df.empty: return df
    req=['match_id','competition_id','match_date','home_team','away_team','home_xg','away_xg','home_goals','away_goals']
    df=df.dropna(subset=req).copy(); df['match_date']=pd.to_datetime(df['match_date'],errors='coerce',utc=True)
    for c in ('home_xg','away_xg','home_goals','away_goals'): df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.dropna(subset=req)
    for c in ('home_xg','away_xg','home_goals','away_goals'): df=df[np.isfinite(df[c]) & (df[c]>=0)]
    df=df[(df.home_goals%1==0)&(df.away_goals%1==0)&(df.home_team!=df.away_team)]
    return df.drop_duplicates('match_id').sort_values(['competition_id','match_date','match_id']).reset_index(drop=True)

def prematch_backtest(df,months):
    last=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M')-1
    predictions=[]; audit=[]
    for cid,league in df.groupby('competition_id'):
        attempted=0; skipped=0
        for step in range(months):
            month=last-(months-1-step)
            cutoff=pd.Timestamp(month.start_time).tz_localize('UTC'); end=pd.Timestamp((month+1).start_time).tz_localize('UTC')
            train=league[league.match_date<cutoff]; test=league[(league.match_date>=cutoff)&(league.match_date<end)]
            attempted+=len(test)
            if len(test)==0: continue
            if len(train)<60: skipped+=len(test); continue
            try:
                ratings=fit_ratings(train[['match_id','competition_id','match_date','home_team','away_team','home_xg','away_xg']],cid,cutoff.strftime('%Y-%m-%d'),minimum_matches=60)
            except (ValueError,np.linalg.LinAlgError): skipped+=len(test); continue
            n=len(train)
            baseline=[((train.home_goals>train.away_goals).sum()+1)/(n+3),((train.home_goals==train.away_goals).sum()+1)/(n+3),((train.home_goals<train.away_goals).sum()+1)/(n+3)]
            bo=((train.home_goals+train.away_goals>=3).sum()+1)/(n+2)
            bb=(((train.home_goals>0)&(train.away_goals>0)).sum()+1)/(n+2)
            for r in test.itertuples(index=False):
                if r.home_team not in ratings.teams or r.away_team not in ratings.teams: skipped+=1; continue
                try: p=price_fixture(ratings,r.home_team,r.away_team)['probabilities']
                except (ValueError,OverflowError): skipped+=1; continue
                actual=0 if r.home_goals>r.away_goals else 1 if r.home_goals==r.away_goals else 2
                predictions.append({'League':league_label(cid),'outcome':actual,'model_home':p['home'],'model_draw':p['draw'],'model_away':p['away'],'base_home':baseline[0],'base_draw':baseline[1],'base_away':baseline[2],'model_over':p['over_2_5'],'base_over':bo,'actual_over':int(r.home_goals+r.away_goals>=3),'model_btts':p['btts_yes'],'base_btts':bb,'actual_btts':int(r.home_goals>0 and r.away_goals>0)})
        audit.append({'League':league_label(cid),'Test matches':attempted,'Not priced':skipped})
    return pd.DataFrame(predictions),pd.DataFrame(audit)

def prematch_summary(df):
    result={'Matches':len(df)}
    for label,prefix in [('Model','model'),('Baseline','base')]:
        p=df[[f'{prefix}_home',f'{prefix}_draw',f'{prefix}_away']].to_numpy(float)
        actual=df.outcome.to_numpy(int); y=np.eye(3)[actual]
        result[f'{label} 1X2 Brier']=round(float(np.mean(np.sum((p-y)**2,axis=1))),4)
        result[f'{label} 1X2 log loss']=round(float(np.mean(-np.log(np.clip(p[np.arange(len(p)),actual],1e-12,1)))),4)
        result[f'{label} O2.5 Brier']=round(float(np.mean((df[f'{prefix}_over']-df.actual_over)**2)),4)
        result[f'{label} BTTS Brier']=round(float(np.mean((df[f'{prefix}_btts']-df.actual_btts)**2)),4)
    return result

st.title('🦎 PRO STARLIZARD')
st.caption('Halftime-first unified pricing | V5.4 · Team-strength experiment')
tab_ht,tab_pre,tab_test=st.tabs(['⏱️ Halftime','⚽ Pre-match','📊 Backtest'])
with tab_ht:
    st.subheader('Halftime pricing — main dashboard')
    try:
        with st.spinner('Loading historical halftime records...'):
            matches,rejected,meta,timelines=historical_data()
    except Exception as exc:
        st.error(f'Historical data failed: {exc}'); matches=[]
    if matches:
        st.caption(f'{len(matches):,} score-valid historical matches loaded')
        c1,c2=st.columns(2)
        with c1: home_name=st.text_input('Home team label','Home')
        with c2: away_name=st.text_input('Away team label','Away')
        c1,c2=st.columns(2)
        with c1:
            hh=st.number_input(f'{home_name} HT goals',0,10,0)
            hx=st.number_input(f'{home_name} HT xG',0.,10.,.85,.05)
        with c2:
            ah=st.number_input(f'{away_name} HT goals',0,10,1)
            ax=st.number_input(f'{away_name} HT xG',0.,10.,.35,.05)
        with st.expander('Historical filters'):
            tolerance=st.slider('HT xG tolerance',.10,1.,.30,.05)
            cid=st.selectbox('League scope',['All leagues']+sorted({m.competition_id for m in matches}),format_func=lambda x:x if x=='All leagues' else league_label(x))
        sample=comparable_matches(matches,int(hh),int(ah),float(hx),float(ax),tolerance=float(tolerance),before_date=date.today().isoformat(),competition_id=None if cid=='All leagues' else cid)
        st.markdown(f'**{home_name} {hh}–{ah} {away_name}** · {len(sample)} comparable matches')
        if len(sample)<100: st.warning('Small historical sample. Prices may be unstable.')
        st.subheader('🥅 First goal after halftime')
        counts={k:0 for k in OUTCOMES}; invalid=0
        for m in sample:
            mid=str(m.match_id); outcome=parse_goal_sequence(m,meta.get(mid,{}),timelines.get(mid))
            if outcome in counts: counts[outcome]+=1
            else: invalid+=1
        n=sum(counts.values())
        if n:
            st.dataframe(pd.DataFrame([{'Outcome':label,'Probability':f'{counts[k]/n:.1%}','Fair odds':f'{n/counts[k]:.2f}' if counts[k] else '—','Count':counts[k]} for k,label in [('home',f'{home_name} scores next'),('away',f'{away_name} scores next'),('none','No second-half goal')]]),hide_index=True,width='stretch')
            st.caption(f'{n} verified goal sequences; {invalid} excluded timelines. Three outcomes total 100%.')
            if n<100: st.warning('Next-goal sample below 100 verified sequences.')
            if hh!=ah:
                trailing='home' if hh<ah else 'away'; txg=hx if trailing=='home' else ax
                if txg>=.20: st.info(f'Automatic flag: trailing team HT xG {txg:.2f} ≥ 0.20. Trailing team scored first in the second half {counts[trailing]}/{n} times ({counts[trailing]/n:.1%}). Historical frequency, not a proven edge.')
        else: st.warning('No verified goal sequences in this sample.')
        st.subheader('Second-half goals, corners and cards')
        if sample: show_halftime_markets(sample)
        st.caption('Historical conditional frequencies, not calibrated team-specific forecasts. No live odds fetched.')
        show_halftime_backtest()
with tab_pre:
    st.subheader('Pre-match pricing')
    try: leagues=catalogue()
    except Exception as exc: st.error(f'Catalogue failed: {exc}'); leagues={}
    if leagues:
        cid=st.selectbox('League',list(leagues),format_func=league_label,key='pre_cid')
        teams=leagues[cid]
        if len(teams)>=2:
            c1,c2=st.columns(2)
            with c1: home=st.selectbox('Home team',teams,key='pre_home')
            with c2: away=st.selectbox('Away team',teams,index=1,key='pre_away')
            cutoff=st.date_input('Price fixture using data before',date.today())
            with st.expander('Rating settings'):
                half_life=st.slider('Recency half-life (days)',60,365,180,5)
                ridge=st.slider('Rating shrinkage',2.,30.,10.,1.)
            if home==away: st.warning('Choose two different teams.')
            else:
                try:
                    rating=ratings_for(cid,cutoff.isoformat(),half_life,ridge)
                    priced=price_fixture(rating,home,away)
                except Exception as exc: st.warning(f'Could not price fixture: {exc}'); priced=None
                if priced:
                    st.markdown(f'**{home} v {away}**')
                    c1,c2=st.columns(2); c1.metric('Home xG',f'{priced["home_xg"]:.2f}'); c2.metric('Away xG',f'{priced["away_xg"]:.2f}')
                    st.caption(f'{rating.matches} training matches across {len(rating.teams)} teams')
                    markets=[('Home win','home'),('Draw','draw'),('Away win','away'),('Over 2.5','over_2_5'),('Under 2.5','under_2_5'),('BTTS Yes','btts_yes'),('BTTS No','btts_no')]
                    st.dataframe(pd.DataFrame([{'Market':label,'Probability':f'{priced["probabilities"][key]:.1%}','Fair odds':f'{priced["fair_odds"][key]:.2f}' if priced['fair_odds'][key] else '—'} for label,key in markets]),hide_index=True,width='stretch')
                    st.subheader('Asian pricing')
                    choices={'Home handicap':'home_handicap','Away handicap':'away_handicap','Over goals':'over_goals','Under goals':'under_goals'}
                    choice=st.selectbox('Asian market',list(choices)); handicap='handicap' in choice
                    lines=[i/4 for i in range(-12,13)] if handicap else [i/4 for i in range(2,25)]
                    line=st.selectbox('Asian line',lines,index=lines.index(0. if handicap else 2.5))
                    asian=asian_market(priced['matrix'],choices[choice],line)
                    if asian['fair_odds'] is None: st.warning('No finite fair odds for this line.')
                    else:
                        st.metric('Asian fair odds',f'{asian["fair_odds"]:.3f}')
                        quote=st.number_input('Bookmaker decimal odds',min_value=1.01,max_value=100.,value=1.95,step=.01)
                        roi=asian['win_units']*(quote-1)-asian['loss_units']
                        st.metric('Model-implied ROI',f'{roi:+.2%}')
                    with st.expander('Correct-score prices'):
                        st.dataframe(pd.DataFrame([{'Score':score,'Probability':f'{p:.2%}','Fair odds':f'{1/p:.2f}'} for score,p in priced['correct_scores'].items() if p>0]),hide_index=True,width='stretch')
                    st.caption('Experimental model prices. No proven betting edge.')
with tab_test:
    st.subheader('Pre-match historical accuracy backtest')
    st.caption('Expanding training history. Complete calendar months only. Lower scores are better.')
    months=st.selectbox('Recent complete months',[3,6,9,12],index=1)
    if st.button('Run historical accuracy test',type='primary'):
        try:
            with st.spinner('Testing pre-match predictions...'):
                data=prematch_test_data()
                predictions,audit=prematch_backtest(data,months) if not data.empty else (pd.DataFrame(),pd.DataFrame())
                st.session_state['pre_result']=(predictions,audit,len(data))
        except Exception as exc: st.error(f'Pre-match backtest failed: {exc}')
    if 'pre_result' in st.session_state:
        predictions,audit,valid=st.session_state['pre_result']; st.caption(f'{valid:,} valid historical records')
        if predictions.empty: st.warning('No out-of-sample predictions in this window.')
        else:
            st.success(f'{len(predictions):,} out-of-sample predictions')
            st.subheader('Overall accuracy'); st.dataframe(pd.DataFrame([prematch_summary(predictions)]),hide_index=True,width='stretch')
            st.subheader('By league'); st.dataframe(pd.DataFrame([dict(League=name,**prematch_summary(part)) for name,part in predictions.groupby('League')]),hide_index=True,width='stretch')
            st.subheader('Probability calibration')
            market=st.selectbox('Calibration market',['Over 2.5 goals','BTTS Yes'])
            pcol,ycol=('model_over','actual_over') if market=='Over 2.5 goals' else ('model_btts','actual_btts')
            bins=[]
            for i in range(10):
                low=i/10; high=(i+1)/10
                part=predictions[(predictions[pcol]>=low)&(predictions[pcol]<(high if i<9 else high+1e-8))]
                if len(part): bins.append({'Band':f'{low:.0%}–{high:.0%}','N':len(part),'Predicted':round(float(part[pcol].mean()),3),'Actual':round(float(part[ycol].mean()),3)})
            st.dataframe(pd.DataFrame(bins),hide_index=True,width='stretch')
            st.download_button('Download backtest predictions',predictions.to_csv(index=False),file_name='starlizard_prematch_backtest.csv',mime='text/csv')
        st.subheader('Coverage and exclusions'); st.dataframe(audit,hide_index=True,width='stretch')
    st.info('Prediction accuracy is not betting profitability. Historical bookmaker odds are needed for ROI testing.')
st.divider(); st.caption('PRO STARLIZARD V5.4 · Read-only Supabase · Halftime-first · Lagged team-strength experiment')
