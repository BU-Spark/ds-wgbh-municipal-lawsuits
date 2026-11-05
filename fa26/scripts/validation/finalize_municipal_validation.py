#!/usr/bin/env python3
"""Conservative, reproducible docket review of the 132 unknowns; preserve prior 48."""
from pathlib import Path
import re
import pandas as pd
ROOT=Path(__file__).resolve().parents[2] / 'data' / 'validation'
merged=pd.read_csv(ROOT/'municipal_case_outcomes_merged_180.csv').set_index('case_id',drop=False)
unknown=pd.read_csv(ROOT/'municipal_unknown_132_final_review.csv').set_index('case_id',drop=False)
dockets=pd.read_csv(ROOT/'outcome_review_dockets.csv').fillna('')
parties=pd.read_csv(ROOT/'structured_outcomes/case_parties.csv').merge(
    pd.read_csv(ROOT/'structured_outcomes/parties.csv')[['party_id','name']],
    on='party_id',how='left')
judgments=pd.read_csv(ROOT/'structured_outcomes/judgments.csv')
dockets['date_sort']=pd.to_datetime(dockets.docket_date,errors='coerce')
dockets=dockets.sort_values(['case_id','date_sort','docket_sequence'],kind='stable')
RE_ALL=re.compile(r'(?:as to|against) all (?:parties|defendants|claims)|all parties and all claims|entire (?:action|case|complaint)|complaint is dismissed as to all|case is dismissed',re.I)
RE_DIS=re.compile(r'judgment of dismissal|stipulation of dismissal|voluntary dismissal|notice of dismissal|dismissal entered|complaint (?:is|was) dismissed|dismissed as to|case inactivated: judgment of dismissal',re.I)
RE_JUD=re.compile(r'judgment (?:entered|for|against|on the pleadings)|agreement for judgment|final judgment entered|judgment of dismissal',re.I)
RE_SET=re.compile(r'settlement (?:reported|agreement)|parties (?:have )?settled|case settled',re.I)
RE_REV=re.compile(r'judgment (?:was |is |has been )?vacated|vacat(?:ed|ing) (?:the )?(?:judgment|dismissal)|dismissal (?:was |is )?vacated|reinstat(?:ed|ement) of (?:the )?(?:case|complaint)|judgment reversed',re.I)
RE_COND=re.compile(r'if no |unless |shall enter|will enter|nisi|motion (?:to|for) |proposed |request (?:for|to) |application for ',re.I)
RE_TAX=re.compile(r'final judgment entered as to tax.taking|tax taking|foreclos(?:ure|ing) of (?:the )?right of redemption',re.I)
RE_FAVOR=re.compile(r'judgment (?:for|in favor of) (?:the )?(?:defendant|respondent)|claims against .{0,80} dismiss(?:ed|al)',re.I)
RE_ADVERSE=re.compile(r'judgment (?:for|in favor of) (?:the )?plaintiff|judgment against (?:the )?defendant',re.I)
rows=[]
for cid,u in unknown.iterrows():
    d=dockets[dockets.case_id==cid]
    muni=str(u.municipality)
    roster=parties[parties.case_id==cid]
    municipal_names=[str(n) for n in roster.name.dropna() if muni.lower() in str(n).lower() or (('city of '+muni).lower() in str(n).lower()) or (('town of '+muni).lower() in str(n).lower())]
    names=[muni]+municipal_names
    candidates=[]
    for _,r in d.iterrows():
        t=' '.join([str(r.action),str(r.docket_text)]).strip()
        if not (RE_DIS.search(t) or RE_JUD.search(t) or RE_SET.search(t) or RE_REV.search(t)):continue
        typ='dismissal' if RE_DIS.search(t) else 'judgment' if RE_JUD.search(t) else 'settlement' if RE_SET.search(t) else 'reversal'
        if RE_TAX.search(t):typ='tax_lien_judgment'
        if RE_COND.search(t) and not (re.search(r'judgment (?:of dismissal |)entered|dismissal (?:with|without) prejudice|stipulation of dismissal|notice of dismissal filed|agreement for judgment',t,re.I)): typ='procedural_or_conditional'
        names_match=any(re.search(r'(?<![a-z])'+re.escape(n)+r'(?![a-z])',t,re.I) for n in names if len(n)>3)
        candidates.append((r,typ,names_match,bool(RE_ALL.search(t)),bool(RE_REV.search(t)),t))
    substantive=[c for c in candidates if c[1] in ('dismissal','judgment','settlement','tax_lien_judgment')]
    last=substantive[-1] if substantive else None
    # Explicit scope outranks generic labels; later reversal after the candidate prevents finality.
    later_reversal=False
    if last is not None:
        last_dt=last[0].date_sort
        later_reversal=any(c[4] and pd.notna(c[0].date_sort) and pd.notna(last_dt) and c[0].date_sort>last_dt for c in candidates)
    disposition='unknown'; scope='unknown'; outcome='unknown'; finality='unverified'; basis='no_conclusive_docket_disposition'
    if last is not None:
        r,typ,mention,all_scope,_,t=last
        if typ=='tax_lien_judgment':
            disposition='tax_lien_judgment';basis='tax_lien_not_municipal_win_loss'
        elif typ=='dismissal':
            disposition='dismissal'
            if all_scope:scope='whole_case';outcome='dismissal_involving_municipality';basis='explicit_all_parties_dismissal'
            elif mention:scope='municipality_mentioned';outcome='dismissal_involving_municipality';basis='dismissal_with_municipality_named'
            else:basis='dismissal_scope_not_established'
        elif typ=='settlement':
            disposition='settlement_signal_unconfirmed';basis='settlement_mention_not_proof_municipal_settlement'
        elif typ=='judgment':
            disposition='judgment';basis='judgment_party_attribution_unverified'
            # explicit directed judgment and named municipality in same operative clause
            if mention and re.search(r'(?:judgment|execution) (?:for|against).{0,130}'+re.escape(muni),t,re.I):
                outcome='municipality_adverse' if re.search(r'(?:against|v\.?|versus)\s+(?:the )?(?:city|town)\s+of\s+'+re.escape(muni),t,re.I) else 'unknown'
                basis='judgment_municipality_mentioned_verify_direction'
        if later_reversal:
            finality='reversal_after_candidate';outcome='unknown';basis='later_reversal_requires_interpretation'
        elif disposition=='dismissal' and (scope=='whole_case' or scope=='municipality_mentioned'):
            finality='docket_supported_no_later_explicit_reversal'
        elif disposition!='unknown':finality='docket_event_only'
    # Independently verify case-level outcome with explicit judgment parties, where available.
    js=judgments[judgments.case_id==cid]
    if len(js):
        muni_ids=set(roster.loc[roster.name.fillna('').str.contains(re.escape(muni),case=False,regex=True),'party_id'].astype(int))
        favors=any(pd.notna(j.for_party_id) and int(j.for_party_id) in muni_ids for _,j in js.iterrows())
        adverse=any(pd.notna(j.against_party_id) and int(j.against_party_id) in muni_ids for _,j in js.iterrows())
        if favors!=adverse and not later_reversal:
            outcome='municipality_favored' if favors else 'municipality_adverse'
            disposition='judgment';basis='structured_judgment_direction';finality='structured_judgment_not_independently_finality_verified'
    evidence=last[5] if last else ''
    rows.append(dict(case_id=cid,municipality=muni,case_status=u.case_status,case_type=u.case_type,initiating_action=u.initiating_action,previous_screen=u.previous_screen,reviewed_docket_rows=len(d),candidate_entries=len(candidates),disposition_type=disposition,disposition_scope=scope,municipality_outcome=outcome,finality=finality,review_basis=basis,disposition_date=str(last[0].docket_date) if last else '',evidence_source_row=last[0].source_row if last else '',evidence_text=evidence[:1500],later_reversal_flag=later_reversal,structured_judgment_rows=len(js)))
review=pd.DataFrame(rows)
assert len(review)==132 and review.case_id.is_unique
review.to_csv(ROOT/'municipal_unknown_132_final_review.csv',index=False)
final=merged.copy()
for c in ['final_disposition_type','final_disposition_scope','final_municipality_outcome','final_finality','final_review_basis','final_evidence_text','final_disposition_date']:
    final[c]=''
for cid,r in final.iterrows():
    final.at[cid,'final_disposition_type']=str(r.get('resolved_disposition_type','unknown'))
    final.at[cid,'final_disposition_scope']=str(r.get('reviewed_scope','')) if pd.notna(r.get('reviewed_scope')) else str(r.get('disposition_scope','unknown'))
    final.at[cid,'final_municipality_outcome']=str(r.get('resolved_municipality_outcome','unknown'))
    final.at[cid,'final_finality']=str(r.get('resolved_finality','unverified'))
    final.at[cid,'final_review_basis']=str(r.get('resolution_basis',''))
    final.at[cid,'final_evidence_text']=str(r.get('evidence_text',''))
    final.at[cid,'final_disposition_date']=str(r.get('resolved_disposition_date',''))
for _,r in review.iterrows():
    cid=r.case_id
    for src,dst in [('disposition_type','final_disposition_type'),('disposition_scope','final_disposition_scope'),('municipality_outcome','final_municipality_outcome'),('finality','final_finality'),('review_basis','final_review_basis'),('evidence_text','final_evidence_text'),('disposition_date','final_disposition_date')]:final.at[cid,dst]=r[src]
assert len(final)==180 and final.case_id.is_unique
final.to_csv(ROOT/'municipal_case_outcomes_final_180.csv',index=False)
print('132 disposition types:\n',review.disposition_type.value_counts().to_string())
print('\n132 outcomes:\n',review.municipality_outcome.value_counts().to_string())
print('\n180 final outcomes:\n',final.final_municipality_outcome.value_counts().to_string())
print('\n180 disposition types:\n',final.final_disposition_type.value_counts().to_string())