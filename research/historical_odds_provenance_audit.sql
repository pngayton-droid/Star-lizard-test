-- Read-only historical odds provenance and opening-price coverage audit.
-- fetched_at is collector retrieval time, not the bookmaker's quote-validity time.
-- last_seen has no quote timestamp in this stored payload and MUST NOT be treated
-- as verified pre-match information.
SELECT count(*) total_odds_records,
       count(*) FILTER(WHERE x.match_date::date < o.fetched_at::date) fetched_after_match,
       min(o.fetched_at) first_fetch, max(o.fetched_at) last_fetch,
       min(x.match_date) earliest_match, max(x.match_date) latest_match
FROM historical_match_odds o JOIN historical_xg x USING(match_id);

SELECT count(*) bet365_records,
       count(*) FILTER(WHERE b->'markets'->'match_odds'->'home'->>'opening' IS NOT NULL
                         AND b->'markets'->'match_odds'->'away'->>'opening' IS NOT NULL) paired_opening,
       count(*) FILTER(WHERE b->'markets'->'match_odds'->'home'->>'last_seen' IS NOT NULL
                         AND b->'markets'->'match_odds'->'away'->>'last_seen' IS NOT NULL) paired_last_seen,
       count(*) FILTER(WHERE b->'markets'->'match_odds'->'home'->>'opening' IS NOT NULL
                         AND b->'markets'->'match_odds'->'away'->>'opening' IS NOT NULL
                         AND x.home_ht_xg IS NOT NULL AND x.away_ht_xg IS NOT NULL
                         AND abs(x.home_ht_goals-x.away_ht_goals)>=1) opening_and_trailing_ht
FROM historical_match_odds o JOIN historical_xg x USING(match_id)
CROSS JOIN LATERAL jsonb_array_elements(coalesce(o.odds_payload->'data'->'bookmakers','[]'::jsonb)) b
WHERE b->>'bookmaker'='Bet365';
