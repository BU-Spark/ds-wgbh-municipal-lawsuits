# # # # import os
# # # # import psycopg2

# # # # # query = """
# # # # # SELECT
# # # # #     table_name,
# # # # #     column_name,
# # # # #     data_type
# # # # # FROM information_schema.columns
# # # # # WHERE table_schema = 'public'
# # # # #   AND (
# # # # #       table_name = 'cases'
# # # # #       OR column_name ILIKE '%disposition%'
# # # # #       OR column_name ILIKE '%judgment%'
# # # # #       OR column_name ILIKE '%settlement%'
# # # # #       OR column_name ILIKE '%outcome%'
# # # # #   )
# # # # # ORDER BY table_name, ordinal_position;
# # # # # """

# # # # # query = """
# # # # # SELECT
# # # # #     table_name,
# # # # #     column_name,
# # # # #     data_type
# # # # # FROM information_schema.columns
# # # # # WHERE table_schema = 'public'
# # # # #   AND table_name IN ('judgments', 'judgment_awards')
# # # # # ORDER BY table_name, ordinal_position;
# # # # # """

# # # # # query = """
# # # # # SELECT
# # # # #     judgment_type,
# # # # #     judgment_method,
# # # # #     COUNT(*) AS n
# # # # # FROM public.judgments
# # # # # GROUP BY judgment_type, judgment_method
# # # # # ORDER BY n DESC
# # # # # LIMIT 30;
# # # # # """

# # # # # query = """
# # # # # SELECT
# # # # #     case_status,
# # # # #     COUNT(*) AS n
# # # # # FROM public.cases
# # # # # GROUP BY case_status
# # # # # ORDER BY n DESC;
# # # # # """

# # # # # query = """
# # # # # SELECT
# # # # #     table_name
# # # # # FROM information_schema.tables
# # # # # WHERE table_schema = 'public'
# # # # #   AND (
# # # # #       table_name ILIKE '%action%'
# # # # #       OR table_name ILIKE '%docket%'
# # # # #       OR table_name ILIKE '%event%'
# # # # #       OR table_name ILIKE '%disposition%'
# # # # #   )
# # # # # ORDER BY table_name;
# # # # # """

# # # # # query = """
# # # # # SELECT
# # # # #     COUNT(*) AS total_judgments,
# # # # #     COUNT(DISTINCT case_id) AS cases_with_judgments,
# # # # #     COUNT(*) FILTER (
# # # # #         WHERE for_party_id IS NOT NULL
# # # # #     ) AS with_for_party,
# # # # #     COUNT(*) FILTER (
# # # # #         WHERE against_party_id IS NOT NULL
# # # # #     ) AS with_against_party,
# # # # #     COUNT(*) FILTER (
# # # # #         WHERE for_party_id IS NOT NULL
# # # # #           AND against_party_id IS NOT NULL
# # # # #     ) AS with_both_parties,
# # # # #     COUNT(*) FILTER (
# # # # #         WHERE judgment_date IS NOT NULL
# # # # #     ) AS with_date
# # # # # FROM public.judgments;
# # # # # """

# # # # # query = """
# # # # # SELECT
# # # # #     award_type,
# # # # #     COUNT(*) AS n,
# # # # #     COUNT(amount) AS with_amount,
# # # # #     SUM(amount) AS total_amount
# # # # # FROM public.judgment_awards
# # # # # GROUP BY award_type
# # # # # ORDER BY n DESC;
# # # # # """

# # # # # query = """
# # # # # SELECT
# # # # #     table_name,
# # # # #     column_name,
# # # # #     data_type
# # # # # FROM information_schema.columns
# # # # # WHERE table_schema = 'public'
# # # # #   AND table_name IN ('case_actions', 'events')
# # # # # ORDER BY table_name, ordinal_position;
# # # # # """

# # # # # query = """
# # # # # SELECT 'case_actions' AS table_name, COUNT(*) AS n
# # # # # FROM public.case_actions

# # # # # UNION ALL

# # # # # SELECT 'events' AS table_name, COUNT(*) AS n
# # # # # FROM public.events;
# # # # # """

# # # # # query = """
# # # # # SELECT *
# # # # # FROM public.judgment_awards
# # # # # LIMIT 10;
# # # # # """

# # # # # query = """
# # # # # SELECT award_type, amount
# # # # # FROM public.judgment_awards
# # # # # LIMIT 20;
# # # # # """

# # # # # query = """
# # # # # SELECT
# # # # #     case_id,
# # # # #     docket_date,
# # # # #     action,
# # # # #     docket_text,
# # # # #     amount_owed
# # # # # FROM public.case_actions
# # # # # WHERE docket_text IS NOT NULL
# # # # # LIMIT 20;
# # # # # """

# # # # # query = """
# # # # # SELECT
# # # # #     relname AS table_name,
# # # # #     n_live_tup AS estimated_rows
# # # # # FROM pg_stat_user_tables
# # # # # WHERE schemaname = 'public'
# # # # #   AND relname IN ('case_actions', 'events', 'judgment_awards');
# # # # # """

# # # # # query = """
# # # # # SELECT
# # # # #     COUNT(DISTINCT cp.case_id) AS municipal_defendant_cases,
# # # # #     COUNT(DISTINCT j.case_id) AS cases_with_judgments
# # # # # FROM public.case_parties cp
# # # # # JOIN public.parties p
# # # # #     ON cp.party_id = p.party_id
# # # # # LEFT JOIN public.judgments j
# # # # #     ON cp.case_id = j.case_id
# # # # # WHERE cp.party_type ILIKE '%defendant%'
# # # # #   AND (
# # # # #       p.party_name ILIKE '%City of %'
# # # # #       OR p.party_name ILIKE '%Town of %'
# # # # #   );
# # # # # """


# # # # with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
# # # #     with conn.cursor() as cur:
# # # #         cur.execute("SET TRANSACTION READ ONLY")
# # # #         cur.execute(query)

# # # #         for row in cur.fetchall():
# # # #             print(row)

# # # import os

# # # import pandas as pd
# # # import psycopg2

# # # df = pd.read_csv("data/analysis/municipal_case_parties.csv")

# # # defendant_ids = (
# # #     df.loc[
# # #         df["party_type"].str.contains(
# # #             "defendant", case=False, na=False
# # #         ),
# # #         "case_id"
# # #     ]
# # #     .dropna()
# # #     .astype("int64")
# # #     .unique()
# # #     .tolist()
# # # )

# # # print(f"Municipal defendant cases: {len(defendant_ids):,}")

# # # # with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
# # # #     with conn.cursor() as cur:
# # # #         cur.execute("""
# # # #             SELECT
# # # #                 COUNT(DISTINCT j.case_id) AS cases_with_judgments,
# # # #                 COUNT(*) AS total_judgments
# # # #             FROM public.judgments j
# # # #             WHERE j.case_id = ANY(%s::bigint[]);
# # # #         """, (defendant_ids,))

# # # #         cases_with_judgments, total_judgments = cur.fetchone()

# # # #         print(f"Cases with judgments: {cases_with_judgments:,}")
# # # #         print(f"Total judgments: {total_judgments:,}")
# # # #         print(
# # # #             f"Judgment coverage: "
# # # #             f"{cases_with_judgments / len(defendant_ids) * 100:.2f}%"
# # # #         )

# # # # with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
# # # #     with conn.cursor() as cur:
# # # #         cur.execute("""
# # # #             SELECT
# # # #                 c.case_status,
# # # #                 COUNT(*) AS n
# # # #             FROM public.cases c
# # # #             WHERE c.case_id = ANY(%s::bigint[])
# # # #             GROUP BY c.case_status
# # # #             ORDER BY n DESC;
# # # #         """, (defendant_ids,))

# # # #         for row in cur.fetchall():
# # # #             print(row)

# # # # with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
# # # #     with conn.cursor() as cur:
# # # #         cur.execute("""
# # # #             SELECT
# # # #                 COUNT(DISTINCT ca.case_id) AS cases_with_actions,
# # # #                 COUNT(*) AS total_actions
# # # #             FROM public.case_actions ca
# # # #             WHERE ca.case_id = ANY(%s::bigint[]);
# # # #         """, (defendant_ids,))

# # # #         cases_with_actions, total_actions = cur.fetchone()

# # # #         print(f"Cases with docket entries: {cases_with_actions:,}")
# # # #         print(f"Total docket entries: {total_actions:,}")
# # # #         print(
# # # #             f"Docket coverage: "
# # # #             f"{cases_with_actions / len(defendant_ids) * 100:.2f}%"
# # # #         )

# # # # with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
# # # #     with conn.cursor() as cur:
# # # #         cur.execute("""
# # # #             WITH judgment_cases AS (
# # # #                 SELECT DISTINCT case_id
# # # #                 FROM public.judgments
# # # #                 WHERE case_id = ANY(%s::bigint[])
# # # #             )
# # # #             SELECT
# # # #                 c.case_type,
# # # #                 COUNT(*) AS total_cases,
# # # #                 COUNT(j.case_id) AS cases_with_judgments,
# # # #                 ROUND(
# # # #                     100.0 * COUNT(j.case_id)
# # # #                     / NULLIF(COUNT(*), 0),
# # # #                     2
# # # #                 ) AS coverage_pct
# # # #             FROM public.cases c
# # # #             LEFT JOIN judgment_cases j
# # # #                 ON c.case_id = j.case_id
# # # #             WHERE c.case_id = ANY(%s::bigint[])
# # # #             GROUP BY c.case_type
# # # #             ORDER BY total_cases DESC;
# # # #         """, (defendant_ids, defendant_ids))

# # # #         for row in cur.fetchall():
# # # #             print(row)

# # import pandas as pd

# # actions = pd.read_csv(
# #     "data/analysis/municipal_defendant_actions.csv"
# # )

# # target_actions = [
# #     "Stipulation of dismissal",
# #     "Dismissal",
# #     "Voluntary Dismissal",
# #     "Agreement for Judgment",
# #     "Judgment",
# #     "Notice of dismissal",
# #     "Settlement agreement",
# #     "Satisfaction of judgment",
# # ]

# # for action in target_actions:
# #     subset = actions[
# #         actions["action"].eq(action)
# #     ]

# #     print(f"\n{'=' * 80}")
# #     print(f"{action}: {len(subset):,} entries")
# #     print(f"{'=' * 80}")

# #     for _, row in subset.sample(
# #         n=min(5, len(subset)),
# #         random_state=42,
# #     ).iterrows():
# #         print(f"\nCase: {row['case_id']}")
# #         print(f"Date: {row['docket_date']}")
# #         print(f"Text: {row['docket_text']}")

# import pandas as pd

# actions = pd.read_csv(
#     "data/analysis/municipal_defendant_actions.csv"
# )

# outcome_actions = [
#     "Stipulation of dismissal",
#     "Dismissal",
#     "Voluntary Dismissal",
#     "Agreement for Judgment",
#     "Judgment",
#     "Settlement agreement",
# ]

# outcomes = actions[
#     actions["action"].isin(outcome_actions)
# ]

# print("Outcome-related docket entries:", len(outcomes))
# print("Cases with outcome-related entries:", outcomes["case_id"].nunique())

# print("\nCases by outcome action:")

# summary = (
#     outcomes.groupby("action")
#     .agg(
#         entries=("case_id", "size"),
#         unique_cases=("case_id", "nunique"),
#     )
#     .sort_values("unique_cases", ascending=False)
# )

# print(summary.to_string())

# print(
#     "\nPreliminary docket outcome coverage:",
#     f"{outcomes['case_id'].nunique() / 27138 * 100:.2f}%"
# )

import os

import pandas as pd
import psycopg2

outcome_actions = {
    "Stipulation of dismissal",
    "Dismissal",
    "Voluntary Dismissal",
    "Agreement for Judgment",
    "Judgment",
    "Settlement agreement",
}

actions = pd.read_csv(
    "data/analysis/municipal_defendant_actions.csv",
    low_memory=False,
)

df = pd.read_csv("data/analysis/municipal_case_parties.csv")

defendant_ids = (
    df.loc[
        df["party_type"].str.contains("defendant", case=False, na=False),
        "case_id",
    ]
    .dropna()
    .astype("int64")
    .unique()
    .tolist()
)

actions["case_id"] = pd.to_numeric(
    actions["case_id"], errors="coerce"
).astype("Int64")

known_outcome_ids = set(
    actions.loc[
        actions["action"].isin(outcome_actions),
        "case_id",
    ].dropna().astype("int64")
)

with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT case_id, case_status
            FROM public.cases
            WHERE case_id = ANY(%s::bigint[]);
        """, (defendant_ids,))

        statuses = pd.DataFrame(
            cur.fetchall(),
            columns=["case_id", "case_status"],
        )

closed = statuses[
    statuses["case_status"].isin([
        "Closed",
        "Disposed - Statistical Purposes",
    ])
]

unresolved_ids = set(closed["case_id"]) - known_outcome_ids

# print(f"Closed/disposed cases: {len(closed):,}")
# print(f"Closed/disposed without identified outcome: {len(unresolved_ids):,}")

unresolved_actions = actions[
    actions["case_id"].isin(unresolved_ids)
]

# print("\nMost common actions in these cases:")
# print(
#     unresolved_actions["action"]
#     .value_counts()
#     .head(50)
#     .to_string()
# )

# target_actions = [
#     "Event resulted",
#     "Motion allowed",
#     "Notice of dismissal",
#     "Case inactivated",
#     "Motion for summary judgment",
#     "Motion denied",
#     "Default",
#     "Order Nisi for Dismissal",
# ]

# for action in target_actions:
#     subset = unresolved_actions[
#         unresolved_actions["action"] == action
#     ]

#     print(f"\n{'=' * 80}")
#     print(f"{action}: {len(subset):,} entries")
#     print(f"{'=' * 80}")

#     for _, row in subset.sample(
#         n=min(8, len(subset)),
#         random_state=42,
#     ).iterrows():
#         print(f"\nCase ID: {row['case_id']}")
#         print(f"Date: {row['docket_date']}")
#         print(f"Text: {row['docket_text']}")


# with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
#     with conn.cursor() as cur:
#         cur.execute("""
#             SELECT DISTINCT case_id
#             FROM public.judgments
#             WHERE case_id = ANY(%s::bigint[]);
#         """, (list(unresolved_ids),))

#         judgment_ids = {row[0] for row in cur.fetchall()}

# print(f"Unresolved closed/disposed cases: {len(unresolved_ids):,}")
# print(f"With structured judgments: {len(judgment_ids):,}")
# print(
#     f"Still without either outcome source: "
#     f"{len(unresolved_ids - judgment_ids):,}"
# )

with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT case_id
            FROM public.judgments
            WHERE case_id = ANY(%s::bigint[]);
        """, (list(unresolved_ids),))

        judgment_ids = {row[0] for row in cur.fetchall()}

print(f"Unresolved closed/disposed cases: {len(unresolved_ids):,}")
print(f"With structured judgments: {len(judgment_ids):,}")
print(
    f"Still without either outcome source: "
    f"{len(unresolved_ids - judgment_ids):,}"
)

import pandas as pd

remaining_ids = unresolved_ids - judgment_ids

remaining = actions[
    actions["case_id"].isin(remaining_ids)
].copy()

remaining["docket_text"] = remaining["docket_text"].fillna("")
remaining["action"] = remaining["action"].fillna("")

patterns = {
    "notice_of_dismissal": r"^Notice of dismissal$",
    "judgment_of_dismissal": r"\bjudgment of dismissal\b",
    "dismissal_entered": r"\b(?:dismissal|dismissed)\s+(?:has been\s+)?entered\b",
    "settlement_reported": r"\bsettlement reported\b",
    "judgment_entered": r"\bjudgment (?:has been |was )?entered\b",
    "summary_judgment_allowed": (
        r"\b(?:motion for )?summary judgment\b"
        r".{0,100}\b(?:allowed|granted)\b"
    ),
    "motion_to_dismiss_allowed": (
        r"\bmotion to dismiss\b"
        r".{0,100}\b(?:allowed|granted)\b"
    ),
}

results = []

for label, pattern in patterns.items():
    mask = (
        remaining["action"].str.contains(
            pattern, case=False, regex=True
        )
        |
        remaining["docket_text"].str.contains(
            pattern, case=False, regex=True
        )
    )

    subset = remaining[mask]

    results.append({
        "category": label,
        "entries": len(subset),
        "unique_cases": subset["case_id"].nunique(),
    })

    # print(f"\n{label}")
    # for _, row in subset.sample(
    #     n=min(3, len(subset)),
    #     random_state=42
    # ).iterrows():
    #     print(
    #         f"Case {row['case_id']}: "
    #         f"{row['docket_text'][:500]}"
    #     )

# print("\nSUMMARY")
# print(pd.DataFrame(results).to_string(index=False))


candidate_patterns = {
    "notice_of_dismissal": r"^Notice of dismissal$",
    "judgment_of_dismissal": r"\bjudgment of dismissal\b",
    "dismissal_entered": r"\b(?:dismissal|dismissed)\s+(?:has been\s+)?entered\b",
    "settlement_reported": r"\bsettlement reported\b",
    "judgment_entered": r"\bjudgment (?:has been |was )?entered\b",
    "summary_judgment_allowed": (
        r"\b(?:motion for )?summary judgment\b"
        r".{0,100}\b(?:allowed|granted)\b"
    ),
    "motion_to_dismiss_allowed": (
        r"\bmotion to dismiss\b"
        r".{0,100}\b(?:allowed|granted)\b"
    ),
}

candidate_ids = set()

for label, pattern in candidate_patterns.items():
    mask = (
        remaining["action"].str.contains(
            pattern, case=False, regex=True
        )
        |
        remaining["docket_text"].str.contains(
            pattern, case=False, regex=True
        )
    )

    candidate_ids.update(
        remaining.loc[mask, "case_id"].dropna().astype(int)
    )

print(f"Previously unidentified cases: {len(remaining_ids):,}")
print(f"Cases with new candidate evidence: {len(candidate_ids):,}")
print(
    f"Potential coverage ceiling: "
    f"{(6961 + len(candidate_ids)) / 16692 * 100:.2f}%"
)