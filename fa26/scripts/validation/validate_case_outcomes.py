#!/usr/bin/env python3
"""Create a reproducible, stratified case-level review sample.

Run from fa26:
    python scripts/validation/validate_case_outcomes.py

After manual annotation, use --score to summarize reviewed labels. The
review is case-level; it is not an estimate of event-level precision.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
STRATA = [
    'no_candidate', 'uncertain_or_partial', 'settlement',
    'dismissal', 'judgment', 'motion_only', 'other_candidate'
]
VALID_COMPLETION = {'yes', 'no', 'unclear'}
VALID_SCOPE = {'whole_case', 'partial', 'unknown'}
VALID_AFFECTED = {'yes', 'no', 'unclear'}
VALID_TYPE = {'dismissal', 'settlement', 'judgment', 'mixed', 'other', 'none', 'unclear'}


def assign_stratum(row):
    n = int(row['candidate_event_count'])
    if n == 0:
        return 'no_candidate'
    if row['any_uncertainty_flag'] or row['any_partial_scope_flag']:
        return 'uncertain_or_partial'
    kinds = set(str(row['candidate_event_types']).split(';'))
    if kinds & {'settlement_reported'}:
        return 'settlement'
    if kinds & {'stipulated_dismissal', 'voluntary_dismissal',
                'dismissal_judgment', 'dismissal_entered', 'dismissal_recorded'}:
        return 'dismissal'
    if kinds & {'judgment_entered', 'judgment_recorded', 'agreement_for_judgment'}:
        return 'judgment'
    if kinds & {'summary_judgment_ruling', 'motion_to_dismiss_ruling'}:
        return 'motion_only'
    return 'other_candidate'


def sample_cases(cases, size, seed):
    rng = np.random.default_rng(seed)
    # Allocate approximately equally across nonempty strata, capped by stratum size.
    groups = {k: cases.loc[cases.stratum.eq(k), 'case_id'].to_numpy()
              for k in STRATA}
    allocations = {k: 0 for k in STRATA}
    remaining = size
    while remaining:
        eligible = [k for k in STRATA if allocations[k] < len(groups[k])]
        if not eligible:
            break
        k = min(eligible, key=lambda x: (allocations[x], STRATA.index(x)))
        allocations[k] += 1
        remaining -= 1
    selected = []
    for k in STRATA:
        if allocations[k]:
            selected.extend(rng.choice(groups[k], size=allocations[k], replace=False).tolist())
    result = cases[cases.case_id.isin(selected)].copy()
    return result.sort_values(['stratum', 'case_id']), allocations


def score_review(path):
    df = pd.read_csv(path, dtype={'review_completed_disposition': 'string',
                                  'review_disposition_type': 'string',
                                  'review_scope': 'string',
                                  'review_municipality_affected': 'string'})
    for col, allowed in [
        ('review_completed_disposition', VALID_COMPLETION),
        ('review_disposition_type', VALID_TYPE),
        ('review_scope', VALID_SCOPE),
        ('review_municipality_affected', VALID_AFFECTED),
    ]:
        invalid = df[col].dropna().str.strip().str.lower()
        invalid = invalid[(invalid != '') & (~invalid.isin(allowed))]
        if len(invalid):
            raise ValueError(f'Invalid values in {col}: {invalid.unique().tolist()}')
    df['review_completed_disposition'] = df['review_completed_disposition'].fillna('').str.strip().str.lower()
    reviewed = df[df.review_completed_disposition.isin(VALID_COMPLETION)].copy()
    print(f'Reviewed cases: {len(reviewed):,} / {len(df):,}')
    if reviewed.empty:
        return
    print(pd.crosstab(reviewed.stratum, reviewed.review_completed_disposition,
                      margins=True).to_string())
    # Proxy precision: among sampled cases with candidate events, fraction
    # judged to have completed disposition. Not event precision or recall.
    positives = reviewed[(reviewed.candidate_event_count > 0) &
                         (reviewed.review_completed_disposition.isin({'yes', 'no'}))]
    if len(positives):
        print(f'Candidate-case completed-disposition confirmation: '
              f'{positives.review_completed_disposition.eq("yes").mean():.1%} '
              f'(n={len(positives)}; stratified, unweighted)')
    negatives = reviewed[(reviewed.candidate_event_count == 0) &
                         (reviewed.review_completed_disposition.isin({'yes', 'no'}))]
    if len(negatives):
        print(f'No-candidate cases with missed completed disposition: '
              f'{negatives.review_completed_disposition.eq("yes").mean():.1%} '
              f'(n={len(negatives)}; not overall recall)')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases', type=Path, default=ROOT / 'data/analysis/municipal_case_outcomes.csv')
    p.add_argument('--events', type=Path, default=ROOT / 'data/analysis/municipal_outcome_events.csv')
    p.add_argument('--actions', type=Path, default=ROOT / 'data/analysis/municipal_defendant_actions.csv')
    p.add_argument('--output-dir', type=Path, default=ROOT / 'data/validation')
    p.add_argument('--sample-size', type=int, default=280)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--score', type=Path, help='Score a manually annotated outcome_review_cases.csv')
    args = p.parse_args()
    if args.score:
        score_review(args.score)
        return
    if args.sample_size < 1:
        p.error('--sample-size must be positive')

    cases = pd.read_csv(args.cases, low_memory=False)
    events = pd.read_csv(args.events, low_memory=False)
    actions = pd.read_csv(args.actions, low_memory=False)
    required = {
        'cases': (cases, {'case_id', 'candidate_event_count', 'candidate_event_types',
                          'any_uncertainty_flag', 'any_partial_scope_flag'}),
        'events': (events, {'case_id', 'source_row', 'candidate_event'}),
        'actions': (actions, {'case_id', 'docket_date', 'action', 'docket_text'}),
    }
    for name, (df, cols) in required.items():
        if missing := cols - set(df.columns):
            p.error(f'{name} missing: {sorted(missing)}')
        df['case_id'] = pd.to_numeric(df.case_id, errors='coerce').astype('Int64')

    cases = cases.dropna(subset=['case_id']).drop_duplicates('case_id').copy()
    cases['candidate_event_count'] = pd.to_numeric(cases.candidate_event_count, errors='coerce').fillna(0).astype(int)
    for col in ['any_uncertainty_flag', 'any_partial_scope_flag']:
        cases[col] = cases[col].astype('string').str.lower().eq('true').fillna(False)
    cases['stratum'] = cases.apply(assign_stratum, axis=1)
    sample, allocations = sample_cases(cases, args.sample_size, args.seed)
    sample['review_completed_disposition'] = ''
    sample['review_disposition_type'] = ''
    sample['review_scope'] = ''
    sample['review_municipality_affected'] = ''
    sample['review_prejudice'] = ''
    sample['review_outcome_date'] = ''
    sample['review_evidence_sufficient'] = ''
    sample['review_notes'] = ''

    selected = set(sample.case_id.astype(int))
    history = actions[actions.case_id.isin(selected)].copy()
    history['docket_date'] = pd.to_datetime(history.docket_date, errors='coerce')
    history['source_row'] = history.index
    matches = events[events.case_id.isin(selected)].groupby(['case_id', 'source_row'], dropna=False).agg(
        matched_candidate_types=('candidate_event', lambda s: ';'.join(sorted(set(s.dropna().astype(str)))))
    ).reset_index()
    history = history.merge(matches, how='left', on=['case_id', 'source_row'])
    history['matched_candidate_types'] = history.matched_candidate_types.fillna('')
    history['is_candidate_event'] = history.matched_candidate_types.ne('')
    history = history.sort_values(['case_id', 'docket_date', 'source_row'], kind='stable')
    history['docket_sequence'] = history.groupby('case_id').cumcount() + 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    sample.to_csv(args.output_dir / 'outcome_review_cases.csv', index=False)
    history.to_csv(args.output_dir / 'outcome_review_dockets.csv', index=False)
    counts = cases.groupby('stratum').size().rename('population_cases').reset_index()
    counts['sampled_cases'] = counts.stratum.map(allocations).fillna(0).astype(int)
    counts['seed'] = args.seed
    counts.to_csv(args.output_dir / 'outcome_validation_summary.csv', index=False)
    print(f'Sampled {len(sample):,} distinct cases; {len(history):,} docket rows')
    print(counts.to_string(index=False))
    print(f'Wrote outputs to {args.output_dir}')
    print('Review cases using the full chronological docket history; do not assume the latest keyword match is final.')

if __name__ == '__main__':
    main()