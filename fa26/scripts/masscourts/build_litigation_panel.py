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
dls["dor_code"] = dls["dor_code"].astype("string").str.strip().str.zfill(3)
towns = dls[["dor_code", "municipality"]].drop_duplicates()

assert towns["dor_code"].nunique() == 351
assert not towns["dor_code"].duplicated().any()

# Assign cases to Massachusetts municipal fiscal years.
cases["file_date"] = pd.to_datetime(cases["file_date"])
cases["fiscal_year"] = (
    cases["file_date"].dt.year
    + (cases["file_date"].dt.month >= 7).astype(int)
)

# Standardize join keys before grouping roles or joining outcomes.
for frame in (parties, cases):
    frame["case_id"] = frame["case_id"].astype("string").str.strip()
    frame["dor_code"] = frame["dor_code"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(3)

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

# V2 has multiple municipality rows per case, and DOR codes may be inconsistent.
# Match on case_id + municipality name, preserving the master DOR code.
outcomes_path = ROOT / "data/analysis/outcomes_v2/municipal_case_outcomes_enriched.csv"
outcomes = pd.read_csv(outcomes_path, dtype={"case_id": str})
for frame in (cases, outcomes):
    frame["case_id"] = frame["case_id"].astype("string").str.strip()
    frame["municipality_key"] = frame["municipality"].astype("string").str.strip().str.casefold()
join_keys = ["case_id", "municipality_key"]
assert not cases.duplicated(join_keys).any(), "Duplicate master case-municipality names"
assert not outcomes.duplicated(join_keys).any(), "Duplicate v2 case-municipality names"
needed = ["v2_disposition_type", "v2_municipality_outcome", "disposition_date", "v2_finality", "review_flags"]
assert set(needed).issubset(outcomes.columns), "Missing expected v2 columns"
cases = cases.merge(outcomes[join_keys + needed], on=join_keys, how="left", validate="one_to_one")
cases = cases.drop(columns="municipality_key")

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

# Outcomes are counted by filing fiscal year, not by disposition fiscal year.
# A separate disposition-year panel is written below.
valid = cases["role_defendant"].fillna(False)
disp = cases["v2_disposition_type"].fillna("unknown").astype(str)
result = cases["v2_municipality_outcome"].fillna("unknown").astype(str)
cases["outcome_v2_matched"] = valid & cases["v2_disposition_type"].notna()
cases["outcome_dismissal"] = valid & disp.isin(["dismissal", "stipulated_dismissal", "dismissal_judgment"])
cases["outcome_judgment"] = valid & disp.str.contains("judgment", case=False, regex=False) & ~disp.eq("tax_lien_judgment")
cases["outcome_tax_lien_judgment"] = valid & disp.eq("tax_lien_judgment")
cases["outcome_settlement"] = valid & disp.eq("settlement")
cases["outcome_settlement_signal"] = valid & disp.eq("settlement_signal_unconfirmed")
cases["outcome_disposition_unknown"] = valid & disp.eq("unknown")
for label in ("municipality_favored", "municipality_adverse", "dismissal_involving_municipality", "settled", "unknown"):
    cases["outcome_" + label] = valid & result.eq(label)

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
    "outcome_v2_matched": cases["outcome_v2_matched"],
    "outcome_dismissal": cases["outcome_dismissal"],
    "outcome_judgment": cases["outcome_judgment"],
    "outcome_tax_lien_judgment": cases["outcome_tax_lien_judgment"],
    "outcome_settlement": cases["outcome_settlement"],
    "outcome_settlement_signal": cases["outcome_settlement_signal"],
    "outcome_disposition_unknown": cases["outcome_disposition_unknown"],
    "outcome_municipality_favored": cases["outcome_municipality_favored"],
    "outcome_municipality_adverse": cases["outcome_municipality_adverse"],
    "outcome_dismissal_involving_municipality": cases["outcome_dismissal_involving_municipality"],
    "outcome_settled": cases["outcome_settled"],
    "outcome_unknown": cases["outcome_unknown"],
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

# Separate counts by fiscal year in which a disposition was recorded.
# These are recorded candidate dates, not verified final disposition dates.
cases["disposition_date"] = pd.to_datetime(cases["disposition_date"], errors="coerce")
cases["disposition_fiscal_year"] = cases["disposition_date"].dt.year + (cases["disposition_date"].dt.month >= 7).astype("Int64")
date_metrics = ["outcome_dismissal", "outcome_judgment", "outcome_tax_lien_judgment", "outcome_settlement", "outcome_municipality_favored", "outcome_municipality_adverse"]
by_date = cases.loc[cases["disposition_date"].notna()].groupby(["dor_code", "disposition_fiscal_year"], as_index=False)[date_metrics].sum()
by_date = by_date.rename(columns={"disposition_fiscal_year": "fiscal_year", **{x: "disposition_year_" + x for x in date_metrics}})
by_date = towns.merge(years, how="cross").merge(by_date, on=["dor_code", "fiscal_year"], how="left", validate="one_to_one")
for x in date_metrics:
    by_date["disposition_year_" + x] = by_date["disposition_year_" + x].fillna(0).astype(int)
by_date.to_csv(MC / "municipal_dispositions_fy_2002_2025.csv", index=False)

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