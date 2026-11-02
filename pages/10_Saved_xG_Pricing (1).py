"""Pro Star Lizard — saved historical xG, no API calls."""
from pathlib import Path
from datetime import date
import math
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Star Lizard | Saved xG Pricing', layout='centered')
st.title('Pro Star Lizard | Saved xG Pricing')
st.caption('Reads data/starlizard_xg_history_master.csv directly from GitHub deployment. No API calls.')

DATA = Path(__file__).resolve().parent.parent / 'data' / 'starlizard_xg_history_master.csv'
if not DATA.exists():
    st.error(f'Cannot find {DATA}. Confirm the CSV is in the repository data folder with this exact filename.')
    st.stop()

@st.cache_data(show_spinner=False)
def load_data(path, modified):
    raw = pd.read_csv(path, encoding='utf-8-sig')
    required = ['Date','Home','Away','Home xG','Away xG']
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise ValueError('Missing CSV columns: ' + ', '.join(missing))
    df = raw.copy()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    for c in ['Home xG','Away xG']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    for c in ['Home','Away']:
        df[c] = df[c].astype('string').str.strip()
    df = df.dropna(subset=required)
    df = df[(df['Home'] != '') & (df['Away'] != '') & (df['Home'] != df['Away'])]
    df = df[(df['Home xG'] >= 0) & (df['Away xG'] >= 0)]
    if 'Match ID' in df.columns:
        valid = df['Match ID'].astype('string').str.startswith('mt_', na=False)
        df['_dedupe'] = np.where(valid, df['Match ID'].astype('string'),
                                  df['Date'].dt.strftime('%Y-%m-%d') + '|' + df['Home'] + '|' + df['Away'])
    else:
        df['_dedupe'] = df['Date'].dt.strftime('%Y-%m-%d') + '|' + df['Home'] + '|' + df['Away']
    return df.drop_duplicates('_dedupe', keep='last').drop(columns='_dedupe')

try:
    df = load_data(str(DATA), DATA.stat().st_mtime_ns)
except Exception as exc:
    st.error(f'Could not read saved xG history: {exc}')
    st.stop()

st.success(f'Loaded {len(df)} unique historical matches automatically.')
st.caption(f'{len(set(df.Home) | set(df.Away))} team names represented. Team names must be consistent across matches.')
if len(df) < 15:
    st.error('Too few usable matches to fit a model.')
    st.stop()

teams = sorted(set(df['Home']) | set(df['Away']))
st.subheader('1. Choose fixture')
col1, col2 = st.columns(2)
with col1:
    home = st.selectbox('Home team', teams, index=teams.index('Newcastle United') if 'Newcastle United' in teams else 0)
with col2:
    away = st.selectbox('Away team', teams, index=teams.index('Everton') if 'Everton' in teams else min(1,len(teams)-1))
cutoff = st.date_input('Train on matches before', value=date.today())
half_life = st.slider('Recency half-life (days)', 60, 365, 180, 30)
ridge = st.slider('Rating shrinkage', 2.0, 30.0, 10.0, 2.0)

@st.cache_data(show_spinner=False)
def fit(data, cutoff_string, half_life, ridge):
    sample = data[data['Date'] < pd.Timestamp(cutoff_string)].copy()
    sample['Age'] = (pd.Timestamp(cutoff_string) - sample['Date']).dt.days
    names = sorted(set(sample['Home']) | set(sample['Away']))
    idx = {t:i for i,t in enumerate(names)}
    n = len(names)
    X, y, weights = [], [], []
    for _, r in sample.iterrows():
        h, a = idx[r['Home']], idx[r['Away']]
        w = 2 ** (-float(r['Age']) / half_life)
        for attack, defence, homeflag, xg in ((h,a,1,r['Home xG']), (a,h,0,r['Away xG'])):
            row = np.zeros(2+2*n)
            row[0], row[1], row[2+attack], row[2+n+defence] = 1, homeflag, 1, -1
            X.append(row)
            y.append(math.log(float(xg)+0.15))
            weights.append(w)
    X = np.asarray(X)
    y = np.asarray(y)
    sw = np.sqrt(np.asarray(weights))
    penalty = np.eye(X.shape[1])*ridge
    penalty[0,0] = .001
    penalty[1,1] = ridge*2
    WX = X*sw[:,None]
    beta = np.linalg.solve(WX.T @ WX + penalty, WX.T @ (y*sw))
    return sample, names, idx, beta

if home == away:
    st.warning('Choose two different teams.')
    st.stop()

training = df[df['Date'] < pd.Timestamp(cutoff)]
if len(training) < 15:
    st.error('Fewer than 15 matches before this cutoff date.')
    st.stop()

try:
    sample, fitted_teams, idx, beta = fit(df, cutoff.isoformat(), half_life, ridge)
except Exception as exc:
    st.error(f'Rating fit failed: {exc}')
    st.stop()
if home not in idx or away not in idx:
    st.error('One selected team has no training matches before the cutoff.')
    st.stop()

n = len(fitted_teams)
h, a = idx[home], idx[away]
hxg = max(.1,min(5.,math.exp(beta[0]+beta[1]+beta[2+h]-beta[2+n+a])-.15))
axg = max(.1,min(5.,math.exp(beta[0]+beta[2+a]-beta[2+n+h])-.15))
st.subheader('2. Opposition-adjusted xG')
c1,c2 = st.columns(2)
c1.metric(f'{home} xG', f'{hxg:.2f}')
c2.metric(f'{away} xG', f'{axg:.2f}')
st.write(f'**{len(sample)}** training matches · **{n}** teams')
st.caption('Weighted regularised log-xG attack/defence regression with home advantage. Training excludes matches on or after the chosen date. No future data is used for earlier cutoffs.')

@st.cache_data(show_spinner=False)
def score_grid(hxg, axg, cap=20):
    def poisson(lam):
        probs = [math.exp(-lam)]
        for k in range(1,cap+1):
            probs.append(probs[-1]*lam/k)
        return probs
    ph,pa = poisson(hxg),poisson(axg)
    return [(h,a,ph[h]*pa[a]) for h in range(cap+1) for a in range(cap+1)]

def result(diff):
    return 1 if diff > 1e-9 else (-1 if diff < -1e-9 else 0)

def settle(diff,line):
    if round(line*4)%2:
        lower = math.floor(line*2)/2
        return (result(diff+lower)+result(diff+lower+.5))/2
    return result(diff+line)

st.subheader('3. Experimental Asian prices')
market = st.selectbox('Market',['Home handicap','Away handicap','Over goals','Under goals'])
lines = [i/4 for i in range(-12,13)] if 'handicap' in market else [i/4 for i in range(2,25)]
line = st.selectbox('Asian line',lines,index=lines.index(0.0 if 'handicap' in market else 2.5))
outcomes = {1:0.,.5:0.,0:0.,-.5:0.,-1:0.}
for hs,aw,p in score_grid(hxg,axg):
    diff = {'Home handicap':hs-aw,'Away handicap':aw-hs,'Over goals':hs+aw,'Under goals':-hs-aw}[market]
    adjusted_line = -line if market == 'Over goals' else line
    outcomes[settle(diff,adjusted_line)] += p
w = outcomes[1]+.5*outcomes[.5]
loss = outcomes[-1]+.5*outcomes[-.5]
fair = 1+loss/w if w else float('inf')
st.metric('Model fair odds', f'{fair:.3f}')
st.write(f'Full win {outcomes[1]:.1%} · Half win {outcomes[.5]:.1%} · Push {outcomes[0]:.1%}')
st.write(f'Half loss {outcomes[-.5]:.1%} · Full loss {outcomes[-1]:.1%}')
quote = st.number_input('Market odds (optional comparison)',1.01,100.0,1.95,.01)
st.metric('Model-implied ROI',f'{w*(quote-1)-loss:+.2%}')
st.warning('Experimental prices only. Not a verified betting edge; the next stage is out-of-sample backtesting and calibration.')
with st.expander('Training evidence'):
    st.dataframe(sample[['Date','Home','Away','Home xG','Away xG']].sort_values('Date',ascending=False),hide_index=True,use_container_width=True)
