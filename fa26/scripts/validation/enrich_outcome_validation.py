#!/usr/bin/env python3
"""Add municipal case metadata to an EXISTING outcome review sample.
Optional DB enrichment (requires DATABASE_URL and psycopg2):
    python scripts/validation/enrich_outcome_validation.py --fetch-db
"""
import argparse
import os
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ['case_number','case_title','case_type','file_date','filing_year',
          'municipality','dor_code','municipal_party_roles','has_defendant',
          'case_status','status_date','initiating_action']

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--review-dir', type=Path, default=ROOT/'data/validation')
    p.add_argument('--municipal-cases', type=Path, default=ROOT/'data/analysis/municipal_cases.csv')
    p.add_argument('--fetch-db', action='store_true')
    args = p.parse_args()
    cases_path = args.review_dir/'outcome_review_cases.csv'
    dockets_path = args.review_dir/'outcome_review_dockets.csv'
    reviews = pd.read_csv(cases_path, dtype={'case_id':'Int64'}, low_memory=False)
    dockets = pd.read_csv(dockets_path, dtype={'case_id':'Int64'}, low_memory=False)
    metadata = pd.read_csv(args.municipal_cases, dtype={'case_id':'Int64','dor_code':'string'}, low_memory=False)
    for df, name in [(reviews,'review cases'),(dockets,'dockets'),(metadata,'municipal cases')]:
        if 'case_id' not in df:
            p.error(f'{name} lacks case_id')
    # Multiple municipality rows may refer to the same case. Preserve them as a
    # semicolon-separated list rather than duplicating sampled cases.
    fields = [c for c in FIELDS if c in metadata and c not in ('case_status','status_date','initiating_action')]
    def collapse(s):
        vals = list(dict.fromkeys(str(v) for v in s.dropna() if str(v).strip()))
        return '; '.join(vals) if vals else pd.NA
    meta = metadata.loc[metadata.case_id.isin(reviews.case_id), ['case_id']+fields]
    meta = meta.groupby('case_id', as_index=False).agg({c:collapse for c in fields})
    if args.fetch_db:
        if not os.getenv('DATABASE_URL'):
            p.error('DATABASE_URL environment variable is required for --fetch-db')
        import psycopg2
        ids = reviews.case_id.dropna().astype('int64').tolist()
        with psycopg2.connect(os.environ['DATABASE_URL']) as conn:
            with conn.cursor() as cur:
                cur.execute('''SELECT case_id, case_status, status_date, initiating_action
                               FROM public.cases WHERE case_id = ANY(%s::bigint[])''', (ids,))
                db = pd.DataFrame(cur.fetchall(), columns=['case_id','case_status','status_date','initiating_action'])
        db['case_id'] = pd.to_numeric(db.case_id, errors='coerce').astype('Int64')
        meta = meta.merge(db.drop_duplicates('case_id'), on='case_id', how='left', validate='one_to_one')
    for c in FIELDS:
        if c not in meta:
            meta[c] = pd.NA
    # Re-runs replace previous metadata columns without losing annotations.
    existing = [c for c in FIELDS if c in reviews]
    reviews = reviews.drop(columns=existing).merge(meta[['case_id']+FIELDS], on='case_id', how='left', validate='one_to_one')
    # Place identifying metadata immediately after case_id.
    front = ['case_id']+FIELDS
    reviews = reviews[front+[c for c in reviews if c not in front]]
    dockets = dockets.drop(columns=[c for c in FIELDS if c in dockets]).merge(meta[['case_id']+FIELDS], on='case_id', how='left', validate='many_to_one')
    front = ['case_id']+FIELDS
    dockets = dockets[front+[c for c in dockets if c not in front]]
    assert len(reviews)==len(pd.read_csv(cases_path))
    assert len(dockets)==len(pd.read_csv(dockets_path))
    reviews.to_csv(cases_path, index=False)
    dockets.to_csv(dockets_path, index=False)
    print(f'Enriched {len(reviews):,} review cases and {len(dockets):,} docket rows')
    print(f'Case metadata matches: {reviews.case_number.notna().sum():,}/{len(reviews):,}')
    print('Database fields:', 'queried' if args.fetch_db else 'blank (run with --fetch-db)')
    print('Saved:', cases_path, 'and', dockets_path)

if __name__ == '__main__':
    main()
