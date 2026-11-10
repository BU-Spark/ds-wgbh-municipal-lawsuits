#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

PATTERNS = [
    ("settlement_reported", r"\bsettlement (?:was |has been )?reported\b|\bparties (?:have )?settled\b"),
    ("stipulated_dismissal", r"\bstipulation of dismissal\b|\bstipulated dismissal\b"),
    ("voluntary_dismissal", r"\bvoluntary dismissal\b|\bnotice of dismissal filed\b"),
    ("agreement_for_judgment", r"\bagreement for judgment\b"),
    ("dismissal_judgment", r"\bjudgment of dismissal\b"),
    ("dismissal_entered", r"\bdismissal entered\b|\b(?:case|complaint|action|claim) (?:is |was |has been )?dismissed\b"),
    ("judgment_entered", r"\b(?:final )?judgment (?:has been |was )?entered\b|\bjudgment for (?:the )?(?:plaintiff|defendant)\b"),
    ("summary_judgment_ruling", r"\bsummary judgment\b.{0,120}\b(?:allowed|granted|denied)\b"),
    ("motion_to_dismiss_ruling", r"\bmotion to dismiss\b.{0,100}\b(?:allowed|granted|denied)\b"),
]

COMPILED = [(name, re.compile(expr, re.I | re.S)) for name, expr in PATTERNS]

ACTION_MAP = {
    "Stipulation of dismissal": "stipulated_dismissal",
    "Voluntary Dismissal": "voluntary_dismissal",
    "Notice of dismissal": "voluntary_dismissal",
    "Settlement agreement": "settlement_reported",
    "Agreement for Judgment": "agreement_for_judgment",
    "Dismissal": "dismissal_recorded",
    "Judgment": "judgment_recorded",
}

UNCERTAIN = re.compile(
    r"\b(?:shall enter|will enter|may enter|to be entered|proposed|draft|"
    r"motion for|request for|notice of potential|order nisi|unless|"
    r"vacated|vacate|reversed|set aside|returned to)\b", re.I
)

PARTIAL = re.compile(
    r"\b(?:in part|partial|as to (?:count|claim|party|defendant|plaintiff)|"
    r"counts? [ivx0-9]|remaining claims?)\b", re.I
)

PREJ_WITHOUT = re.compile(r"\bwithout prejudice\b", re.I)
PREJ_WITH = re.compile(r"\bwith prejudice\b", re.I)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--actions",
        type=Path,
        default=ROOT / "data/analysis/municipal_defendant_actions.csv",
    )
    parser.add_argument(
        "--parties",
        type=Path,
        default=ROOT / "data/analysis/municipal_case_parties.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/analysis",
    )
    args = parser.parse_args()

    actions = pd.read_csv(args.actions, low_memory=False)
    parties = pd.read_csv(args.parties, low_memory=False)

    for name, df, required in [
        ("actions", actions, {"case_id", "docket_date", "action", "docket_text"}),
        ("parties", parties, {"case_id", "party_type"}),
    ]:
        missing = required - set(df.columns)
        if missing:
            parser.error(f"{name} missing columns: {sorted(missing)}")

    parties["case_id"] = pd.to_numeric(
        parties.case_id, errors="coerce"
    )

    defendant_ids = set(
        parties.loc[
            parties.party_type.fillna("").str.contains(
                "defendant", case=False
            ),
            "case_id",
        ].dropna().astype("int64")
    )

    actions["case_id"] = pd.to_numeric(
        actions.case_id, errors="coerce"
    )

    actions = actions[
        actions.case_id.isin(defendant_ids)
    ].copy()

    actions["docket_date"] = pd.to_datetime(
        actions.docket_date, errors="coerce"
    )

    actions = actions.sort_values(
        ["case_id", "docket_date"], kind="stable"
    )

    records = []

    for i, row in actions.iterrows():
        action = "" if pd.isna(row.action) else str(row.action)
        description = (
            "" if pd.isna(row.docket_text)
            else str(row.docket_text)
        )

        labels = set()

        if action in ACTION_MAP:
            labels.add(ACTION_MAP[action])

        for label, regex in COMPILED:
            if regex.search(description):
                labels.add(label)

        if not labels:
            continue

        uncertain = bool(UNCERTAIN.search(description))
        partial = bool(PARTIAL.search(description))

        if (
            PREJ_WITHOUT.search(description)
            and PREJ_WITH.search(description)
        ):
            prejudice = "mixed_or_ambiguous"
        elif PREJ_WITHOUT.search(description):
            prejudice = "without_prejudice"
        elif PREJ_WITH.search(description):
            prejudice = "with_prejudice"
        else:
            prejudice = "unknown"

        for label in sorted(labels):
            records.append({
                "case_id": int(row.case_id),
                "source_row": int(i),
                "docket_date": row.docket_date,
                "action": action,
                "candidate_event": label,
                "requires_review": True,
                "uncertainty_flag": uncertain,
                "partial_scope_flag": partial,
                "prejudice_text": prejudice,
                "municipality_affected": "unknown",
                "final_case_disposition": "unverified",
                "docket_text": description,
            })

    columns = [
        "case_id",
        "source_row",
        "docket_date",
        "action",
        "candidate_event",
        "requires_review",
        "uncertainty_flag",
        "partial_scope_flag",
        "prejudice_text",
        "municipality_affected",
        "final_case_disposition",
        "docket_text",
    ]

    events = pd.DataFrame.from_records(
        records, columns=columns
    )

    summary = pd.DataFrame({
        "case_id": sorted(defendant_ids)
    })

    if not events.empty:
        aggregates = events.groupby("case_id").agg(
            candidate_event_count=("candidate_event", "size"),
            candidate_event_types=(
                "candidate_event",
                lambda s: ";".join(sorted(set(s))),
            ),
            latest_candidate_date=("docket_date", "max"),
            any_uncertainty_flag=("uncertainty_flag", "any"),
            any_partial_scope_flag=("partial_scope_flag", "any"),
        ).reset_index()

        summary = summary.merge(
            aggregates, how="left", on="case_id"
        )
    else:
        summary["candidate_event_count"] = 0

    summary["candidate_event_count"] = (
        summary["candidate_event_count"]
        .fillna(0)
        .astype(int)
    )

    summary["outcome_status"] = "unverified"
    summary["municipality_outcome"] = "unknown"

    args.output_dir.mkdir(
        parents=True, exist_ok=True
    )

    events.to_csv(
        args.output_dir / "municipal_outcome_events.csv",
        index=False,
    )

    summary.to_csv(
        args.output_dir / "municipal_case_outcomes.csv",
        index=False,
    )

    print(f"Municipal defendant cases: {len(defendant_ids):,}")
    print(f"Candidate event rows: {len(events):,}")
    print(
        f"Cases with candidate events: "
        f"{(summary.candidate_event_count > 0).sum():,}"
    )
    print(
        "All candidates require review; "
        "no final municipality win/loss inferred."
    )
    print(
        f"Outputs: "
        f"{args.output_dir / 'municipal_outcome_events.csv'}"
    )
    print(
        f"         "
        f"{args.output_dir / 'municipal_case_outcomes.csv'}"
    )


if __name__ == "__main__":
    main()
