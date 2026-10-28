#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import plotly.express as px
from scipy.optimize import minimize
from scipy.special import gammaln

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "processed"

DATA = BASE / "municipal_litigation_finances_2000_2025.csv"
VISUALS = ROOT / "visuals"
VISUALS.mkdir(parents=True, exist_ok=True)

GEOJSON_URL = (
    "https://services1.arcgis.com/"
    "hGdibHYSPO59RG1h/arcgis/rest/services/"
    "Massachusetts_Municipalities/FeatureServer/1/query"
    "?where=1%3D1&outFields=TOWN,TOWN_ID"
    "&outSR=4326&f=geojson"
)

df = pd.read_csv(DATA, dtype={"dor_code": str})

df["dor_code"] = df["dor_code"].str.strip().str.zfill(3)

df = df[
    (df["year"] >= 2006)
    & (df["year"] <= 2024)
].copy()

print(f"Loaded {len(df):,} municipality-year observations")

municipal = (
    df.groupby(["dor_code", "municipality"], as_index=False)
    .agg(
        total_cases=("cases_total", "sum"),
        defendant_cases=("cases_defendant", "sum"),
        avg_population=("population", "mean"),
        population_years=("population", "sum"),
        observed_years=("population", "count"),
    )
)

municipal["exposure"] = municipal["population_years"] / 10000

municipal["defendant_rate"] = (
    municipal["defendant_cases"] / municipal["exposure"]
)

municipal["total_rate"] = (
    municipal["total_cases"] / municipal["exposure"]
)

municipal["annual_defendant_cases"] = (
    municipal["defendant_cases"] / municipal["observed_years"]
)

print(f"Municipalities in litigation data: {len(municipal)}")

# Fit Gamma prior for municipality-specific Poisson rates.
# Y_i | lambda_i ~ Poisson(exposure_i * lambda_i)
# lambda_i ~ Gamma(shape=a, rate=b)

counts = municipal["defendant_cases"].to_numpy(dtype=float)
exposures = municipal["exposure"].to_numpy(dtype=float)

valid = (
    np.isfinite(counts)
    & np.isfinite(exposures)
    & (exposures > 0)
)

if not valid.all():
    raise ValueError("Missing or invalid case counts or population exposure.")

counts = counts[valid]
exposures = exposures[valid]

statewide_rate = counts.sum() / exposures.sum()

def negative_log_likelihood(log_params):
    a, b = np.exp(log_params)

    log_prob = (
        gammaln(counts + a)
        - gammaln(a)
        - gammaln(counts + 1)
        + a * np.log(b)
        + counts * np.log(exposures)
        - (counts + a) * np.log(b + exposures)
    )

    return -np.sum(log_prob)

initial_a = 2.0
initial_b = initial_a / max(statewide_rate, 1e-8)

result = minimize(
    negative_log_likelihood,
    x0=np.log([initial_a, initial_b]),
    method="L-BFGS-B",
    bounds=[(-10, 15), (-10, 15)],
)

if not result.success:
    raise RuntimeError(f"Empirical Bayes fit failed: {result.message}")

a, b = np.exp(result.x)

municipal["defendant_rate_eb"] = (
    municipal["defendant_cases"] + a
) / (
    municipal["exposure"] + b
)

print(f"\nStatewide defendant rate: {statewide_rate:.3f}")
print(f"Gamma prior shape: {a:.3f}")
print(f"Gamma prior rate: {b:.3f}")
print(f"Prior mean: {a / b:.3f}")

print("\nDownloading Massachusetts municipal boundaries...")

geo = gpd.read_file(GEOJSON_URL)

print("Boundary columns:", geo.columns.tolist())
print("Boundary records:", len(geo))

def normalize_name(series):
    return (
        series.astype(str)
        .str.upper()
        .str.strip()
        .str.replace(r"[^A-Z0-9]", "", regex=True)
    )

geo["municipality_key"] = normalize_name(geo["TOWN"])

municipal["municipality_key"] = normalize_name(
    municipal["municipality"]
)

# total piece of shit naming convention. you need aliases
NAME_ALIASES = {
    "MANCHESTERBYTHESEA": "MANCHESTER",
}

geo["municipality_key"] = (
    geo["municipality_key"]
    .replace(NAME_ALIASES)
)

municipal["municipality_key"] = (
    municipal["municipality_key"]
    .replace(NAME_ALIASES)
)

assert len(geo) == 351, (
    f"Expected 351 municipality boundaries, got {len(geo)}"
)

assert geo["municipality_key"].is_unique, (
    "Duplicate municipality names in MassGIS boundaries"
)

assert municipal["municipality_key"].is_unique, (
    "Duplicate municipality names in litigation data"
)

gdf = geo.merge(
    municipal,
    on="municipality_key",
    how="left",
    validate="one_to_one",
    indicator=True,
)

print("\nMerge status:")
print(gdf["_merge"].value_counts())

unmatched = gdf[gdf["_merge"] != "both"]

if not unmatched.empty:
    print("\nUnmatched municipalities:")
    print(
        unmatched[
            ["TOWN", "municipality_key"]
        ].to_string(index=False)
    )

    raise ValueError(
        f"Municipality boundary matching incomplete: "
        f"{len(unmatched)} unmatched"
    )

assert len(gdf) == 351

gdf = gdf.drop(columns=["_merge"])

print("\nAll 351 municipalities matched successfully.")

gdf = gdf.to_crs("EPSG:4326")
gdf = gdf.reset_index(drop=True)
gdf["map_id"] = gdf.index.astype(str)

geojson = gdf.__geo_interface__

hover_data = {
    "defendant_cases": ":,",
    "total_cases": ":,",
    "annual_defendant_cases": ":.2f",
    "avg_population": ":,.0f",
    "defendant_rate": ":.2f",
    "defendant_rate_eb": ":.2f",
    "total_rate": ":.2f",
    "map_id": False,
}

labels = {
    "defendant_cases": "Defendant cases (total)",
    "total_cases": "All cases (total)",
    "annual_defendant_cases": "Defendant cases / year",
    "avg_population": "Average population",
    "defendant_rate": "Raw defendant rate / 10k / year",
    "defendant_rate_eb": "Smoothed defendant rate / 10k / year",
    "total_rate": "Total case rate / 10k / year",
}

maps = [
    {
        "column": "defendant_cases",
        "title": "Municipal Defendant Litigation: Total Cases (FY2006–2024)",
        "filename": "municipal_defendant_counts.html",
        "legend": "Total defendant<br>cases",
        "cap": True,
    },
    {
        "column": "defendant_rate",
        "title": "Municipal Defendant Litigation: Population-Adjusted Rates (FY2006–2024)",
        "filename": "municipal_defendant_rates.html",
        "legend": "Cases per 10k<br>residents / year",
        "cap": True,
    },
    {
        "column": "defendant_rate_eb",
        "title": "Municipal Defendant Litigation: Empirical Bayes Rates (FY2006–2024)",
        "filename": "municipal_defendant_rates_eb.html",
        "legend": "Smoothed cases per 10k<br>residents / year",
        "cap": True,
    },
]

for config in maps:
    column = config["column"]

    color_max = (
        np.nanpercentile(gdf[column], 95)
        if config["cap"]
        else gdf[column].max()
    )

    print(f"\n{column}: 95th percentile = {color_max:.3f}")

    fig = px.choropleth(
        gdf,
        geojson=geojson,
        locations="map_id",
        featureidkey="properties.map_id",
        color=column,
        hover_name="municipality",
        hover_data=hover_data,
        color_continuous_scale="Blues",
        range_color=(0, color_max),
        labels=labels,
        title=config["title"],
    )

    fig.update_geos(
        fitbounds="locations",
        visible=False,
        showcoastlines=False,
        showland=False,
        bgcolor="white",
    )

    fig.update_traces(
        marker_line_color="rgba(50, 65, 85, 0.5)",
        marker_line_width=0.45,
    )

    fig.update_layout(
        height=850,
        margin=dict(l=20, r=20, t=80, b=20),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(
            family="Arial",
            size=13,
            color="#24364B",
        ),
        title=dict(
            x=0.5,
            xanchor="center",
            font=dict(size=22),
        ),
        coloraxis_colorbar=dict(
            title=config["legend"],
            thickness=18,
            len=0.65,
            ticks="outside",
        ),
    )

    output = VISUALS / config["filename"]

    fig.write_html(
        output,
        include_plotlyjs=True,
        full_html=True,
    )

    print(f"Saved: {output}")

print("\nAll three maps generated successfully.")