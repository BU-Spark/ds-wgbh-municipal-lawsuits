from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'data' / 'processed' / 'masscourts'
VALIDATION = BASE / 'validation' / 'case_context'
INITIAL = BASE / 'validation' / 'initial'
INITIAL.mkdir(parents=True, exist_ok=True)
VALIDATION.mkdir(parents=True, exist_ok=True)

review_path = VALIDATION / 'municipal_entity_case_context_review.csv'
if not review_path.exists():
    review_path = ROOT / 'municipal_entity_case_context_review.csv'
if not review_path.exists():
    # Previously generated overrides retain the reviewed categories and notes.
    review_path = VALIDATION / 'municipal_entity_case_context_overrides.csv'
    if review_path.exists():
        print('Review CSV missing; reusing existing reviewed overrides:', review_path)
    else:
        raise SystemExit(
            'No reviewed classifications found. Place municipal_entity_case_context_review.csv '
            f'in {ROOT} or {VALIDATION}. '
            'Required columns: party_id, party_name, entity_category. '
            'municipal_entity_case_context.csv contains case context, not reviewed categories.'
        )

review = pd.read_csv(review_path, dtype={'party_id':str, 'dor_code':str})
required_columns = {'party_id', 'party_name', 'entity_category'}
missing_columns = required_columns - set(review.columns)
if missing_columns:
    raise SystemExit(f'{review_path}: missing required columns: {", ".join(sorted(missing_columns))}')
if review.empty or review[list(required_columns)].isna().any().any():
    raise SystemExit(f'{review_path}: reviewed classifications must contain nonempty party IDs, names, and categories')
if not review.party_id.is_unique:
    raise SystemExit(f'{review_path}: each party_id must have exactly one reviewed classification')
rows = []
for _, r in review.iterrows():
    cat = r['entity_category']
    if cat == 'municipal_body_with_named_official':
        decision, attribution, confidence = 'include', 'single_municipality', 'high'
    elif cat == 'named_municipal_official':
        decision, attribution, confidence = 'include_official_capacity', 'single_municipality', 'medium'
    elif cat == 'municipal_housing_trust':
        decision, attribution, confidence = 'review_separate_entity', 'single_municipality', 'medium'
    elif cat == 'joint_municipal_police_department_agent':
        decision, attribution, confidence = 'review_joint_attribution', 'multiple_municipalities', 'medium'
    else:
        decision, attribution, confidence = 'unresolved', 'unknown', 'low'
    rows.append({'party_id':str(r['party_id']), 'party_name':r['party_name'],
                 'entity_category':cat, 'inclusion_decision':decision,
                 'attribution_rule':attribution,
                 'identified_municipality':r.get('identified_municipality'),
                 'review_confidence':confidence, 'evidence':'case_title_and_party_name',
                 'case_context_note':r.get('case_context_note'),
                 'requires_manual_review':decision in ('review_separate_entity','review_joint_attribution','unresolved')})
overrides = pd.DataFrame(rows)
assert overrides.party_id.is_unique
out = VALIDATION / 'municipal_entity_case_context_overrides.csv'
overrides.to_csv(out,index=False)
print('Wrote:',out)
print(overrides.inclusion_decision.value_counts().to_string())

# Apply only as annotations, without silently changing registry membership or case counts.
files = [BASE / 'versions' / 'v33' / f'municipal_entities_{s}.csv' for s in ('matched','review','excluded')]
for src in files:
    if not src.exists():
        print('Skipped missing registry:',src)
        continue
    registry = pd.read_csv(src, dtype={'party_id':str,'dor_code':str})
    registry = registry.merge(overrides.drop(columns=['party_name']),on='party_id',how='left',validate='many_to_one')
    dest = INITIAL / (src.stem + '_annotated.csv')
    registry.to_csv(dest,index=False)
    print('Wrote:',dest,'affected:',registry.inclusion_decision.notna().sum())
print('Existing registry and litigation panel were NOT overwritten.')
