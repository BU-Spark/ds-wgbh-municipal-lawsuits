#!/usr/bin/env python3
"""Merge Massachusetts municipal litigation with DLS finances."""

from pathlib import Path
import os
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "processed"
MC = Path(os.environ.get("LITIGATION_REBUILD_DIR", str(BASE / "masscourts")))
MC.mkdir(parents=True, exist_ok=True)

DLS_PATH = ROOT / "data" / "analysis" / "municipal_panel_2000_2025.csv"
LIT_PATH = MC / "municipal_litigation_fy_2002_2025.csv"
OUTPUT = MC / "municipal_litigation_finances_2000_2025.csv"

dls = pd.read_csv(DLS_PATH, dtype={"dor_code": str})
lit = pd.read_csv(LIT_PATH, dtype={"dor_code": str})

# Normalize municipality identifiers.
# DLS codes may appear as 1, 01, or 001.
dls["dor_code"] = dls["dor_code"].str.strip().str.zfill(3)
lit["dor_code"] = lit["dor_code"].str.strip().str.zfill(3)

dls["year"] = pd.to_numeric(dls["year"], errors="raise").astype(int)
lit["fiscal_year"] = pd.to_numeric(
    lit["fiscal_year"], errors="raise"
).astype(int)

# Ensure uniqueness before merging.
assert not dls.duplicated(["dor_code", "year"]).any()
assert not lit.duplicated(["dor_code", "fiscal_year"]).any()

# Drop duplicate municipality name from litigation data.
lit = lit.drop(columns=["municipality"])

merged = dls.merge(
    lit,
    left_on=["dor_code", "year"],
    right_on=["dor_code", "fiscal_year"],
    how="left",
    validate="one_to_one",
    indicator=True,
)

print("Merge status:")
print(merged["_merge"].value_counts())

# Distinguish years without litigation coverage.
merged["has_litigation_data"] = (
    merged["_merge"] == "both"
).astype(int)

# FY2000-FY2001 are outside the litigation panel.
# Leave litigation counts missing rather than assigning zero.
merged = merged.drop(columns=["_merge", "fiscal_year"])

# Population-adjusted litigation measures.
# Rates per 10,000 residents.
for col in [
    "cases_total",
    "cases_plaintiff",
    "cases_defendant",
    "cases_tax_lien",
    "cases_housing",
    "cases_tort_defendant",
    "cases_admin_defendant",
    "outcome_dismissal",
    "outcome_judgment",
    "outcome_municipality_favored",
    "outcome_municipality_adverse",
    "outcome_unknown",
]:
    merged[col + "_per_10k"] = (
        merged[col]
        / merged["population"].where(merged["population"] > 0)
        * 10000
    )

merged = merged.sort_values(
    ["dor_code", "year"]
).reset_index(drop=True)

assert len(merged) == len(dls)
assert merged["dor_code"].nunique() == 351

merged.to_csv(OUTPUT, index=False)

print("\nOutput:", OUTPUT)
print("Rows:", len(merged))
print("Municipalities:", merged["dor_code"].nunique())
print("Years:", merged["year"].min(), "-", merged["year"].max())

print("\nAvailability by year:")
print(
    merged.groupby("year")[
        ["has_population", "has_finances", "has_litigation_data"]
    ].sum().to_string()
)

print("\nMissing litigation counts:")
print(merged["cases_total"].isna().sum())

print("\nMissing population:")
print(merged["population"].isna().sum())
