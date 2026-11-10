#!/usr/bin/env python3
import argparse
import os
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

def norm(x):
    return re.sub(r'[^a-z0-9]+', ' ', str(x).lower()).strip()

def municipality_match(name, municipality):
    """Strict official-name match; avoid matching arbitrary private parties."""
    n, m = norm(name), norm(municipality)
    if not n or not m or n in ('nan', 'none'):
        return False
    allowed = {m, 'city of '+m, 'town of '+m, 'municipality of '+m,
               m+' city', m+' town', 'the city of '+m, 'the town of '+m}
    # Name variants such as 'City of X, Massachusetts' are acceptable.
    allowed |= {a+' massachusetts' for a in list(allowed)}
    return n in allowed

def load_db(ids, chunk_size):
    try:
        import psycopg2
    except ImportError as exc:
        raise SystemExit('Install psycopg2-binary or use --offline') from exc
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise SystemExit('DATABASE_URL is required unless --offline is supplied')
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    rows = {'judgments': [], 'case_parties': [], 'parties': []}
    try:
        with conn.cursor() as cur:
            for start in range(0, len(ids), chunk_size):
                batch = [int(i) for i in ids[start:start+chunk_size]]
                cur.execute('SELECT judgment_id, case_id, judgment_date, judgment_type, judgment_method, for_party_id, against_party_id FROM public.judgments WHERE case_id = ANY(%s::bigint[])', (batch,))
                rows['judgments'].extend(cur.fetchall())
                cur.execute('SELECT case_id, party_id, party_type FROM public.case_parties WHERE case_id = ANY(%s::bigint[])', (batch,))
                rows['case_parties'].extend(cur.fetchall())
                print(f'Database batch {min(start+chunk_size,len(ids)):,}/{len(ids):,}', flush=True)
            pids = sorted({int(r[1]) for r in rows['case_parties'] if r[1] is not None} |
                          {int(p) for r in rows['judgments'] for p in (r[5],r[6]) if p is not None})
            for start in range(0,len(pids),chunk_size):
                cur.execute('SELECT party_id, name FROM public.parties WHERE party_id = ANY(%s::bigint[])', (pids[start:start+chunk_size],))
                rows['parties'].extend(cur.fetchall())
    finally:
        conn.close()
    return (pd.DataFrame(rows['judgments'],columns=['judgment_id','case_id','judgment_date','judgment_type','judgment_method','for_party_id','against_party_id']),
            pd.DataFrame(rows['case_parties'],columns=['case_id','party_id','party_type']),
            pd.DataFrame(rows['parties'],columns=['party_id','name']))

def date(x):
    v = pd.to_datetime(x,errors='coerce')
    return v if pd.notna(v) else pd.NaT

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'data/analysis/outcomes_v1/municipal_case_outcomes_full.csv')
    p.add_argument('--actions',type=Path,default=ROOT/'data/analysis/municipal_defendant_actions.csv')
    p.add_argument('--output-dir',type=Path,default=ROOT/'data/analysis/outcomes_v2')
    p.add_argument('--offline',action='store_true',help='Use supplied structured CSVs instead of database')
    p.add_argument('--judgments',type=Path)
    p.add_argument('--case-parties',type=Path)
    p.add_argument('--parties',type=Path)
    p.add_argument('--chunk-size',type=int,default=1000)
    args=p.parse_args()
    base=pd.read_csv(args.input,dtype={'case_id':'Int64'},low_memory=False)
    for c in ['case_id','municipality','disposition_type','municipality_outcome']:
        if c not in base: raise SystemExit(f'Missing input column: {c}')
    if base[['case_id','municipality']].duplicated().any():
        raise SystemExit('Duplicate case_id/municipality input rows; resolve before enrichment')
    ids=base.case_id.dropna().astype('int64').unique().tolist()
    if args.offline:
        if not all([args.judgments,args.case_parties,args.parties]):
            raise SystemExit('--offline requires --judgments, --case-parties, --parties')
        judgments=pd.read_csv(args.judgments)
        cp=pd.read_csv(args.case_parties)
        parties=pd.read_csv(args.parties)
    else:
        judgments,cp,parties=load_db(ids,args.chunk_size)
    for df,cols in [(judgments,['case_id','for_party_id','against_party_id']), (cp,['case_id','party_id']), (parties,['party_id'])]:
        for c in cols:
            if c not in df: raise SystemExit(f'Missing structured column: {c}')
            df[c]=pd.to_numeric(df[c],errors='coerce').astype('Int64')
    if 'party_type' not in cp or 'name' not in parties:
        raise SystemExit('Party tables require party_type and name')
    parties=parties.drop_duplicates('party_id')
    cp=cp.merge(parties[['party_id','name']],on='party_id',how='left')
    cp=cp[cp.case_id.isin(ids)]
    cp_by_case={int(k):g for k,g in cp.groupby('case_id')}
    judgments=judgments[judgments.case_id.isin(ids)].copy()
    judgments['judgment_date_parsed']=pd.to_datetime(judgments.get('judgment_date'),errors='coerce')
    judgments=judgments.sort_values(['judgment_date_parsed','judgment_id'],kind='stable')
    j_by_case={int(k):g for k,g in judgments.groupby('case_id')}
    name_by_id={int(r.party_id):str(r.name) for r in parties.itertuples() if pd.notna(r.party_id)}
    # Collect only potentially relevant later reversal entries; do not infer a reversal from a generic 'vacated'.
    reversal_by_case={}
    if args.actions.exists():
        for chunk in pd.read_csv(args.actions,chunksize=75000,usecols=lambda c:c in {'case_id','docket_date','action','docket_text'}):
            chunk['case_id']=pd.to_numeric(chunk['case_id'],errors='coerce')
            chunk=chunk[chunk.case_id.isin(ids)]
            if chunk.empty:continue
            text=chunk.get('action',pd.Series('',index=chunk.index)).fillna('').astype(str)+' '+chunk.get('docket_text',pd.Series('',index=chunk.index)).fillna('').astype(str)
            mask=text.str.contains(r'\b(?:judgment|dismissal|order|rescript|reinstat|remand|appeal)\b',case=False,regex=True) & text.str.contains(r'\b(?:vacat(?:ed|ur)|revers(?:ed|al)|reinstat(?:ed|ement)|remand(?:ed)?|set aside|modified)\b',case=False,regex=True)
            for r,t in zip(chunk.loc[mask].itertuples(index=False),text[mask]):
                cid=int(r.case_id)
                reversal_by_case.setdefault(cid,[]).append((date(getattr(r,'docket_date',None)),str(t)[:400]))
    results=[]; audit=[]
    for r in base.itertuples(index=False):
        cid=int(r.case_id); muni=str(r.municipality)
        roster=cp_by_case.get(cid)
        mids=set()
        if roster is not None:
            for pr in roster.itertuples():
                if pd.notna(pr.party_id) and 'defend' in str(pr.party_type).lower() and municipality_match(pr.name,muni):
                    mids.add(int(pr.party_id))
        js=j_by_case.get(cid)
        directions=[]
        if js is not None:
            for j in js.itertuples():
                fid=int(j.for_party_id) if pd.notna(j.for_party_id) else None
                aid=int(j.against_party_id) if pd.notna(j.against_party_id) else None
                if not mids or (fid not in mids and aid not in mids): continue
                direction='conflicting' if fid in mids and aid in mids else ('favored' if fid in mids else 'adverse')
                directions.append({'judgment_id':str(j.judgment_id),'date':date(j.judgment_date), 'direction':direction,'for':name_by_id.get(fid,''),'against':name_by_id.get(aid,''),'type':str(j.judgment_type)})
        old_out=str(r.municipality_outcome); old_type=str(r.disposition_type)
        outcome=old_out; disposition=old_type; basis='retained_v1'; finality=str(getattr(r,'finality','unknown'))
        flags=[]
        if not mids: flags.append('municipal_defendant_party_id_unmatched')
        if directions:
            newest=max((d['date'] for d in directions if pd.notna(d['date'])),default=pd.NaT)
            latest=[d for d in directions if (pd.notna(newest) and d['date']==newest)] if pd.notna(newest) else directions
            kinds={d['direction'] for d in latest}
            if len(kinds)==1 and 'conflicting' not in kinds:
                candidate='municipality_favored' if 'favored' in kinds else 'municipality_adverse'
                if old_out in ('municipality_favored','municipality_adverse') and old_out!=candidate:
                    flags.append('docket_structured_conflict')
                    outcome='unknown';basis='conflicting_sources'
                else:
                    outcome=candidate;disposition='judgment';basis='structured_party_linked_judgment'
                finality='unverified'
            else:
                flags.append('conflicting_latest_structured_judgments')
                outcome='unknown';basis='conflicting_structured_judgments';finality='unverified'
            if len({d['direction'] for d in directions})>1:
                flags.append('multiple_judgment_directions')
        elif js is not None and len(js):
            flags.append('structured_judgment_not_attributed_to_municipality')
        # Do not replace an earlier final disposition based solely on an unrelated reversal keyword.
        ref_date=max((d['date'] for d in directions if pd.notna(d['date'])),default=pd.NaT) if directions else date(getattr(r,'disposition_date',None))
        later=[(dt,txt) for dt,txt in reversal_by_case.get(cid,[]) if pd.isna(ref_date) or (pd.notna(dt) and dt>=ref_date)]
        if later:
            flags.append('possible_later_reversal_or_modification')
            finality='requires_chronological_review'
            # Direction may remain a historical judgment, but cannot be asserted as final.
        if old_type=='tax_lien_judgment' and basis=='retained_v1':
            flags.append('tax_lien_party_role_caution')
        results.append({'case_id':cid,'municipality':muni,'v2_disposition_type':disposition,
                        'v2_municipality_outcome':outcome,'v2_finality':finality,'v2_basis':basis,
                        'municipal_party_ids':'|'.join(map(str,sorted(mids))),
                        'structured_judgment_count':0 if js is None else len(js),
                        'linked_judgment_count':len(directions),
                        'latest_linked_judgment_date':max((d['date'] for d in directions if pd.notna(d['date'])),default=pd.NaT),
                        'review_flags':'|'.join(sorted(set(flags))),
                        'later_reversal_signal_count':len(later)})
        for d in directions:
            audit.append({'case_id':cid,'municipality':muni,**d})
    enriched=base.merge(pd.DataFrame(results),on=['case_id','municipality'],validate='one_to_one')
    assert len(enriched)==len(base)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    enriched.to_csv(args.output_dir/'municipal_case_outcomes_enriched.csv',index=False)
    pd.DataFrame(audit,columns=['case_id','municipality','judgment_id','date','direction','for','against','type']).to_csv(args.output_dir/'structured_judgment_audit.csv',index=False)
    changed=enriched[(enriched.municipality_outcome.astype(str)!=enriched.v2_municipality_outcome.astype(str)) | (enriched.disposition_type.astype(str)!=enriched.v2_disposition_type.astype(str))]
    changed.to_csv(args.output_dir/'classification_changes.csv',index=False)
    summary=enriched.groupby(['v2_disposition_type','v2_municipality_outcome','v2_basis'],dropna=False).size().reset_index(name='municipality_case_rows')
    summary.to_csv(args.output_dir/'municipal_outcome_summary.csv',index=False)
    print('Rows:',len(enriched),'Unique cases:',enriched.case_id.nunique())
    print('Linked judgment rows:',len(audit),'Changed classifications:',len(changed))
    print('Outcomes:\n',enriched.v2_municipality_outcome.value_counts().to_string())
    print('Review flags:\n',enriched.review_flags.value_counts().head(12).to_string())
    print('Wrote:',args.output_dir)

if __name__=='__main__':main()
