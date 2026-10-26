#!/usr/bin/env python3
"""Produce review-only typo audit and deterministic sample of newly matched officials."""
import argparse
import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data" / "processed" / "masscourts"

ALIASES = {
    'middleboro': 'Middleborough', 'worceser': 'Worcester', 'worcster': 'Worcester',
    'worceter': 'Worcester', 'adamas': 'Adams', 'leoaminster': 'Leominster',
    'westboro': 'Westborough', 'foxorough': 'Foxborough', 'northboro': 'Northborough',
    'southbrige': 'Southbridge', 'northhampton': 'Northampton',
    'acusnet': 'Acushnet', 'stroughton': 'Stoughton', 'wentham': 'Wenham',
    'quiincy': 'Quincy', 'somerille': 'Somerville', 'lincon': 'Lincoln',
    'wetport': 'Westport', 'billericca': 'Billerica',
}


def read_registry(folder):
    frames=[]
    for status in ('matched','review','excluded'):
        p=folder/f'municipal_entities_{status}.csv'
        x=pd.read_csv(p,dtype={'party_id':str,'dor_code':str},keep_default_na=False)
        if x.party_id.duplicated().any(): raise ValueError(f'Duplicate party IDs in {p}')
        frames.append(x)
    result=pd.concat(frames,ignore_index=True)
    if result.party_id.duplicated().any(): raise ValueError('Duplicate IDs across statuses')
    return result


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base',type=Path,default=BASE)
    ap.add_argument('--out',type=Path,default=BASE / 'validation' / 'v36_audit')
    ap.add_argument('--sample-size',type=int,default=100)
    ap.add_argument('--seed',type=int,default=20261025)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    current=read_registry(a.base/'versions'/'v36')
    original=read_registry(a.base/'versions'/'v33')
    prev=original[['party_id','match_status']].rename(columns={'match_status':'v33_status'})
    new=current.merge(prev,on='party_id',how='left',validate='one_to_one')
    promoted=new[(new.v33_status!='matched')&(new.match_status=='matched')].copy()
    officials=promoted[promoted.municipal_relationship.str.contains('official',case=False,na=False)].copy()
    if officials.empty:
        print('WARNING: no newly matched official-capacity parties; check relationship names')
    sample=officials.sample(n=min(a.sample_size,len(officials)),random_state=a.seed).copy()
    for field in ('manual_label','case_context_evidence','reviewer_notes','reviewed_by'):
        sample[field]=''
    sample['review_status']='pending_independent_review'
    sample.to_csv(a.out/'new_official_capacity_sample.csv',index=False)
    excluded=current[current.match_status=='excluded'].copy()
    audit=[]
    for _,r in excluded.iterrows():
        name=str(r.party_name)
        norm=re.sub(r'[^a-z0-9]+',' ',name.lower())
        hits=[(alias,municipality) for alias,municipality in ALIASES.items()
              if re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',norm)]
        for alias,municipality in hits:
            audit.append({'party_id':r.party_id,'party_name':name,'suspected_alias':alias,
                          'proposed_municipality':municipality,'current_status':r.match_status,
                          'review_status':'needs_manual_verification',
                          'case_context_checked':'no','verified_municipality':'',
                          'reviewer_notes':''})
    pd.DataFrame(audit,columns=['party_id','party_name','suspected_alias','proposed_municipality',
       'current_status','review_status','case_context_checked','verified_municipality','reviewer_notes']).to_csv(
       a.out/'excluded_typo_candidates.csv',index=False)
    print(f'V3.3->V3.6 newly matched: {len(promoted)}')
    print(f'Newly matched official-capacity candidates: {len(officials)}')
    print(f'Independent-review sample: {len(sample)}')
    print(f'Excluded typo candidates: {len(audit)}')
    print('Files saved in',a.out)

if __name__=='__main__':main()
