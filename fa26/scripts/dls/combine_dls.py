
"""Combine Massachusetts DLS Schedule A and population data.

Run from fa26: python scripts/dls/combine_dls.py

Inputs:
  data/raw/dls/schedule_a/*.xlsx
  OR data/raw/dls/schedule_a.zip
  OR schedule_a.zip

  data/raw/dls/population.xlsx

Outputs:
  data/processed/dls/municipal_finances_2002_2025.csv
  data/processed/dls/municipal_population_2000_2024.csv
  data/analysis/municipal_panel_2000_2025.csv

  all stanard puython liebaraies
"""

from pathlib import Path
from io import BytesIO
import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict

FINANCE_START, FINANCE_END = 2002, 2025
POP_START, POP_END = 2000, 2024
EXPECTED_MUNICIPALITIES = 351

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "data" / "raw" / "dls" / "schedule_a"
ZIP_CANDIDATES = [
    ROOT / "data" / "raw" / "dls" / "schedule_a.zip",
    ROOT / "schedule_a.zip",
]
POPULATION_FILE = ROOT / "data" / "raw" / "dls" / "population.xlsx"

OUTPUT_DIR = ROOT / "data" / "processed" / "dls"
ANALYSIS_DIR = ROOT / "data" / "analysis"
FINANCE_OUTPUT = OUTPUT_DIR / "municipal_finances_2002_2025.csv"
POPULATION_OUTPUT = OUTPUT_DIR / "municipal_population_2000_2024.csv"
PANEL_OUTPUT = ANALYSIS_DIR / "municipal_panel_2000_2025.csv"
QUALITY_OUTPUT = OUTPUT_DIR / "dls_data_quality.csv"

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
}

PATTERN = re.compile(
    r"schedule_a_(revenues|expenditures)_(\d{4})\.xlsx$",
    re.I,
)


def column_index(cell_ref):
    letters = re.match(r"[A-Z]+", cell_ref).group()
    index = 0

    for ch in letters:
        index = index * 26 + ord(ch) - ord("A") + 1

    return index - 1


def read_xlsx(data):
    """Read first XLSX worksheet using Python standard library."""
    with zipfile.ZipFile(BytesIO(data)) as workbook:
        strings = []

        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ET.fromstring(
                workbook.read("xl/sharedStrings.xml")
            )
            strings = [
                "".join(
                    t.text or ""
                    for t in item.findall(".//m:t", NS)
                )
                for item in root.findall("m:si", NS)
            ]

        sheet = ET.fromstring(
            workbook.read("xl/worksheets/sheet1.xml")
        )

        rows = []

        for row in sheet.findall(".//m:sheetData/m:row", NS):
            values = {}

            for cell in row.findall("m:c", NS):
                raw = cell.find("m:v", NS)
                inline = cell.find("m:is", NS)

                value = (
                    raw.text
                    if raw is not None and raw.text is not None
                    else ""
                )

                if cell.get("t") == "s" and value:
                    value = strings[int(value)]
                elif cell.get("t") == "inlineStr" and inline is not None:
                    value = "".join(
                        t.text or ""
                        for t in inline.findall(".//m:t", NS)
                    )

                values[column_index(cell.attrib["r"])] = value.strip()

            if values:
                rows.append([
                    values.get(i, "")
                    for i in range(max(values) + 1)
                ])

    if not rows:
        raise ValueError("Empty worksheet")

    header = rows[0]

    return [
        dict(zip(
            header,
            row + [""] * (len(header) - len(row))
        ))
        for row in rows[1:]
    ]


def source_files():
    if SOURCE_DIR.is_dir():
        files = list(
            SOURCE_DIR.glob("schedule_a_*.xlsx")
        )

        if files:
            return [
                (f.name, f.read_bytes())
                for f in files
            ]

    for path in ZIP_CANDIDATES:
        if path.is_file():
            with zipfile.ZipFile(path) as archive:
                return [
                    (
                        Path(name).name,
                        archive.read(name),
                    )
                    for name in archive.namelist()
                    if PATTERN.fullmatch(
                        Path(name).name
                    )
                ]

    raise FileNotFoundError(
        "Schedule A workbooks not found."
    )


def normalize_code(value):
    value = str(value).strip()

    if re.fullmatch(r"\d+\.0", value):
        value = value.split(".")[0]

    if not value.isdigit():
        return None

    return value.zfill(3)


def normalize_name(value):
    return re.sub(
        r"\s+", " ", str(value).strip()
    ).casefold()


def write_csv(path, records, fields):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(records)

    print(
        f"SAVED {path}: "
        f"{len(records):,} rows, "
        f"{len(fields)} columns"
    )


def parse_number(value):
    """Convert financial strings to numbers without modifying source."""
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    value = value.replace(",", "").replace("$", "")

    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]

    try:
        return float(value)
    except ValueError:
        return None


def load_finances():
    records = {}
    columns = {
        "revenues": [],
        "expenditures": [],
    }
    seen_files = set()

    for filename, data in sorted(source_files()):
        match = PATTERN.fullmatch(filename)

        if not match:
            continue

        kind, year_text = match.groups()
        kind = kind.lower()
        year = int(year_text)

        if not FINANCE_START <= year <= FINANCE_END:
            continue

        if (kind, year) in seen_files:
            raise ValueError(
                f"Duplicate workbook: {kind} FY{year}"
            )

        seen_files.add((kind, year))
        count = 0

        for row in read_xlsx(data):
            code = normalize_code(
                row.get("DOR Code", "")
            )
            name = row.get(
                "Municipality", ""
            ).strip()

            if (
                not code
                or not name
                or name.lower().startswith("totals")
            ):
                continue

            fy = row.get(
                "Fiscal Year", ""
            ).strip()

            if fy != str(year):
                raise ValueError(
                    f"{filename}: {name} has FY{fy}, "
                    f"expected {year}"
                )

            key = (code, year)

            entry = records.setdefault(
                key,
                {
                    "dor_code": code,
                    "municipality": name,
                    "fiscal_year": str(year),
                },
            )

            if normalize_name(
                entry["municipality"]
            ) != normalize_name(name):
                raise ValueError(
                    f"Municipality mismatch for {key}"
                )

            marker = f"_{kind}_present"

            if marker in entry:
                raise ValueError(
                    f"Duplicate municipality "
                    f"{key} in {filename}"
                )

            entry[marker] = True

            for original, value in row.items():
                if (
                    original in (
                        "DOR Code",
                        "Municipality",
                        "Fiscal Year",
                    )
                    or not original.strip()
                ):
                    continue

                col = (
                    kind[:-1]
                    + "_"
                    + re.sub(
                        r"[^a-z0-9]+",
                        "_",
                        original.lower(),
                    ).strip("_")
                )

                if col not in columns[kind]:
                    columns[kind].append(col)

                entry[col] = value

            count += 1

        if count != EXPECTED_MUNICIPALITIES:
            raise ValueError(
                f"{filename}: expected 351 "
                f"municipalities, found {count}"
            )

        print(
            f"OK FY{year} {kind}: "
            f"{count} municipalities"
        )

    required = {
        (kind, year)
        for kind in (
            "revenues",
            "expenditures",
        )
        for year in range(
            FINANCE_START,
            FINANCE_END + 1,
        )
    }

    if seen_files != required:
        raise ValueError(
            "Missing workbooks: "
            f"{sorted(required - seen_files)}"
        )

    expected = (
        EXPECTED_MUNICIPALITIES
        * (
            FINANCE_END
            - FINANCE_START
            + 1
        )
    )

    if len(records) != expected:
        raise ValueError(
            f"Expected {expected} finance records; "
            f"got {len(records)}"
        )

    for key, row in records.items():
        if not (
            row.pop(
                "_revenues_present", False
            )
            and row.pop(
                "_expenditures_present", False
            )
        ):
            raise ValueError(
                "Unmatched revenue/expenditure "
                f"for {key}"
            )

    fields = (
        [
            "dor_code",
            "municipality",
            "fiscal_year",
        ]
        + columns["revenues"]
        + columns["expenditures"]
    )

    ordered = [
        records[key]
        for key in sorted(
            records,
            key=lambda k: (
                k[1], k[0]
            ),
        )
    ]

    write_csv(
        FINANCE_OUTPUT,
        ordered,
        fields,
    )

    return records, fields


def load_population():
    if not POPULATION_FILE.is_file():
        raise FileNotFoundError(
            f"Population file not found: "
            f"{POPULATION_FILE}"
        )

    rows = read_xlsx(
        POPULATION_FILE.read_bytes()
    )

    if not rows:
        raise ValueError(
            "Population workbook is empty"
        )

    headers = list(rows[0])

    code_col = next(
        (
            h for h in headers
            if re.search(
                r"\b(DOR\s*Code|DORCode)\b",
                h,
                re.I,
            )
        ),
        None,
    )

    name_col = next(
        (
            h for h in headers
            if re.search(
                r"municipality|city.?town",
                h,
                re.I,
            )
        ),
        None,
    )

    county_col = next(
        (
            h for h in headers
            if re.search(
                r"county", h, re.I
            )
        ),
        None,
    )

    if not code_col or not name_col:
        raise ValueError(
            "Could not identify DOR Code "
            "and Municipality columns. "
            f"Headers: {headers}"
        )

    year_columns = {}

    for header in headers:
        match = re.search(
            r"(?<!\d)(20\d{2})(?!\d)",
            header,
        )

        if not match:
            continue

        year = int(
            match.group(1)
        )

        if POP_START <= year <= POP_END:
            if year in year_columns:
                raise ValueError(
                    "Multiple population "
                    f"columns for {year}"
                )

            year_columns[year] = header

    expected_years = set(
        range(
            POP_START,
            POP_END + 1,
        )
    )

    if set(year_columns) != expected_years:
        raise ValueError(
            "Population year columns missing: "
            f"{sorted(expected_years - set(year_columns))}. "
            f"Headers: {headers}"
        )

    records = {}
    municipalities = set()

    for row in rows:
        code = normalize_code(
            row.get(code_col, "")
        )
        name = row.get(
            name_col, ""
        ).strip()

        if (
            not code
            or not name
            or name.lower().startswith("totals")
        ):
            continue

        if code in municipalities:
            raise ValueError(
                "Duplicate population "
                f"DOR code: {code}"
            )

        municipalities.add(code)

        county = (
            row.get(
                county_col, ""
            ).strip()
            if county_col
            else ""
        )

        for year, column in sorted(
            year_columns.items()
        ):
            value = row.get(
                column, ""
            ).strip()

            if value:
                cleaned = value.replace(
                    ",", ""
                )

                try:
                    numeric = float(
                        cleaned
                    )
                except ValueError:
                    raise ValueError(
                        "Invalid population: "
                        f"{name}, {year}: "
                        f"{value!r}"
                    )

                if (
                    numeric < 0
                    or not numeric.is_integer()
                ):
                    raise ValueError(
                        "Invalid population: "
                        f"{name}, {year}: "
                        f"{value!r}"
                    )

                value = str(
                    int(numeric)
                )

            key = (
                code, year
            )

            records[key] = {
                "dor_code": code,
                "municipality": name,
                "county": county,
                "year": str(year),
                "population": value,
            }

    if len(municipalities) != EXPECTED_MUNICIPALITIES:
        raise ValueError(
            "Expected 351 municipalities "
            "in population, found "
            f"{len(municipalities)}"
        )

    expected = (
        EXPECTED_MUNICIPALITIES
        * (
            POP_END
            - POP_START
            + 1
        )
    )

    if len(records) != expected:
        raise ValueError(
            "Expected "
            f"{expected} population records; "
            f"got {len(records)}"
        )

    fields = [
        "dor_code",
        "municipality",
        "county",
        "year",
        "population",
    ]

    ordered = [
        records[key]
        for key in sorted(
            records,
            key=lambda k: (
                k[1], k[0]
            ),
        )
    ]

    write_csv(
        POPULATION_OUTPUT,
        ordered,
        fields,
    )

    return records


def build_county_lookup(population):
    """Create stable DOR code -> county mapping."""
    counties = defaultdict(set)

    for (code, _), row in population.items():
        county = row.get(
            "county", ""
        ).strip()

        if county:
            counties[code].add(
                county
            )

    lookup = {}

    for code, values in counties.items():
        if len(values) != 1:
            raise ValueError(
                "Conflicting counties for "
                f"DOR code {code}: {values}"
            )

        lookup[code] = next(
            iter(values)
        )

    return lookup


def build_panel(finances, finance_fields, population):
    keys = set(finances) | set(population)

    county_lookup = build_county_lookup(
        population
    )

    panel = []

    for code, year in sorted(
        keys,
        key=lambda k: (
            k[1], k[0]
        ),
    ):
        finance = finances.get(
            (code, year)
        )
        pop = population.get(
            (code, year)
        )

        if finance and pop:
            if normalize_name(
                finance["municipality"]
            ) != normalize_name(
                pop["municipality"]
            ):
                raise ValueError(
                    "Municipality name mismatch: "
                    f"{code}, {year}: "
                    f"{finance['municipality']} "
                    f"vs {pop['municipality']}"
                )

        source = finance or pop

        entry = {
            "dor_code": code,
            "municipality": source["municipality"],
            "county": county_lookup.get(
                code, ""
            ),
            "year": str(year),
            "population": (
                pop.get(
                    "population", ""
                )
                if pop
                else ""
            ),
            "has_population": int(
                pop is not None
            ),
            "has_finances": int(
                finance is not None
            ),
        }

        if finance:
            for field in finance_fields:
                if field not in (
                    "dor_code",
                    "municipality",
                    "fiscal_year",
                ):
                    entry[field] = finance.get(
                        field, ""
                    )

        # Flag records with both totals equal to zero.
        # Do not alter the original financial values.
        zero_flag = 0

        if finance:
            revenue = parse_number(
                finance.get(
                    "revenue_total_revenues"
                )
            )
            expenditure = parse_number(
                finance.get(
                    "expenditure_total_expenditures"
                )
            )

            if (
                revenue is not None
                and expenditure is not None
                and revenue == 0
                and expenditure == 0
            ):
                zero_flag = 1

        entry["finance_zero_flag"] = zero_flag

        panel.append(
            entry
        )

    financial_columns = [
        field
        for field in finance_fields
        if field not in (
            "dor_code",
            "municipality",
            "fiscal_year",
        )
    ]

    fields = [
        "dor_code",
        "municipality",
        "county",
        "year",
        "population",
        "has_population",
        "has_finances",
        "finance_zero_flag",
    ] + financial_columns

    write_csv(
        PANEL_OUTPUT,
        panel,
        fields,
    )

    expected = (
        EXPECTED_MUNICIPALITIES
        * (
            max(
                FINANCE_END,
                POP_END,
            )
            - min(
                FINANCE_START,
                POP_START,
            )
            + 1
        )
    )

    if len(panel) != expected:
        raise ValueError(
            "Expected "
            f"{expected} panel records; "
            f"got {len(panel)}"
        )

    return panel, financial_columns


def create_quality_report(panel, financial_columns):
    """Report zero-total records and negative financial cells."""
    issues = []

    for row in panel:
        code = row["dor_code"]
        municipality = row["municipality"]
        year = row["year"]

        if row["finance_zero_flag"] == 1:
            issues.append({
                "dor_code": code,
                "municipality": municipality,
                "year": year,
                "issue_type": "zero_financial_totals",
                "field": (
                    "revenue_total_revenues / "
                    "expenditure_total_expenditures"
                ),
                "value": "0 / 0",
                "description": (
                    "Both total revenues and total "
                    "expenditures are zero; "
                    "possible missing submission."
                ),
            })

        if not row["has_finances"]:
            continue

        for field in financial_columns:
            value = parse_number(
                row.get(field)
            )

            if value is not None and value < 0:
                issues.append({
                    "dor_code": code,
                    "municipality": municipality,
                    "year": year,
                    "issue_type": "negative_financial_value",
                    "field": field,
                    "value": row.get(
                        field, ""
                    ),
                    "description": (
                        "Negative reported amount; "
                        "review accounting context."
                    ),
                })

    fields = [
        "dor_code",
        "municipality",
        "year",
        "issue_type",
        "field",
        "value",
        "description",
    ]

    write_csv(
        QUALITY_OUTPUT,
        issues,
        fields,
    )

    zero_count = sum(
        row["issue_type"] == "zero_financial_totals"
        for row in issues
    )

    negative_count = sum(
        row["issue_type"] == "negative_financial_value"
        for row in issues
    )

    print(
        f"\nData quality summary:"
        f"\n  Zero-total municipality-years: {zero_count}"
        f"\n  Negative financial cells: {negative_count}"
    )


def main():
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Processing Schedule A...")
    finances, finance_fields = load_finances()

    print("\nProcessing population...")
    population = load_population()

    print("\nBuilding combined panel...")
    panel, financial_columns = build_panel(
        finances,
        finance_fields,
        population,
    )

    print("\nChecking data quality...")
    create_quality_report(
        panel,
        financial_columns,
    )

    print(
        "\nDone."
        "\nExpected panel coverage: 2000-2025"
        "\nExpected municipalities: 351"
        "\nExpected panel rows: 9,126"
    )


if __name__ == "__main__":
    main()
