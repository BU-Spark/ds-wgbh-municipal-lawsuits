import os

import pandas as pd
import psycopg2

df = pd.read_csv("data/analysis/municipal_case_parties.csv")

defendant_ids = (
    df.loc[
        df["party_type"].str.contains(
            "defendant", case=False, na=False
        ),
        "case_id"
    ]
    .dropna()
    .astype("int64")
    .unique()
    .tolist()
)

print(f"Municipal defendant cases: {len(defendant_ids):,}")

query = """
SELECT
    ca.case_id,
    ca.docket_date,
    ca.action,
    ca.docket_text,
    ca.amount_owed
FROM public.case_actions ca
WHERE ca.case_id = ANY(%s::bigint[])
ORDER BY ca.case_id, ca.docket_date, ca.case_action_id;
"""

with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor(name="municipal_actions") as cur:
        cur.itersize = 10000
        cur.execute(query, (defendant_ids,))

        rows = []
        while batch := cur.fetchmany(10000):
            rows.extend(batch)
            print(f"Retrieved {len(rows):,} docket entries", end="\r")

actions = pd.DataFrame(
    rows,
    columns=[
        "case_id",
        "docket_date",
        "action",
        "docket_text",
        "amount_owed",
    ],
)

print(f"\nTotal docket entries: {len(actions):,}")

os.makedirs("data/analysis", exist_ok=True)

actions.to_csv(
    "data/analysis/municipal_defendant_actions.csv",
    index=False,
)

print("\nMost common docket actions:")
print(actions["action"].value_counts().head(50).to_string())

