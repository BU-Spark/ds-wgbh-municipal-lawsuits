#!/usr/bin/env python3
from __future__ import annotations
import argparse
import re
from collections import defaultdict
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def read(path, required=True):
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Missing {path}")
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def col(df, *names):
    for n in names:
        if n in df.columns:
            return n
    return None


def val(row, *names):
    for n in names:
        x = str(row.get(n, '') or '').strip()
        if x and x.lower() not in ('nan', 'none'):
            return x
    return ''


def norm(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', str(s).lower())).strip()


def aliases(municipality):
    name = norm(municipality)
    if not name:
        return set()
    out = {name}
    for prefix in ('city of ', 'town of ', 'the city of ', 'the town of '):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    if len(name) >= 4:
        out |= {f'city of {name}', f'town of {name}', f'the city of {name}', f'the town of {name}'}
    return out


def mentions_municipality(text, municipality):
    s = norm(text)
    a = aliases(municipality)
    # Require explicit municipal title, except when docket itself has a titled name.
    return any((' ' + x + ' ') in (' ' + s + ' ') for x in a if x.startswith(('city of ', 'town of ', 'the city of ', 'the town of ')))


PATTERNS = [
    ('tax_lien_judgment', re.compile(r'\b(?:tax lien|tax taking|foreclos(?:ure|e) of (?:the )?right of redemption)\b', re.I)),
    ('settlement', re.compile(r'\b(?:settlement agreement|settlement approved|settlement reached|parties have settled|case (?:has been )?settled)\b', re.I)),
    ('settlement_signal_unconfirmed', re.compile(r'\b(?:settlement reported|notice of settlement|settlement conference|settlement discussions)\b', re.I)),
    ('dismissal', re.compile(r'\b(?:stipulation of dismissal|voluntary dismissal|notice of dismissal|judgment of dismissal|dismissal entered|case (?:is |was )?dismissed|complaint (?:is |was )?dismissed|order of dismissal)\b', re.I)),
    ('judgment', re.compile(r'\b(?:judgment entered|judgment for (?:the )?(?:plaintiff|defendant)|final judgment|judgment on the pleadings|agreement for judgment|summary judgment (?:allowed|granted))\b', re.I)),
]
MOTION = re.compile(r'\b(?:motion (?:for|to)|opposition to|hearing (?:on|regarding)|proposed|request for|notice of hearing|memorandum (?:in support|of law))\b', re.I)
NEGATED = re.compile(r'\b(?:denied|not granted|without ruling|shall enter unless|may enter if|if no objection|proposed order|motion to vacate|motion to dismiss)\b', re.I)
REVERSAL = re.compile(r'\b(?:judgment|dismissal|order|case|complaint)\b.{0,95}\b(?:vacated|reversed|set aside|reinstated|reopened)\b|\b(?:vacated|reversed|set aside|reinstated)\b.{0,95}\b(?:judgment|dismissal|order|case|complaint)\b', re.I)
WHOLE = re.compile(r'\b(?:all (?:claims|parties|defendants)|entire (?:case|action)|case dismissed|complaint dismissed|action dismissed|as to all)\b', re.I)
PARTIAL = re.compile(r'\b(?:partial|some claims|certain claims|count [ivx0-9]+|as to (?:one|certain|some)|remaining claims)\b', re.I)
FOR_MUNI = re.compile(r'\b(?:judgment for|judgment in favor of|summary judgment (?:for|in favor of)|dismissed as to|claims against)\b', re.I)
AGAINST_MUNI = re.compile(r'\b(?:judgment against|judgment entered against|liable for|damages against)\b', re.I)


def classify_event(action, text, municipality):
    s = f'{action} {text}'.strip()
    if not s:
        return None
    # A docket line about a motion is not automatically an entered disposition.
    if MOTION.search(s) and not re.search(r'\b(?:judgment entered|dismissal entered|stipulation of dismissal filed|case dismissed|complaint dismissed)\b', s, re.I):
        return None
    if NEGATED.search(s) and not re.search(r'\b(?:judgment entered|dismissal entered|stipulation of dismissal filed)\b', s, re.I):
        return None
    kind = None
    for k, p in PATTERNS:
        if p.search(s):
            kind = k
            break
    if not kind:
        return None
    if kind == 'tax_lien_judgment' and not re.search(r'\b(?:judgment|decree|foreclosure)\b', s, re.I):
        return None
    mention = mentions_municipality(s, municipality)
    scope = 'partial_or_uncertain' if PARTIAL.search(s) else ('whole_case' if WHOLE.search(s) else 'unknown')
    outcome = 'unknown'
    if mention and kind == 'dismissal' and (re.search(r'\b(?:claims against|dismissed as to)\b', s, re.I) or scope == 'whole_case'):
        outcome = 'dismissal_involving_municipality'
    elif mention and kind == 'judgment':
        # Only unambiguous party-specific wording, not mere proximity of name.
        for phrase, result in ((r'judgment (?:entered )?(?:in favor of|for)\s+(?:the\s+)?(?:city|town) of\s+', 'municipality_favored'),
                               (r'judgment (?:entered )?against\s+(?:the\s+)?(?:city|town) of\s+', 'municipality_adverse')):
            if re.search(phrase + re.escape(norm(municipality)) + r'\b', norm(s)):
                outcome = result
                break
    elif mention and kind == 'settlement':
        outcome = 'settled'
    return kind, scope, outcome, mention


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=ROOT)
    ap.add_argument('--chunksize', type=int, default=100000)
    args = ap.parse_args()
    root = args.root.resolve()
    inp = root / 'data/analysis'
    out = inp / 'outcomes_v1'
    out.mkdir(parents=True, exist_ok=True)
    cases = read(inp / 'municipal_cases.csv')
    parties = read(inp / 'municipal_case_parties.csv')
    if 'case_id' not in cases or 'case_id' not in parties:
        raise ValueError('Both municipal_cases.csv and municipal_case_parties.csv need case_id')
    if 'party_type' not in parties:
        raise ValueError('municipal_case_parties.csv needs party_type')
    if 'municipality' not in parties.columns and 'municipality' not in cases.columns:
        raise ValueError('A municipality column is required')
    parties = parties[parties.party_type.str.contains(r'\bdefendant\b', case=False, regex=True, na=False)].copy()
    if parties.empty:
        raise ValueError('No defendant party rows found. Inspect party_type values.')
    case_meta = cases.drop_duplicates('case_id').set_index('case_id')
    # A case can have multiple municipal defendants: classify each separately.
    keys = parties[['case_id', 'municipality']].copy() if 'municipality' in parties else parties[['case_id']].assign(municipality=parties.case_id.map(case_meta.municipality))
    keys = keys.dropna().drop_duplicates()
    keys = keys[keys.municipality.astype(str).str.strip().ne('')]
    lookup = defaultdict(list)
    for r in keys.itertuples(index=False):
        lookup[str(r.case_id)].append(str(r.municipality))
    actions_path = inp / 'municipal_defendant_actions.csv'
    if not actions_path.exists():
        raise FileNotFoundError(actions_path)
    events = []
    reversal_rows = defaultdict(list)
    action_counts = defaultdict(int)
    for chunk in pd.read_csv(actions_path, dtype=str, keep_default_na=False, chunksize=args.chunksize):
        if 'case_id' not in chunk:
            raise ValueError('Actions file needs case_id')
        for r in chunk.to_dict('records'):
            cid = str(r['case_id'])
            if cid not in lookup:
                continue
            action_counts[cid] += 1
            date = val(r, 'docket_date')
            action = val(r, 'action')
            text = val(r, 'docket_text')
            combined = f'{action} {text}'
            if REVERSAL.search(combined):
                reversal_rows[cid].append((date, combined[:400]))
            for muni in lookup[cid]:
                result = classify_event(action, text, muni)
                if result:
                    kind, scope, outcome, mention = result
                    events.append(dict(case_id=cid, municipality=muni, docket_date=date, disposition_type=kind,
                                       disposition_scope=scope, municipality_outcome=outcome,
                                       explicit_municipality_mention=mention, action=action, evidence_text=text[:1200]))
    ev = pd.DataFrame(events, columns=['case_id','municipality','docket_date','disposition_type','disposition_scope','municipality_outcome','explicit_municipality_mention','action','evidence_text'])
    ev.to_csv(out / 'municipal_outcome_evidence.csv', index=False)
    grouped = {(str(k[0]),str(k[1])):g.sort_values('docket_date') for k,g in ev.groupby(['case_id','municipality'], sort=False)} if not ev.empty else {}
    records = []
    for r in keys.to_dict('records'):
        cid, muni = str(r['case_id']), str(r['municipality'])
        group = grouped.get((cid, muni))
        e = group.iloc[-1] if group is not None and len(group) else None
        reversals = reversal_rows.get(cid, [])
        possible_later = bool(e is not None and any((not d or not e.docket_date or d >= e.docket_date) for d,_ in reversals))
        if e is None:
            dtype, scope, outcome, date, evidence = 'unknown','unknown','unknown','',''
        else:
            dtype, scope, outcome, date, evidence = e.disposition_type,e.disposition_scope,e.municipality_outcome,e.docket_date,e.evidence_text
        # A reversal signal does not prove a reversal. Withhold party-specific outcomes pending review.
        if possible_later:
            outcome = 'unknown'
        if dtype == 'settlement_signal_unconfirmed':
            outcome = 'unknown'
        rec = dict(case_id=cid, municipality=muni, disposition_type=dtype, disposition_scope=scope,
                   municipality_outcome=outcome, disposition_date=date,
                   finality='possible_reversal_review' if possible_later else ('unverified_docket_evidence' if e is not None else 'unknown'),
                   evidence_count=0 if group is None else len(group), action_count=action_counts[cid],
                   reversal_signal_count=len(reversals), evidence_text=evidence,
                   classification_source='automated_docket_rules_v1')
        if cid in case_meta.index:
            row = case_meta.loc[cid]
            for name in ('case_number','case_title','case_type','initiating_action','case_status','status_date','file_date','dor_code'):
                if name in case_meta.columns:
                    rec[name] = row[name]
        records.append(rec)
    result = pd.DataFrame(records)
    result.to_csv(out / 'municipal_case_outcomes_full.csv', index=False)
    summary = (result.groupby(['municipality','disposition_type','municipality_outcome'], dropna=False).size()
               .rename('case_count').reset_index())
    summary.to_csv(out / 'municipal_outcome_summary.csv', index=False)
    print(f'Rows classified (case x municipality): {len(result):,}')
    print(f'Unique cases: {result.case_id.nunique():,}')
    print('Disposition types:\n' + result.disposition_type.value_counts().to_string())
    print('Municipality outcomes:\n' + result.municipality_outcome.value_counts().to_string())
    print(f'Wrote outputs to {out}')

if __name__ == '__main__':
    main()
