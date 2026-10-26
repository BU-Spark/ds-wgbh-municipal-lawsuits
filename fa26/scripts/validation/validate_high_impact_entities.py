from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MASSCOURTS = ROOT / "data" / "processed" / "masscourts"
BASE = MASSCOURTS / "versions" / "v33"
OUT = MASSCOURTS / "validation" / "initial"
OUT.mkdir(parents=True, exist_ok=True)

matched = pd.read_csv(
    BASE / "municipal_entities_matched.csv",
    dtype={"party_id": str, "dor_code": str},
)

parties = pd.read_csv(
    MASSCOURTS / "municipal_case_parties.csv",
    dtype={"party_id": str, "case_id": str, "dor_code": str},
)

# Count distinct cases associated with each matched party ID.
case_counts = (
    parties.groupby("party_id")["case_id"]
    .nunique()
    .rename("case_count")
    .reset_index()
)

ranked = matched.merge(
    case_counts,
    on="party_id",
    how="left",
    validate="one_to_one",
)

ranked["case_count"] = (
    ranked["case_count"].fillna(0).astype(int)
)

ranked = ranked.sort_values("case_count", ascending=False)

# Select the 50 highest-impact entities.
top = ranked.head(50).copy()

top["original_classification"] = "matched"
top["sample_group"] = "high_impact"
top["manual_classification"] = ""
top["reviewer_notes"] = ""
top["reviewed_by"] = ""

output = OUT / "high_impact_validation.csv"
top.to_csv(output, index=False)

print("\nTop 20 entities:")
print(
    top[
        ["party_name", "municipality", "case_count", "match_reason"]
    ].head(20).to_string(index=False)
)

print("\nTotal cases associated with top 50:",
      top["case_count"].sum())

print("\nSaved:", output)
