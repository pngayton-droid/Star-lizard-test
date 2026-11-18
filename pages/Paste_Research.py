"""Paste-based research and fair-odds desk. No external API requests."""
import csv
import io
import math
import re
from collections import Counter
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Starlizard | Paste Research",page_icon="📋",layout="wide")
st.title("📋 Paste Research & Fair Odds")
st.caption("Paste your own match statistics or an odds report. No API calls or database writes.")

tab1,tab2=st.tabs(["📊 Calculate from match data","🎯 Display a fair-odds report"])
with tab1:
    st.markdown("### Paste recent match statistics")
    st.write("Use one match per line, with a header row. Columns: `goals_for,goals_against,corners_for,corners_against,cards_for,cards_against,shots_for,shots_against,fouls_for,fouls_against`. Missing optional statistics may be left blank.")
    example="goals_for,goals_against,corners_for,corners_against,cards_for,cards_against,shots_for,shots_against,fouls_for,fouls_against\n2,1,6,4,2,3,15,10,11,14\n1,1,5,5,1,2,12,12,10,12"
    data=st.text_area("Recent matches (CSV)",height=180,placeholder=example,key="recent_paste")
    st.caption("Enter the home team's home matches and the away team's away matches separately for more meaningful comparisons.")
    data2=st.text_area("Away team's recent away matches (same columns)",height=160,key="away_paste")
    def parse(text):
        if not text.strip():return []
        rows=[]
        reader=csv.DictReader(io.StringIO(text.strip()))
        cols={"goals_for","goals_against","corners_for","corners_against","cards_for","cards_against","shots_for","shots_against","fouls_for","fouls_against"}
        if not {"goals_for","goals_against"}.issubset(set(reader.fieldnames or [])):
            raise ValueError("Include goals_for and goals_against column headers.")
        for raw in reader:
            record={}
            for key in cols:
                value=(raw.get(key) or "").strip()
                if not value:continue
                number=float(value)
                if not math.isfinite(number) or number<0:raise ValueError(f"Invalid {key}: {value}")
                record[key]=number
            rows.append(record)
        return rows
    def calc_market(label,values,predicate):
        count=sum(predicate(v) for v in values);n=len(values);p=count/n
        return {"Market":label,"Occurred":count,"Sample":n,"Frequency":f"{p:.1%}","Historical fair odds":f"{1/p:.2f}" if p else "—"}
    if st.button("Calculate pasted match frequencies",type="primary",use_container_width=True):
        try:
            h=parse(data);a=parse(data2)
            if not h and not a:st.warning("Paste at least one match first.")
            else:
                st.info(f"Home sample: {len(h)} matches · Away sample: {len(a)} matches. Each team is analysed separately.")
                results=[]
                for label,rows in [("Home team",h),("Away team",a)]:
                    if not rows:continue
                    st.subheader(label)
                    out=[]
                    for title,keys,thresholds in [
                        ("Total goals",("goals_for","goals_against"),[1.5,2.5,3.5]),
                        ("Total corners",("corners_for","corners_against"),[8.5,9.5,10.5,11.5]),
                        ("Total cards",("cards_for","cards_against"),[2.5,3.5,4.5,5.5]),
                    ]:
                        valid=[r for r in rows if all(k in r for k in keys)]
                        for t in thresholds:
                            if valid:out.append(calc_market(f"Over {t:g} {title.lower()}",valid,lambda r,t=t,keys=keys:sum(r[k] for k in keys)>t))
                    valid=[r for r in rows if "goals_for" in r and "goals_against" in r]
                    if valid:
                        out.append(calc_market("Both teams scored",valid,lambda r:r["goals_for"]>0 and r["goals_against"]>0))
                        out.append(calc_market("Team won",valid,lambda r:r["goals_for"]>r["goals_against"]))
                    st.dataframe(pd.DataFrame(out),hide_index=True,use_container_width=True)
                    averages=[]
                    for metric in ["goals_for","goals_against","corners_for","corners_against","cards_for","cards_against","shots_for","shots_against","fouls_for","fouls_against"]:
                        v=[r[metric] for r in rows if metric in r]
                        if v:averages.append({"Statistic":metric.replace("_"," ").title(),"Average":round(sum(v)/len(v),2),"Matches":len(v)})
                    st.markdown("**Recent averages**")
                    st.dataframe(pd.DataFrame(averages),hide_index=True,use_container_width=True)
                st.warning("These are observed frequencies for each team's sample, not combined fixture predictions. Small samples and differences in opponents can make prices unreliable.")
        except Exception as exc:
            st.error(f"Please check the pasted format: {exc}")

with tab2:
    st.markdown("### Paste a fair-odds report")
    st.write("Paste a table with one market per line: `Market,Probability,Fair Odds`. Probability can be entered as a percentage. You can paste the table I prepare in our chat.")
    fixture=st.text_input("Fixture name",placeholder="Manchester City v Fulham")
    pasted=st.text_area("Market,Probability,Fair Odds",height=210,placeholder="Market,Probability,Fair Odds\nOver 2.5 goals,58.8%,1.70\nBoth teams to score,60.1%,1.67",key="odds_paste")
    if st.button("Show my fair-odds board",type="primary",use_container_width=True):
        try:
            reader=csv.reader(io.StringIO(pasted.strip()))
            board=[]
            for row in reader:
                if not row or not any(c.strip() for c in row):continue
                if row[0].strip().lower()=="market":continue
                if len(row)<3:raise ValueError("Each row needs Market, Probability, Fair Odds.")
                name,p_raw,o_raw=[x.strip() for x in row[:3]]
                p=float(p_raw.rstrip("%"))/(100 if "%" in p_raw else 1)
                price=float(o_raw)
                if not (0<p<=1 and price>=1 and math.isfinite(price)):
                    raise ValueError("Probabilities must be 0–100% and fair odds at least 1.00.")
                expected=1/p
                board.append({"Market":name,"Probability":f"{p:.1%}","Fair odds":f"{price:.2f}","Calculated odds":f"{expected:.2f}","Check":"OK" if abs(price-expected)<0.06 else "Review"})
            if not board:st.warning("Paste some market rows first.")
            else:
                st.subheader(fixture or "Fair-odds board")
                st.dataframe(pd.DataFrame(board),hide_index=True,use_container_width=True)
                st.download_button("Download odds as CSV",pd.DataFrame(board).to_csv(index=False),file_name="starlizard_fair_odds.csv",mime="text/csv",use_container_width=True)
                st.caption("These are pasted estimates, not independently verified by the app. Check the source and assumptions before using them.")
        except Exception as exc:st.error(f"Couldn't read the odds table: {exc}")
