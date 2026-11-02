
# Massachusetts Municipal Financial and Population Data

**Project:** Massachusetts Municipal Lawsuits  
**Semester:** Fall 2026  
**Data source:** Massachusetts Department of Revenue, Division of Local Services (DLS)

## Dataset Description

This dataset contains municipal financial and population information for all 351 cities and towns in Massachusetts. The data was collected to support an investigation of lawsuits involving Massachusetts municipalities, particularly whether lawsuit frequency and outcomes vary with municipal size and financial resources.

The dataset combines Schedule A General Fund revenue and expenditure reports with annual municipal population estimates. The resulting panel covers 2000-2025, although the two sources have different year ranges.

All raw and processed data is stored in the GitHub repository under the `data/` directory.

## Data Sources

The data was obtained from the Massachusetts Division of Local Services (DLS):

1. **Schedule A General Fund:** https://dls-gw.dor.state.ma.us/reports/rdPage.aspx?rdReport=ScheduleA.GenFund_MAIN
   - Municipal revenue and expenditure data
   - Fiscal years 2002-2025
   - 351 municipalities

2. **Municipal Population:** https://dls-gw.dor.state.ma.us/reports/rdPage.aspx?rdReport=Socioeconomic.Population.population_main
   - Annual municipal population estimates
   - Years 2000-2024
   - 351 municipalities

Both datasets are publicly available through the Massachusetts Department of Revenue.

## Data Collection

We developed `download_dls.py` to automate downloading the Schedule A reports. The script uses Playwright to interact with the DLS reporting interface and export separate Excel files for revenues and expenditures for each fiscal year.

This produced 48 Excel files covering fiscal years 2002-2025. The population data was downloaded separately as a single Excel workbook containing annual population figures for all municipalities.

The original files are stored in `data/raw/dls/` within the repository.

## Data Processing

The `combine_dls.py` script processes the downloaded files and creates a consistent municipality-year panel.

The script:

1. Reads the Schedule A revenue and expenditure workbooks.
2. Combines the financial records using municipality DOR codes and fiscal years.
3. Reshapes the population workbook from wide format into one row per municipality and year.
4. Performs a full outer join between the financial and population datasets using DOR code and year.
5. Fills county information using each municipality's DOR code.
6. Checks for duplicate records, missing years, and inconsistent municipality names.
7. Flags potentially incomplete financial records and negative financial values.

The original reported financial values are preserved.

## Repository Structure

All datasets are included in the repository under the `data/` directory.

```text
data/
+-- raw/
|   +-- dls/
|       +-- schedule_a/
|       |   +-- *.xlsx
|       +-- population.xlsx
+-- processed/
    +-- municipal_finances_2002_2025.csv
    +-- municipal_population_2000_2024.csv
    +-- municipal_panel_2000_2025.csv
    +-- dls_data_quality.csv
```

## Processed Files

The processing script produces four CSV files in `data/processed/`:

| File | Description | Rows |
|---|---|---:|
| `municipal_finances_2002_2025.csv` | Combined Schedule A revenues and expenditures | 8,424 |
| `municipal_population_2000_2024.csv` | Annual municipal population data | 8,775 |
| `municipal_panel_2000_2025.csv` | Combined financial and population panel | 9,126 |
| `dls_data_quality.csv` | Records flagged for potential data-quality issues | 93 |

The primary dataset is `municipal_panel_2000_2025.csv`. Each row represents one municipality-year observation, identified by its three-digit DOR code and year.

The panel includes municipality name, county, population, financial categories, and indicators showing whether population and financial records are available.

## Data Quality and Limitations

The datasets have different coverage periods. Population data begins in 2000 and ends in 2024, while Schedule A financial data begins in 2002 and ends in 2025. As a result, financial data is unavailable for 2000-2001 and population data is unavailable for 2025. Both sources overlap during 2002-2024.

There are also several issues in the financial reports:

- **13 municipality-year records** have both total revenues and total expenditures reported as zero. These may represent incomplete submissions rather than actual zero spending.
- **80 negative financial values** appear across revenue and expenditure categories. These may be legitimate accounting adjustments, but their meaning has not been individually verified.
- Population data is reported by calendar year, while Schedule A uses fiscal years. Matching the year labels does not mean the underlying reporting periods are identical.

These issues are documented in `data/processed/dls_data_quality.csv`. The combined panel includes `finance_zero_flag`, `has_population`, and `has_finances` to help identify records that should be excluded or reviewed for particular analyses.

No questionable financial values were automatically corrected or removed.

## Reproducibility

The data collection and processing scripts are included in the repository:

- `download_dls.py` - downloads Schedule A Excel reports.
- `combine_dls.py` - combines financial and population data and generates the data-quality report.

The original datasets are already included under `data/raw/dls/`. To regenerate the processed datasets, run the following command from the repository root:

```bash
python combine_dls.py
```

The processing script uses only the Python standard library. Downloading the Schedule A reports requires Playwright and a working browser environment.

## Intended Use

The dataset will be used alongside court records obtained through OpenCourt or other Massachusetts court data sources.

Potential analyses include comparing lawsuit frequency across municipalities, normalizing lawsuit counts by population, examining relationships between municipal spending and litigation, and comparing municipalities with similar financial resources.

The financial and population data alone does not identify lawsuits or establish any relationship between municipal finances and litigation outcomes. Those analyses will require matching court records to municipalities and accounting for differences in reporting coverage.

## Future Work

The next step is to integrate municipal lawsuit records once the relevant court data becomes available. This will require standardizing municipality names, matching defendants to DOR codes, and determining which cases should count as lawsuits involving municipal governments.

Additional work may include investigating the flagged financial records, obtaining more recent population estimates, and identifying financial measures most appropriate for comparing municipalities.
