#!/usr/bin/env python3
"""Join v2 outcomes to the master municipality-case table (no database required).

Run from any directory: python scripts/masscourts/integrate_municipal_outcomes.py
Writes a separate research-ready file without overwriting source datasets.
"""
from pathlib import Path
import os
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MC = Path(os.environ.get('LITIGATION_REBUILD_DIR', str(ROOT / 'data/processed/masscourts')))
OUTCOME_PATH = Path(os.environ.get('MUNICIPAL_OUTCOMES_V2', str(ROOT / 'data/analysis/outcomes_v2/municipal_case_outcomes_enriched.csv')))
OUTPUT = ROOT / 'data/analysis/municipal_cases_with_outcomes.csv'
KEYS = ['case_id', 'municipality_key']

def normalize(df, name):
    for key in ('case_id', 'municipality'):
        if key not in df:
            raise ValueError(f'{name} missing {key}')
    df = df.copy()
    df['case_id'] = df['case_id'].astype('string').str.strip()
    df['municipality_key'] = df['municipality'].astype('string').str.strip().str.casefold()
    if df[KEYS].isna().any().any():
        raise ValueError(f'{name} contains missing join keys')
    if df.duplicated(KEYS).any():
        examples = df.loc[df.duplicated(KEYS, keep=False), KEYS].head(8)
        raise ValueError(f'{name} has duplicate case/municipality keys:\n{examples}')
    return df

def main():
    cases = normalize(pd.read_csv(MC / 'municipal_cases.csv', dtype={'case_id': str, 'dor_code': str}), 'master cases')
    outcomes = normalize(pd.read_csv(OUTCOME_PATH, dtype={'case_id': str, 'dor_code': str}), 'v2 outcomes')
    selected = ['v2_disposition_type', 'v2_municipality_outcome', 'v2_finality', 'v2_basis',
                'disposition_scope', 'disposition_date', 'review_flags', 'structured_judgment_count',
                'linked_judgment_count', 'latest_linked_judgment_date', 'evidence_count',
                'evidence_text', 'municipal_party_ids']
    available = [x for x in selected if x in outcomes]
    # Prefix all outcome fields, preventing accidental overwrite of master metadata.
    outcome_slice = outcomes[KEYS + available].rename(columns={x: 'outcome_' + x for x in available})
    merged = cases.merge(outcome_slice, on=KEYS, how='left', validate='one_to_one', indicator=True)
    merged['outcome_v2_matched'] = merged['_merge'].eq('both')
    merged = merged.drop(columns=['_merge', 'municipality_key'])
    extra = outcomes.merge(cases[KEYS], on=KEYS, how='left', indicator=True)
    unmatched_outcomes = extra['_merge'].eq('left_only').sum()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT, index=False)
    print(f'Master municipality-case rows: {len(cases):,}')
    print(f'V2 municipality-case rows: {len(outcomes):,}')
    print(f'Matched master rows: {merged.outcome_v2_matched.sum():,}')
    print(f'Unmatched master rows: {(~merged.outcome_v2_matched).sum():,}')
    print(f'V2 rows absent from master: {unmatched_outcomes:,}')
    print(f'Wrote: {OUTPUT}')
    if unmatched_outcomes:
        print('NOTE: v2 has case-municipality pairs absent from the master; inspect role/universe differences.')

if __name__ == '__main__':
    main()
