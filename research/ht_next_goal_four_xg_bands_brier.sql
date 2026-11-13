-- Existing stored StatsAPI only. Train-only smoothed model comparison.
-- Four bands: <0.20, 0.20-0.49, 0.50-0.99, >=1.00.
-- Price relative strength from Bet365 last_seen: timestamp not verified.
-- Existing StatsAPI records only; no provider calls.
-- Strength uses unverified Bet365 last_seen relative prices, not true pre-match odds.
-- Pre-July 2025 training only, fixed smoothing, date-separated validation and later test.
-- SQL score-reconciled timelines, not yet strict full-event chronology verified.
-- Read-only. Bet365 last_seen is not verified pre-match; relative strength proxy only.
-- Goal totals reconciled, not a full chronology audit.
-- Read-only chronological validation of a previously selected HT xG 0.20 screen.
-- These are descriptive outcomes, not a pristine untouched holdout:
-- the threshold was explored before this split.
-- All scoring events: goal, penalty_scored, own_goal (credited to opponent).
-- Requires exact official HT and FT score reconciliation.
WITH scoring AS (
 SELECT x.match_id,x.match_date,x.home_ht_goals hh,x.away_ht_goals ah,
        x.home_goals hf,x.away_goals af,x.home_ht_xg hx,x.away_ht_xg ax,
        v->>'period' period,(v->>'sequence')::int seq,
        CASE WHEN (v->>'type'='own_goal' AND v->'team'->>'name'=x.away_team)
                    OR (v->>'type'<>'own_goal' AND v->'team'->>'name'=x.home_team)
                  THEN 'home'
             WHEN (v->>'type'='own_goal' AND v->'team'->>'name'=x.home_team)
                    OR (v->>'type'<>'own_goal' AND v->'team'->>'name'=x.away_team)
                  THEN 'away' ELSE 'unknown' END side
 FROM historical_xg x JOIN historical_match_events e USING(match_id)
 CROSS JOIN LATERAL jsonb_array_elements(e.timeline_data->'events') v
 WHERE v->>'type' IN ('goal','own_goal','penalty_scored')
), reconciled AS (
 SELECT match_id,max(match_date) match_date,max(hh) hh,max(ah) ah,
        max(hf) hf,max(af) af,max(hx) hx,max(ax) ax,
        (array_agg(side ORDER BY seq) FILTER(WHERE period='second_half'))[1] first_2h,
        count(*) FILTER(WHERE side='home' AND period='first_half') chh,
        count(*) FILTER(WHERE side='away' AND period='first_half') cah,
        count(*) FILTER(WHERE side='home') chf,
        count(*) FILTER(WHERE side='away') caf,
        count(*) FILTER(WHERE side='unknown'
                            OR period NOT IN ('first_half','second_half')) invalid
 FROM scoring GROUP BY match_id
), eligible AS (
 SELECT *,CASE WHEN hh>ah THEN 'away' ELSE 'home' END trailing_side,
          CASE WHEN hh>ah THEN ax ELSE hx END trailing_ht_xg
 FROM reconciled
 WHERE abs(hh-ah)=1 AND hh=chh AND ah=cah
   AND hf=chf AND af=caf AND invalid=0
)
, quotes AS (
 SELECT o.match_id,
 (b->'markets'->'match_odds'->'home'->>'last_seen')::numeric hp,
 (b->'markets'->'match_odds'->'away'->>'last_seen')::numeric ap
 FROM historical_match_odds o
 CROSS JOIN LATERAL jsonb_array_elements(coalesce(o.odds_payload->'data'->'bookmakers','[]'::jsonb)) b
 WHERE b->>'bookmaker'='Bet365'
 AND b->'markets'->'match_odds'->'home'->>'last_seen' IS NOT NULL
 AND b->'markets'->'match_odds'->'away'->>'last_seen' IS NOT NULL
), classified AS (
 SELECT e.*,CASE WHEN trailing_side='home' THEN q.hp ELSE q.ap END trailing_quote,
 CASE WHEN trailing_side='home' THEN q.ap ELSE q.hp END leader_quote
 FROM eligible e JOIN quotes q USING(match_id)
 WHERE abs(hh-ah)=1
)
, samples AS (
 SELECT match_id,match_date,
 CASE WHEN trailing_quote>leader_quote THEN 'longer'
 WHEN trailing_quote<leader_quote THEN 'shorter' ELSE 'equal' END strength,
 CASE WHEN trailing_ht_xg<0.20 THEN 'xg_0_019'
 WHEN trailing_ht_xg<0.50 THEN 'xg_020_049'
 WHEN trailing_ht_xg<1.00 THEN 'xg_050_099'
 ELSE 'xg_100_plus' END xg_band,
 CASE WHEN trailing_ht_xg>=0.20 THEN 'high' ELSE 'low' END binary_xg,
 CASE WHEN first_2h=trailing_side THEN 1.0 ELSE 0.0 END outcome
 FROM classified WHERE trailing_ht_xg IS NOT NULL AND trailing_quote>1 AND leader_quote>1
), training AS (
 SELECT strength,count(*) n,sum(outcome) wins FROM samples
 WHERE match_date<'2025-07-01' GROUP BY strength
), train_binary AS (
 SELECT strength,binary_xg,count(*) n,sum(outcome) wins FROM samples
 WHERE match_date<'2025-07-01' GROUP BY strength,binary_xg
), train_four AS (
 SELECT strength,xg_band,count(*) n,sum(outcome) wins FROM samples
 WHERE match_date<'2025-07-01' GROUP BY strength,xg_band
), preds AS (
 SELECT s.*,CASE WHEN match_date<'2026-01-01' THEN 'validation' ELSE 'later_test' END period,
 (t.wins+2.0)/(t.n+4.0) p_strength,
 (b.wins+4.0*((t.wins+2.0)/(t.n+4.0)))/(b.n+4.0) p_binary,
 (f.wins+12.0*((t.wins+2.0)/(t.n+4.0)))/(f.n+12.0) p_four
 FROM samples s JOIN training t USING(strength)
 JOIN train_binary b USING(strength,binary_xg)
 JOIN train_four f USING(strength,xg_band)
 WHERE s.match_date>='2025-07-01'
)
SELECT period,strength,count(*) n,
 round(avg(power(outcome-p_strength,2))::numeric,6) brier_strength,
 round(avg(power(outcome-p_binary,2))::numeric,6) brier_binary,
 round(avg(power(outcome-p_four,2))::numeric,6) brier_four_bins,
 round((avg(power(outcome-p_binary,2))-avg(power(outcome-p_four,2)))::numeric,6) four_vs_binary_improvement
FROM preds GROUP BY period,strength
UNION ALL
SELECT period,'ALL',count(*),
 round(avg(power(outcome-p_strength,2))::numeric,6),
 round(avg(power(outcome-p_binary,2))::numeric,6),
 round(avg(power(outcome-p_four,2))::numeric,6),
 round((avg(power(outcome-p_binary,2))-avg(power(outcome-p_four,2)))::numeric,6)
FROM preds GROUP BY period ORDER BY period,strength;