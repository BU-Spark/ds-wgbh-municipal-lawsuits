#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

def read(path):
    if not path.exists():
        raise SystemExit(f"Missing required input: {path}")
    return pd.read_csv(path, dtype={'case_id':'string'}, low_memory=False).fillna('')

def norm(x):
    return re.sub(r'\s+', ' ', str(x).strip().lower().replace('_',' '))

def disposition(x):
    s=norm(x)
    if not s or s in ('unknown','none','nan'): return 'unknown'
    if 'tax lien' in s: return 'tax_lien_judgment'
    if 'settlement signal' in s or 'unconfirmed' in s: return 'settlement_unconfirmed'
    if 'settlement' in s or 'settled' in s: return 'settlement'
    if 'dismiss' in s and ('judgment' in s or 'summary' in s): return 'judgment_and_dismissal'
    if 'dismiss' in s: return 'dismissal'
    if 'judgment' in s: return 'judgment'
    return 'other'

def outcome(x):
    s=norm(x)
    if s in ('municipality favored','favored'): return 'municipality_favored'
    if s in ('municipality adverse','adverse'): return 'municipality_adverse'
    if s in ('dismissal involving municipality',): return 'dismissal_involving_municipality'
    if s in ('settled','settlement'): return 'settled'
    return 'unknown'

def flagged(s, token):
    return token in str(s).split('|')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--v2',type=Path,default=ROOT/'data/analysis/outcomes_v2/municipal_case_outcomes_enriched.csv')
    p.add_argument('--review',type=Path,default=ROOT/'data/validation/outcome_review_cases.csv')
    p.add_argument('--strata',type=Path,default=ROOT/'data/validation/outcome_validation_summary.csv')
    p.add_argument('--final180',type=Path,default=ROOT/'data/validation/municipal_case_outcomes_final_180.csv')
    p.add_argument('--changes',type=Path,default=ROOT/'data/analysis/outcomes_v2/classification_changes.csv')
    p.add_argument('--judgments',type=Path,default=ROOT/'data/analysis/outcomes_v2/structured_judgment_audit.csv')
    p.add_argument('--dockets',type=Path,default=ROOT/'data/validation/outcome_review_dockets.csv')
    p.add_argument('--out',type=Path,default=ROOT/'data/validation/outcomes_v2')
    a=p.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    v=read(a.v2); r=read(a.review)
    for c in ('case_id','municipality','v2_disposition_type','v2_municipality_outcome','review_flags'):
        if c not in v: raise SystemExit(f'v2 missing column {c}')
    if 'case_id' not in r or 'stratum' not in r: raise SystemExit('review must include case_id and stratum')
    if r.case_id.duplicated().any(): raise SystemExit('Review has duplicate case IDs')
    if v.duplicated(['case_id','municipality']).any(): raise SystemExit('v2 has duplicate case/municipality rows')
    v['pred_disposition']=v.v2_disposition_type.map(disposition)
    v['pred_outcome']=v.v2_municipality_outcome.map(outcome)
    v['has_review_flag']=v.review_flags.astype(str).str.len().gt(0)
    v['flag_reversal']=v.review_flags.map(lambda s: flagged(s,'possible_later_reversal_or_modification'))
    v['flag_conflict']=v.review_flags.map(lambda s: flagged(s,'multiple_judgment_directions'))
    v['flag_party_unmatched']=v.review_flags.map(lambda s: flagged(s,'municipal_defendant_party_id_unmatched'))
    v['flag_unattributed']=v.review_flags.map(lambda s: flagged(s,'structured_judgment_not_attributed_to_municipality'))
    # Join by case only to preserve all municipality-specific rows in multi-town cases.
    sample=v.merge(r, on='case_id', how='inner',suffixes=('','_review'),validate='many_to_one')
    if sample.empty: raise SystemExit('No matching case IDs between v2 and review')
    sample['sample_case_count_weight']=1/sample.groupby('case_id').case_id.transform('size')
    # Review fields may be blank: never equate blank with unknown truth.
    truth_disp=r.get('review_disposition_type',pd.Series('',index=r.index)).astype(str)
    truth_out=r.get('municipality_outcome',pd.Series('',index=r.index)).astype(str)
    review_completed=r.get('review_completed_disposition',pd.Series('',index=r.index)).astype(str).str.strip().str.lower()
    sufficient=r.get('review_evidence_sufficient',pd.Series('',index=r.index)).astype(str).str.strip().str.lower()
    r['reference_disposition']=truth_disp.map(disposition)
    r['reference_outcome']=truth_out.map(outcome)
    # Only explicitly reviewed rows with sufficient evidence are candidates for scoring.
    yes={'true','yes','1','y'}
    r['review_explicit']=review_completed.isin(yes) & sufficient.isin(yes)
    r['score_disposition']=r.review_explicit & r.reference_disposition.ne('unknown')
    # Outcome field in the original review is often an *automated* prediction.
    # Do not score municipality outcomes from it without a separate verified field.
    sample=sample.drop(columns=[c for c in ('reference_disposition','reference_outcome','review_explicit','score_disposition') if c in sample],errors='ignore')
    sample=sample.merge(r[['case_id','reference_disposition','reference_outcome','review_explicit','score_disposition']],on='case_id',how='left',validate='many_to_one')
    sample['disposition_agrees']=sample.pred_disposition.eq(sample.reference_disposition).where(sample.score_disposition,pd.NA)
    sample.to_csv(a.out/'stratified_case_comparison.csv',index=False)
    # No outcome agreement computed: 280 sample has no independently adjudicated labels.
    strata=read(a.strata) if a.strata.exists() else pd.DataFrame()
    strata_rows=[]
    for name,g in r.groupby('stratum',dropna=False):
        matching=sample[sample.stratum.eq(name)]
        checked=matching[matching.score_disposition]
        row={'stratum':name,'sampled_cases':g.case_id.nunique(), 'matched_cases':matching.case_id.nunique(),
             'scorable_disposition_cases':checked.case_id.nunique(),
             'scorable_disposition_rows':len(checked),
             'disposition_row_agreement':checked.disposition_agrees.astype(float).mean() if len(checked) else None,
             'outcome_gold_standard_available':False}
        if len(strata) and 'stratum' in strata and 'population_cases' in strata:
            pop=strata.loc[strata.stratum.eq(name),'population_cases']
            row['population_cases']=int(pd.to_numeric(pop,errors='coerce').iloc[0]) if len(pop) and pd.notna(pd.to_numeric(pop,errors='coerce').iloc[0]) else None
        strata_rows.append(row)
    pd.DataFrame(strata_rows).to_csv(a.out/'stratified_validation_summary.csv',index=False)
    # Compare to 180 provisional adjudications; explicitly mark as non-independent.
    if a.final180.exists():
        f=read(a.final180)
        if {'case_id','municipality','final_municipality_outcome'}.issubset(f):
            f=f[['case_id','municipality','final_municipality_outcome','final_disposition_type','final_finality']].drop_duplicates(['case_id','municipality'])
            compare=v.merge(f,on=['case_id','municipality'],how='inner',validate='one_to_one')
            compare['provisional_outcome']=compare.final_municipality_outcome.map(outcome)
            compare['provisional_disposition']=compare.final_disposition_type.map(disposition)
            compare['outcome_agrees_provisional']=compare.pred_outcome.eq(compare.provisional_outcome)
            compare['disposition_agrees_provisional']=compare.pred_disposition.eq(compare.provisional_disposition)
            compare.to_csv(a.out/'provisional_180_comparison.csv',index=False)
    # Priority queue: conflicts and reversals first, then changed classifications.
    changes=read(a.changes) if a.changes.exists() else pd.DataFrame()
    change_keys=set(zip(changes.case_id.astype(str),changes.municipality.astype(str))) if {'case_id','municipality'}.issubset(changes) else set()
    v['classification_changed']= [ (str(c),str(m)) in change_keys for c,m in zip(v.case_id,v.municipality)]
    v['audit_priority']=v.flag_conflict.astype(int)*100+v.flag_reversal.astype(int)*50+v.classification_changed.astype(int)*20+v.flag_party_unmatched.astype(int)*10+v.flag_unattributed.astype(int)*5
    queue=v[v.audit_priority.gt(0)].sort_values(['audit_priority','case_id'],ascending=[False,True])
    keep=['case_id','municipality','case_number','case_type','v2_disposition_type','v2_municipality_outcome','v2_finality','v2_basis','review_flags','classification_changed','audit_priority','evidence_text']
    queue[[c for c in keep if c in queue]].to_csv(a.out/'priority_audit_queue.csv',index=False)
    # Audit judgment chronology using judgment date and selected disposition date.
    if a.judgments.exists():
        j=read(a.judgments)
        if {'case_id','municipality','date'}.issubset(j):
            jj=j.merge(v[['case_id','municipality','disposition_date','v2_finality','review_flags']],on=['case_id','municipality'],how='left',validate='many_to_one')
            jj['judgment_date_parsed']=pd.to_datetime(jj.date,errors='coerce')
            jj['selected_date_parsed']=pd.to_datetime(jj.disposition_date,errors='coerce')
            jj['judgment_after_selected_docket_event']=(jj.judgment_date_parsed>jj.selected_date_parsed).where(jj.selected_date_parsed.notna() & jj.judgment_date_parsed.notna(),pd.NA)
            jj.to_csv(a.out/'judgment_chronology_audit.csv',index=False)
    if a.dockets.exists():
        d=read(a.dockets)
        if {'case_id','docket_date','docket_text'}.issubset(d):
            risk=sample.loc[sample.flag_reversal | sample.flag_conflict,['case_id','municipality','review_flags']].drop_duplicates()
            dd=d.merge(risk,on='case_id',how='inner',validate='many_to_many')
            dd=dd.sort_values(['case_id','docket_date'])
            dd.to_csv(a.out/'flagged_sample_docket_chronology.csv',index=False)
    report=[f'Full v2 rows: {len(v):,}; cases: {v.case_id.nunique():,}',
            f'Stratified sample cases matched: {sample.case_id.nunique():,} of {r.case_id.nunique():,}',
            f'Scorable independently reviewed disposition cases: {sample.loc[sample.score_disposition,"case_id"].nunique():,}',
            'Municipality-outcome accuracy: NOT ESTIMABLE from current 280-case review fields.',
            'Provisional 180-case comparison is diagnostic only, not independent validation.',
            f'Priority audit queue: {len(queue):,} municipality-case rows.',
            'Reversal flags indicate possible chronology issues, not verified reversals.',
            'Do not use sample-weighted accuracy until independent reference labels exist for all strata.']
    (a.out/'validation_readme.txt').write_text('\n'.join(report)+'\n')
    print('\n'.join(report));print('Wrote:',a.out)
if __name__=='__main__': main()
