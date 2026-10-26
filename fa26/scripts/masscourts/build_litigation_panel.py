#!/usr/bin/env python3
"""Build municipality-fiscal-year litigation panel from extracted cases."""

from pathlib import Path
import os
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data" / "processed"
MC = Path(os.environ.get("LITIGATION_REBUILD_DIR", str(BASE / "masscourts")))
MC.mkdir(parents=True, exist_ok=True)

parties = pd.read_csv(
    MC / "municipal_case_parties.csv",
    dtype={"dor_code": str, "party_id": str, "case_id": str},
    keep_default_na=True,
)
cases = pd.read_csv(
    MC / "municipal_cases.csv",
    dtype={"dor_code": str, "case_id": str},
)

dls = pd.read_csv(
    ROOT / "data" / "analysis" / "municipal_panel_2000_2025.csv",
    dtype={"dor_code": str},
)

# Use the DLS municipality universe, retaining its DOR codes.
towns = dls[["dor_code", "municipality"]].drop_duplicates()

assert towns["dor_code"].nunique() == 351
assert not towns["dor_code"].duplicated().any()

# Assign cases to Massachusetts municipal fiscal years.
cases["file_date"] = pd.to_datetime(cases["file_date"])
cases["fiscal_year"] = (
    cases["file_date"].dt.year
    + (cases["file_date"].dt.month >= 7).astype(int)
)

# Normalize case types and roles.
parties["role"] = (
    parties["party_type"]
    .fillna("")
    .str.strip()
    .str.casefold()
)

parties["role_plaintiff"] = parties["role"].str.contains(
    r"plaintiff", regex=True
)

parties["role_defendant"] = parties["role"].str.contains(
    r"defendant|respondent", regex=True
)

parties["role_procedural"] = parties["role"].str.contains(
    r"trustee|garnishee|interested party|party in interest|"
    r"reach\s*(?:&|and)\s*apply",
    regex=True
)

parties["role_unknown"] = parties["role"].eq("")

# Aggregate party roles to one row per municipality and case.
keys = ["dor_code", "case_id"]

roles = (
    parties.groupby(keys, as_index=False)[
        [
            "role_plaintiff",
            "role_defendant",
            "role_procedural",
            "role_unknown",
        ]
    ]
    .max()
)

assert not roles.duplicated(keys).any()
assert not cases.duplicated(keys).any()

cases = cases.drop(
    columns=[
        "has_plaintiff",
        "has_defendant",
        "has_other_role",
        "has_procedural_party",
    ],
    errors="ignore",
)

cases = cases.merge(
    roles,
    on=keys,
    how="left",
    validate="one_to_one",
    indicator=True,
)

assert (cases["_merge"] == "both").all()
cases = cases.drop(columns="_merge")

case_type = cases["case_type"].fillna("").str.casefold()

cases["is_tax_lien"] = case_type.eq("tax lien")
cases["is_housing"] = case_type.str.contains("housing court")
cases["is_tort_defendant"] = (
    case_type.eq("torts") & cases["role_defendant"]
)
cases["is_admin_defendant"] = (
    case_type.str.contains("administrative")
    & cases["role_defendant"]
)

# Create numeric indicators.
indicators = {
    "cases_total": pd.Series(1, index=cases.index),
    "cases_plaintiff": cases["role_plaintiff"],
    "cases_defendant": cases["role_defendant"],
    "cases_tax_lien": cases["is_tax_lien"],
    "cases_housing": cases["is_housing"],
    "cases_tort_defendant": cases["is_tort_defendant"],
    "cases_admin_defendant": cases["is_admin_defendant"],
    "cases_procedural": cases["role_procedural"],
    "cases_role_unknown": cases["role_unknown"],
}

for name, values in indicators.items():
    cases[name] = values.astype(int)

metrics = list(indicators)

annual = (
    cases.groupby(["dor_code", "fiscal_year"], as_index=False)[metrics]
    .sum()
)

# Full municipality x fiscal year grid.
years = pd.DataFrame({"fiscal_year": range(2002, 2026)})
panel = towns.merge(years, how="cross")

panel = panel.merge(
    annual,
    on=["dor_code", "fiscal_year"],
    how="left",
    validate="one_to_one",
)

# Zero means no cases observed in the extracted data,
# not necessarily complete database coverage.
for metric in metrics:
    panel[metric] = panel[metric].fillna(0).astype(int)

# Coverage flags: preliminary, not verified completeness.
panel["early_coverage_caution"] = (
    panel["fiscal_year"] <= 2005
).astype(int)

panel["coverage_verified"] = 0

# Exclude the incomplete current fiscal year (FY2027).
panel = panel.sort_values(
    ["dor_code", "fiscal_year"]
).reset_index(drop=True)

assert len(panel) == 351 * 24
assert not panel.duplicated(
    ["dor_code", "fiscal_year"]
).any()

output = MC / "municipal_litigation_fy_2002_2025.csv"
panel.to_csv(output, index=False)

print("Output:", output)
print("Panel rows:", len(panel))
print("Municipalities:", panel["dor_code"].nunique())
print("Fiscal years:", panel["fiscal_year"].min(),
      "-", panel["fiscal_year"].max())
print("\nObserved totals:")
print(panel[metrics].sum().to_string())
print("\nCases by fiscal year:")
print(
    panel.groupby("fiscal_year")[
        ["cases_total", "cases_plaintiff", "cases_defendant"]
    ].sum().to_string()
)
