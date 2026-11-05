#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import pandas as pd
import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[2]


def table_columns(cur, table):
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_schema='public' AND table_name=%s
                   ORDER BY ordinal_position""", (table,))
    return [r[0] for r in cur.fetchall()]


def fetch_table(cur, table, case_ids):
    cols = table_columns(cur, table)
    if not cols or 'case_id' not in cols:
        print(f"Skipping public.{table}: missing table or case_id column")
        return pd.DataFrame()
    cur.execute(sql.SQL('SELECT * FROM {}.{} WHERE case_id = ANY(%s::bigint[])').format(
        sql.Identifier('public'), sql.Identifier(table)), (case_ids,))
    return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--queue', type=Path, default=ROOT/'data/validation/municipal_outcome_party_review_queue.csv')
    ap.add_argument('--out', type=Path, default=ROOT/'data/validation/structured_outcomes')
    args = ap.parse_args()
    if not args.queue.exists():
        ap.error(f'Queue not found: {args.queue}; use --queue to specify its path')
    if not os.getenv('DATABASE_URL'):
        ap.error('DATABASE_URL environment variable is required')
    queue = pd.read_csv(args.queue)
    ids = pd.to_numeric(queue['case_id'], errors='coerce').dropna().astype('int64').unique().tolist()
    print(f'Fetching structured records for {len(ids)} case IDs')
    args.out.mkdir(parents=True, exist_ok=True)
    with psycopg2.connect(os.environ['DATABASE_URL']) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            for table in ('case_parties', 'judgments', 'judgment_awards'):
                df = fetch_table(cur, table, ids)
                df.to_csv(args.out/f'{table}.csv', index=False)
                print(f'{table}: {len(df):,} rows')
            # Fetch party name records if a public.parties table with party_id exists.
            party_cols = table_columns(cur, 'parties')
            cp = pd.read_csv(args.out/'case_parties.csv')
            if 'party_id' in party_cols and 'party_id' in cp.columns:
                pids = pd.to_numeric(cp.party_id, errors='coerce').dropna().astype('int64').unique().tolist()
                cur.execute('SELECT * FROM public.parties WHERE party_id = ANY(%s::bigint[])', (pids,))
                df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
                df.to_csv(args.out/'parties.csv', index=False)
                print(f'parties: {len(df):,} rows')
            else:
                print('No compatible public.parties table; case_parties.csv retains available party fields')
    print(f'Files written to {args.out}')

if __name__ == '__main__':
    main()
