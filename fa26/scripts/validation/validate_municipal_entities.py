from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MASSCOURTS = ROOT / "data" / "processed" / "masscourts"
BASE = MASSCOURTS / "versions" / "v33"
OUT = MASSCOURTS / "validation" / "initial"
OUT.mkdir(parents=True, exist_ok=True)

SEED = 42

matched = pd.read_csv(BASE / "municipal_entities_matched.csv")
review = pd.read_csv(BASE / "municipal_entities_review.csv")
excluded = pd.read_csv(BASE / "municipal_entities_excluded.csv")

print("Matched columns:", matched.columns.tolist())
print("Review columns:", review.columns.tolist())
print("Excluded columns:", excluded.columns.tolist())

# Use a common set of columns, retaining original classification details.
all_cols = list(dict.fromkeys(
    list(matched.columns)
    + list(review.columns)
    + list(excluded.columns)
))

def prepare(df, classification):
    df = df.reindex(columns=all_cols).copy()
    df["original_classification"] = classification
    return df

matched = prepare(matched, "matched")
review = prepare(review, "review")
excluded = prepare(excluded, "excluded")

# Random samples from each classification.
samples = []

for df, n in [
    (matched, 100),
    (review, 100),
    (excluded, 50),
]:
    sample = df.sample(
        n=min(n, len(df)),
        random_state=SEED,
    ).copy()

    sample["sample_group"] = "random"
    samples.append(sample)

validation = pd.concat(samples, ignore_index=True)

# Fields to complete manually.
validation["manual_classification"] = ""
validation["reviewer_notes"] = ""
validation["reviewed_by"] = ""

validation.to_csv(
    OUT / "entity_validation_sample.csv",
    index=False,
)

print("\nSample composition:")
print(
    validation.groupby(
        ["original_classification", "sample_group"]
    ).size()
)

print("\nSaved:")
print(OUT / "entity_validation_sample.csv")