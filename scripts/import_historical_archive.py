"""Historical archive importer. Run privately with SUPABASE_DB_URL set.
Usage: python scripts/import_historical_archive.py starlizard_import_ready.zip
Dependencies: psycopg[binary]>=3.2,<4
Never commit database credentials or archive files to a public repository.
"""
import csv
import io
import json
import os
import sys
import zipfile

import psycopg

BATCH = 300

def rows(z, filename):
    with z.open(filename) as file:
        yield from csv.DictReader(io.TextIOWrapper(file, encoding="utf-8-sig"))

def flag(value):
    return str(value).lower() in ("1", "true")

def number(value):
    if value is None or value == "":
        return None
    return float(value)

def insert_batches(cursor, sql, values):
    batch = []
    count = 0
    for value in values:
        batch.append(value)
        if len(batch) >= BATCH:
            cursor.executemany(sql, batch)
            count += len(batch)
            batch = []
    if batch:
        cursor.executemany(sql, batch)
        count += len(batch)
    return count

def football(r):
    excluded = {"archive_key", "source_file", "source_row"}
    payload = {k: (number(v) if k.startswith(("ft_", "ht_", "corners_", "yellow_", "red_", "odds_")) else v)
               for k, v in r.items() if k not in excluded and v != ""}
    return (r["archive_key"], r["date"], r["league"], r["home"], r["away"],
            flag(r["has_ft_score"]), flag(r["has_ht_score"]), flag(r["has_corners"]),
            flag(r["has_yellows"]), flag(r["has_b365_odds"]), r["source_file"],
            int(r["source_row"]), json.dumps(payload))

def understat(r):
    payload = {k: (number(v) if k.startswith(("ft_", "ht_xg_", "full_xg_", "shot_xg_"))
                   and k != "ht_xg_timing_convention" else v)
               for k, v in r.items() if v != ""}
    return (int(r["understat_id"]), r["date"], r["league"], r["home"], r["away"],
            flag(r["verified_goal_sequence"]), True, json.dumps(payload))

def main(path):
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("SUPABASE_DB_URL missing; set privately, never in GitHub source")
    with zipfile.ZipFile(path) as z, psycopg.connect(url, connect_timeout=20) as conn:
        with conn.cursor() as cur:
            n = insert_batches(cur, """
                INSERT INTO public.archive_football_data
                (archive_key,match_date,league,home_team,away_team,has_ft_score,has_ht_score,
                has_corners,has_yellows,has_b365_odds,source_file,source_row,payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (archive_key) DO NOTHING
            """, (football(r) for r in rows(z, "football_data_pre2022.csv")))
            print("football-data processed", n)
            n = insert_batches(cur, """
                INSERT INTO public.archive_understat
                (understat_id,match_date,league,home_team,away_team,verified_goal_sequence,
                ht_xg_provisional,payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (understat_id) DO NOTHING
            """, (understat(r) for r in rows(z, "understat_pre2022.csv")))
            print("understat processed", n)
            # Replace only events for imported archive fixtures, transactionally.
            # This repairs incomplete test fixtures and is safe to rerun.
            cur.execute("""
                DELETE FROM public.archive_understat_goal_events
                WHERE understat_id IN (
                    SELECT understat_id FROM public.archive_understat
                    WHERE match_date < DATE '2022-08-05'
                )
            """)
            n = insert_batches(cur, """
                INSERT INTO public.archive_understat_goal_events
                (understat_id,minute,shot_team_side,result,goal_attribution_verified)
                VALUES (%s,%s,%s,%s,%s)
            """, ((int(r["understat_id"]), int(float(r["minute"])), r["shot_team_side"],
                   r["result"], flag(r["goal_attribution_verified"]))
                  for r in rows(z, "understat_verified_goal_events_pre2022.csv")))
            print("goal events processed", n)
            linked = 0
            unresolved = 0
            conflicts = 0
            for r in rows(z, "cross_source_links_pre2022.csv"):
                if not flag(r["score_agrees"]):
                    conflicts += 1
                    continue
                cur.execute("""
                    SELECT archive_key FROM public.archive_football_data
                    WHERE match_date=%s AND league=%s AND source_file=%s
                    AND lower(home_team)=lower(%s) AND lower(away_team)=lower(%s)
                """, (r["date"], r["football_data_league"], r["football_data_source"],
                      r["home"], r["away"]))
                found = cur.fetchall()
                if len(found) != 1:
                    unresolved += 1
                    continue
                cur.execute("""
                    INSERT INTO public.archive_source_links (understat_id,archive_key,score_agrees)
                    VALUES (%s,%s,true) ON CONFLICT (understat_id) DO NOTHING
                """, (int(r["understat_id"]), found[0][0]))
                linked += 1
            print("links processed", linked, "unresolved", unresolved, "score conflicts", conflicts)
            for table in ("archive_football_data", "archive_understat",
                          "archive_understat_goal_events", "archive_source_links"):
                cur.execute("SELECT count(*) FROM public." + table)
                print(table, cur.fetchone()[0])
        conn.commit()
    print("COMMITTED")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/import_historical_archive.py archive.zip")
    main(sys.argv[1])
