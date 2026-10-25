#!/usr/bin/env python3
"""Read-only MassCourtsPlus case context for unresolved municipal party IDs.

Run from fa26 directory:
  python scripts/masscourts/extract_municipal_entity_case_context.py --input data/processed/masscourts/validation/initial/municipal_entities_uncertain_researched.csv
Requires: pip install psycopg2-binary
Set DATABASE_URL to the read-only Neon PostgreSQL connection string.
"""
import argparse
import csv
import os
from pathlib import Path
import psycopg2


ROOT = Path(__file__).resolve().parents[2]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--output', type=Path, default=ROOT / 'data' / 'processed' / 'masscourts' / 'validation' / 'case_context' / 'municipal_entity_case_context.csv')
    ap.add_argument('--max-cases', type=int, default=12)
    ap.add_argument('--all-29', action='store_true', help='Include previously provisionally resolved rows')
    args = ap.parse_args()
    if args.max_cases < 1: ap.error('--max-cases must be positive')
    with args.input.open(newline='', encoding='utf-8-sig') as f:
        entries = list(csv.DictReader(f))
    if not args.all_29:
        entries = [r for r in entries if (r.get('verified_label') or '').strip().lower() == 'uncertain']
    if not entries:
        ap.error('No unresolved records found; check verified_label column or use --all-29')
    url = os.getenv('DATABASE_URL') or os.getenv('MASSCOURTS_DATABASE_URL')
    if not url: ap.error('Set DATABASE_URL or MASSCOURTS_DATABASE_URL for read-only PostgreSQL access')
    fields = ['party_id','validation_party_name','verified_label','case_id','case_number','case_title','case_type','file_date','case_status','court_department','court_division','party_type','database_party_name','other_parties','case_context_status']
    rows = []
    with psycopg2.connect(url, connect_timeout=15, options='-c statement_timeout=90000 -c default_transaction_read_only=on') as conn:
        with conn.cursor() as cur:
            for i, entry in enumerate(entries, 1):
                pid = int(entry['party_id'])
                cur.execute('''
                    SELECT c.case_id, c.case_number, c.case_title, c.case_type,
                           c.file_date, c.case_status, ch.court_department, ch.court_division,
                           cp.party_type, p.party_name
                    FROM case_parties cp
                    JOIN cases c ON c.case_id = cp.case_id
                    LEFT JOIN courthouses ch ON ch.courthouse_id = c.courthouse_id
                    LEFT JOIN parties p ON p.party_id = cp.party_id
                    WHERE cp.party_id = %s
                    ORDER BY c.file_date DESC NULLS LAST, c.case_id DESC
                    LIMIT %s
                ''', (pid, args.max_cases))
                cases = cur.fetchall()
                for case in cases:
                    case_id = case[0]
                    cur.execute('''
                        SELECT p.party_name, cp.party_type
                        FROM case_parties cp
                        JOIN parties p ON p.party_id = cp.party_id
                        WHERE cp.case_id = %s AND cp.party_id <> %s
                        ORDER BY cp.party_id
                        LIMIT 20
                    ''', (case_id, pid))
                    others = '; '.join(f'{name} ({role})' if role else str(name) for name, role in cur.fetchall())
                    rows.append(dict(zip(fields, [pid, entry['party_name'], entry.get('verified_label',''), *[str(x) if x is not None else '' for x in case], others, 'case_found'])))
                if not cases:
                    rows.append(dict(zip(fields, [pid, entry['party_name'], entry.get('verified_label',''), *([''] * 10), '', 'no_case_found'])))
                print(f'[{i}/{len(entries)}] {pid}: {len(cases)} cases')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
    print(f'Wrote {len(rows)} rows to {args.output}')

if __name__ == '__main__':
    main()
