import os
from pathlib import Path
import pandas as pd
import psycopg2

ROOT = Path(__file__).resolve().parents[2]
validation = ROOT / "data" / "processed" / "masscourts" / "validation"
base = validation / "case_context"
base.mkdir(parents=True, exist_ok=True)
source = validation / "initial" / "municipal_entities_uncertain_researched.csv"

df = pd.read_csv(source, dtype={"party_id": str})

if "verified_label" in df.columns:
    df = df[
        df["verified_label"].fillna("").str.strip().str.lower() == "uncertain"
    ].copy()

ids = df["party_id"].dropna().unique().tolist()
print(f"Retrieving cases for {len(ids)} party IDs")

query = """
SELECT
    cp.party_id,
    cp.party_type,
    c.case_id,
    c.case_number,
    c.case_title,
    c.case_type,
    c.case_status,
    c.file_date,
    c.initiating_action
FROM public.case_parties cp
JOIN public.cases c ON c.case_id = cp.case_id
WHERE cp.party_id::text = ANY(%s)
ORDER BY cp.party_id, c.file_date DESC NULLS LAST
"""

with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(query, (ids,))
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

result = pd.DataFrame(rows, columns=columns)

if not result.empty:
    result["party_id"] = result["party_id"].astype(str)
    result = result.merge(
        df.drop_duplicates("party_id"),
        on="party_id",
        how="left",
        validate="many_to_one"
    )

output = base / "municipal_entity_case_context.csv"
result.to_csv(output, index=False)

print(f"Retrieved {len(result):,} case-party records")
print(f"Saved to: {output}")