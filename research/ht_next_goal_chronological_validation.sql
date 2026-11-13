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
SELECT CASE WHEN match_date<'2025-07-01' THEN 'train_pre_jul_2025'
            WHEN match_date<'2026-01-01' THEN 'validation_jul_dec_2025'
            ELSE 'later_test_2026' END period,
       CASE WHEN trailing_ht_xg>=0.20 THEN 'xg_020_plus' ELSE 'xg_below_020' END band,
       count(*) matches,
       count(*) FILTER(WHERE first_2h=trailing_side) hits,
       round(100.0*count(*) FILTER(WHERE first_2h=trailing_side)/count(*),2) hit_pct
FROM eligible WHERE trailing_ht_xg IS NOT NULL
GROUP BY 1,2 ORDER BY 1,2;
