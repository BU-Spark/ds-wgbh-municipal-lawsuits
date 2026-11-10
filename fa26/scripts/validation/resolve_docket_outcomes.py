#!/usr/bin/env python3
import argparse
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def txt(value):
    return '' if pd.isna(value) else str(value)


def norm(value):
    return re.sub(r'[^a-z0-9]+', ' ', txt(value).lower()).strip()


def municipality_aliases(municipality, party_names):
    """Use municipality and exact roster names; avoid matching 'town' alone."""
    base = norm(municipality)
    if not base:
        return []
    aliases = {base, 'city of ' + base, 'town of ' + base}
    for name in party_names:
        n = norm(name)
        if n == base or n in aliases or n.endswith(' of ' + base):
            aliases.add(n)
    return sorted(aliases, key=len, reverse=True)


def party_mentioned(s, aliases):
    normalized = ' ' + norm(s) + ' '
    return any(' ' + alias + ' ' in normalized for alias in aliases)


# Only completed/entered dispositions; do not treat a motion or request as a result.
DISMISSAL = re.compile(
    r'\b(?:judgment of dismissal (?:was |has been )?entered|'
    r'(?:case|complaint|action|claims?) (?:was |were |has been |have been )?dismissed|'
    r'(?:stipulation|notice) of dismissal (?:filed|entered)|'
    r'dismissed (?:with|without) prejudice)\b', re.I)
JUDGMENT = re.compile(
    r'\b(?:final judgment entered|judgment (?:was |has been )?entered|'
    r'judgment (?:for|against) (?:the )?(?:plaintiff|defendant|city|town))\b', re.I)
SETTLEMENT = re.compile(r'\b(?:settlement (?:was |has been )?reported|settlement agreement (?:filed|executed)|parties (?:have )?settled)\b', re.I)
REVERSAL = re.compile(
    r'\b(?:judgment|dismissal|order|complaint|case)\b.{0,90}'
    r'\b(?:vacated|reversed|set aside|reinstated)\b|'
    r'\b(?:vacated|reversed|set aside|reinstated)\b.{0,90}'
    r'\b(?:judgment|dismissal|order|complaint|case)\b', re.I)
MOTION = re.compile(r'\b(?:motion|request|petition|application) to (?:vacate|reverse|set aside|reinstate)\b', re.I)
CONDITIONAL = re.compile(
    r'\b(?:shall enter|will enter|may enter|to be entered|unless|'
    r'proposed|order nisi|within \d+ days|if no|subject to)\b', re.I)
PARTIAL = re.compile(
    r'\b(?:in part|partial|as to (?:count|claim|defendant|plaintiff)|'
    r'certain (?:claims|defendants)|remaining (?:claims|defendants))\b', re.I)
AGAINST = re.compile(r'\b(?:against|judgment against|recover from|in favor of .{0,100} against)\b', re.I)
FAVORED = re.compile(r'\b(?:in favor of|claims? against .{0,100} dismissed|dismissed as to)\b', re.I)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--adjudicated', type=Path, default=ROOT/'data/validation/municipal_case_outcomes_adjudicated_180.csv')
    ap.add_argument('--dockets', type=Path, default=ROOT/'data/validation/outcome_review_dockets.csv')
    ap.add_argument('--case-parties', type=Path, default=ROOT/'data/validation/structured_outcomes/case_parties.csv')
    ap.add_argument('--parties', type=Path, default=ROOT/'data/validation/structured_outcomes/parties.csv')
    ap.add_argument('--judgments', type=Path, default=ROOT/'data/validation/structured_outcomes/judgments.csv')
    ap.add_argument('--out', type=Path, default=ROOT/'data/analysis/municipal_case_outcomes_resolved_180.csv')
    args = ap.parse_args()
    for path in [args.adjudicated, args.dockets, args.case_parties, args.parties, args.judgments]:
        if not path.exists():
            ap.error(f'Missing {path}; supply its corresponding --argument')
    base = pd.read_csv(args.adjudicated, low_memory=False)
    dockets = pd.read_csv(args.dockets, low_memory=False)
    cp = pd.read_csv(args.case_parties, low_memory=False)
    parties = pd.read_csv(args.parties, low_memory=False)
    judgments = pd.read_csv(args.judgments, low_memory=False)
    for label, frame, cols in [
        ('adjudicated',base,{'case_id','municipality'}),
        ('dockets',dockets,{'case_id','docket_date','action','docket_text'}),
        ('case_parties',cp,{'case_id','party_id','party_type'}),
        ('parties',parties,{'party_id','name'}),
        ('judgments',judgments,{'case_id','for_party_id','against_party_id'}),
    ]:
        if not cols.issubset(frame.columns):
            ap.error(f'{label} missing columns: {sorted(cols-set(frame.columns))}')
    for frame in (base,dockets,cp,judgments):
        frame['case_id'] = pd.to_numeric(frame['case_id'],errors='coerce').astype('Int64')
    cp['party_id'] = pd.to_numeric(cp['party_id'],errors='coerce').astype('Int64')
    parties['party_id'] = pd.to_numeric(parties['party_id'],errors='coerce').astype('Int64')
    names = parties.dropna(subset=['party_id']).drop_duplicates('party_id').set_index('party_id')['name'].to_dict()
    roster = defaultdict(list)
    for r in cp.itertuples(index=False):
        if pd.notna(r.case_id) and pd.notna(r.party_id):
            roster[int(r.case_id)].append((int(r.party_id),txt(r.party_type),txt(names.get(int(r.party_id)))))
    docket_groups = {int(cid):g.copy() for cid,g in dockets.dropna(subset=['case_id']).groupby('case_id')}
    judgment_groups = {int(cid):g.copy() for cid,g in judgments.dropna(subset=['case_id']).groupby('case_id')}
    outputs=[]
    for row in base.to_dict('records'):
        cid=int(row['case_id'])
        municipality=txt(row['municipality'])
        relevant=[(pid,role,name) for pid,role,name in roster[cid] if name and
                  (norm(name)==norm(municipality) or norm(name) in
                   {'city of '+norm(municipality),'town of '+norm(municipality)} or
                   norm(name).endswith(' of '+norm(municipality)))]
        municipal_ids={pid for pid,role,name in relevant if 'defendant' in role.lower()}
        aliases=municipality_aliases(municipality,[name for _,_,name in relevant])
        g=docket_groups.get(cid,pd.DataFrame())
        if not g.empty:
            g['parsed_date']=pd.to_datetime(g['docket_date'],errors='coerce')
            g=g.sort_values(['parsed_date'] + (['docket_sequence'] if 'docket_sequence' in g else []),kind='stable')
        evidence=[]
        reversal_events=[]
        for dr in g.to_dict('records'):
            content=txt(dr.get('docket_text'))
            action=txt(dr.get('action'))
            full=action+' '+content
            date=txt(dr.get('docket_date'))
            if REVERSAL.search(content) and not MOTION.search(content):
                reversal_events.append((date,content[:500]))
            kind=('dismissal' if DISMISSAL.search(content) else
                  'judgment' if JUDGMENT.search(content) else
                  'settlement' if SETTLEMENT.search(content) else '')
            if not kind:
                continue
            if CONDITIONAL.search(content) or MOTION.search(content) or PARTIAL.search(content):
                continue
            # Municipality name must appear in disposition description, not merely case title.
            if not party_mentioned(content,aliases):
                continue
            # Textual direction is conservative: settlement is neutral; dismissals
            # are not automatically a win; adverse judgment requires explicit link.
            direction='unknown'
            if kind=='settlement':
                direction='settled'
            elif kind=='judgment':
                # Only narrow local context around municipality, not any 'against' in row.
                n=norm(content)
                for alias in aliases:
                    if re.search(r'\bagainst (?:the )?'+re.escape(alias)+r'\b',n):
                        direction='municipality_adverse'
                    if re.search(r'\bin favor of (?:the )?'+re.escape(alias)+r'\b',n):
                        direction='municipality_favored'
            elif kind=='dismissal':
                direction='dismissal_involving_municipality'
            evidence.append((date,kind,direction,content[:1200],txt(dr.get('source_row'))))
        structured=[]
        for jr in judgment_groups.get(cid,pd.DataFrame()).to_dict('records'):
            fp=pd.to_numeric(jr.get('for_party_id'),errors='coerce')
            apid=pd.to_numeric(jr.get('against_party_id'),errors='coerce')
            if pd.notna(fp) and int(fp) in municipal_ids:
                structured.append(('municipality_favored',txt(jr.get('judgment_date')),txt(jr.get('judgment_type'))))
            if pd.notna(apid) and int(apid) in municipal_ids:
                structured.append(('municipality_adverse',txt(jr.get('judgment_date')),txt(jr.get('judgment_type'))))
        result=dict(row)
        result['municipal_party_ids']=';'.join(map(str,sorted(municipal_ids)))
        result['explicit_party_docket_matches']=len(evidence)
        result['effective_reversal_candidates']=len(reversal_events)
        result['docket_evidence_date']=evidence[-1][0] if evidence else ''
        result['docket_evidence_type']=evidence[-1][1] if evidence else ''
        result['docket_evidence_source_row']=evidence[-1][4] if evidence else ''
        result['docket_evidence_text']=evidence[-1][3] if evidence else ''
        result['reversal_evidence_text']=reversal_events[-1][1] if reversal_events else ''
        result['resolved_disposition_type']='unknown'
        result['resolved_municipality_outcome']='unknown'
        result['resolved_disposition_date']=''
        result['resolved_finality']='unverified'
        result['resolution_basis']='insufficient_party_specific_evidence'
        if reversal_events:
            result['resolution_basis']='possible_reversal_requires_chronological_review'
        elif structured:
            directions={s[0] for s in structured}
            if len(directions)==1:
                result['resolved_municipality_outcome']=next(iter(directions))
                result['resolved_disposition_type']='judgment'
                result['resolved_disposition_date']=structured[-1][1]
                result['resolution_basis']='structured_party_linked_judgment'
            else:
                result['resolution_basis']='conflicting_structured_judgments'
        elif evidence:
            kinds={e[1] for e in evidence}
            dirs={e[2] for e in evidence}
            if len(kinds)==1 and len(dirs)==1:
                result['resolved_disposition_type']=evidence[-1][1]
                result['resolved_municipality_outcome']=evidence[-1][2]
                result['resolved_disposition_date']=evidence[-1][0]
                result['resolution_basis']='explicit_municipality_mention_in_docket'
            else:
                result['resolution_basis']='multiple_or_conflicting_docket_events'
        outputs.append(result)
    output=pd.DataFrame(outputs)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    output.to_csv(args.out,index=False)
    print(f'Cases: {len(output):,}')
    print('Resolution basis:')
    print(output['resolution_basis'].value_counts().to_string())
    print('Municipality outcome:')
    print(output['resolved_municipality_outcome'].value_counts().to_string())
    print(f'Written: {args.out}')

if __name__=='__main__':
    main()
