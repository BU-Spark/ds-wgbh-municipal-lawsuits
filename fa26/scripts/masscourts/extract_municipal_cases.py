#!/usr/bin/env python3
"""Extract municipal litigation cases from MassCourtsPlus.

Inputs:
    municipal_entities_matched.csv

Outputs:
    municipal_case_parties.csv
    municipal_cases.csv

Requires:
    pip install psycopg2-binary

Database connection:
    DATABASE_URL or MASSCOURTS_DATABASE_URL environment variable
"""

import argparse
import csv
import os
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

import psycopg2


PARTY_FIELDS = [
    "dor_code",
    "municipality",
    "case_id",
    "case_number",
    "case_title",
    "case_type",
    "file_date",
    "party_id",
    "party_name",
    "party_type",
    "municipal_relationship",
    "match_confidence",
    "procedural_designation",
]

CASE_FIELDS = [
    "dor_code",
    "municipality",
    "case_id",
    "case_number",
    "case_title",
    "case_type",
    "file_date",
    "filing_year",
    "municipal_party_count",
    "municipal_party_roles",
    "has_plaintiff",
    "has_defendant",
    "has_other_role",
    "has_procedural_party",
]


def batches(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def load_registry(path):
    registry = {}

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        required = {
            "party_id",
            "party_name",
            "dor_code",
            "municipality",
        }

        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Registry is missing required columns")

        for row in reader:
            pid = row["party_id"]

            if pid in registry:
                raise ValueError(f"Duplicate party_id: {pid}")

            registry[pid] = row

    return registry


def initialize_cache(db):
    db.executescript("""
        CREATE TABLE cases (
            dor_code TEXT NOT NULL,
            municipality TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_number TEXT,
            case_title TEXT,
            case_type TEXT,
            file_date TEXT,
            filing_year TEXT,
            PRIMARY KEY (dor_code, case_id)
        );

        CREATE TABLE associations (
            dor_code TEXT NOT NULL,
            case_id TEXT NOT NULL,
            party_id TEXT NOT NULL,
            party_type TEXT NOT NULL,
            procedural_designation TEXT,
            PRIMARY KEY (
                dor_code, case_id, party_id, party_type
            )
        );

        CREATE INDEX idx_associations_case
        ON associations (dor_code, case_id);
    """)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--registry",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
    )

    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    url = os.environ.get("DATABASE_URL") or os.environ.get("MASSCOURTS_DATABASE_URL")

    if not url:
        raise RuntimeError(
            "Set DATABASE_URL or MASSCOURTS_DATABASE_URL before running."
        )

    registry = load_registry(args.registry)
    party_ids = list(registry)

    print(f"Loaded {len(party_ids):,} municipal party IDs", flush=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    party_output = args.output_dir / "municipal_case_parties.csv"
    case_output = args.output_dir / "municipal_cases.csv"

    counts = Counter()

    # Local temporary SQLite database for deduplication.
    with tempfile.TemporaryDirectory() as tempdir:
        cache_path = Path(tempdir) / "cases.sqlite"
        cache = sqlite3.connect(cache_path)
        initialize_cache(cache)

        conn = psycopg2.connect(
            url,
            connect_timeout=20,
            application_name="municipal_case_extraction",
        )

        try:
            conn.set_session(readonly=True, autocommit=True)

            with conn.cursor() as cur:
                # Determine the PostgreSQL party_id type so
                # array parameters can be cast correctly.
                cur.execute("""
                    SELECT pg_typeof(party_id)::text
                    FROM parties
                    LIMIT 1
                """)

                result = cur.fetchone()

                if not result:
                    raise RuntimeError("The parties table is empty")

                party_id_type = result[0]

                allowed_types = {
                    "integer",
                    "bigint",
                    "uuid",
                    "text",
                    "character varying",
                }

                if party_id_type not in allowed_types:
                    raise RuntimeError(
                        f"Unsupported party_id type: {party_id_type}"
                    )

            query = f"""
                SELECT
                    cp.case_id,
                    cp.party_id,
                    cp.party_type,
                    c.case_number,
                    c.case_title,
                    c.case_type,
                    c.file_date
                FROM case_parties AS cp
                JOIN cases AS c
                    ON c.case_id = cp.case_id
                WHERE cp.party_id = ANY(
                    %s::{party_id_type}[]
                )
            """

            with party_output.open(
                "w",
                newline="",
                encoding="utf-8",
            ) as f:

                writer = csv.DictWriter(
                    f,
                    fieldnames=PARTY_FIELDS,
                )
                writer.writeheader()

                total_batches = (
                    len(party_ids) + args.batch_size - 1
                ) // args.batch_size

                for batch_number, batch in enumerate(
                    batches(party_ids, args.batch_size),
                    start=1,
                ):
                    # Use a fresh cursor for each batch.
                    with conn.cursor() as cur:
                        cur.execute(query, (batch,))

                        while True:
                            rows = cur.fetchmany(5000)

                            if not rows:
                                break

                            for (
                                case_id,
                                party_id,
                                party_type,
                                case_number,
                                case_title,
                                case_type,
                                file_date,
                            ) in rows:

                                pid = str(party_id)
                                party = registry[pid]

                                code = party["dor_code"]
                                municipality = party["municipality"]

                                case_id = str(case_id)
                                role = str(party_type or "")

                                date_str = (
                                    file_date.isoformat()
                                    if file_date is not None
                                    else ""
                                )

                                record = {
                                    "dor_code": code,
                                    "municipality": municipality,
                                    "case_id": case_id,
                                    "case_number": case_number or "",
                                    "case_title": case_title or "",
                                    "case_type": case_type or "",
                                    "file_date": date_str,
                                    "party_id": pid,
                                    "party_name": party["party_name"],
                                    "party_type": role,
                                    "municipal_relationship": party.get(
                                        "municipal_relationship", ""
                                    ),
                                    "match_confidence": party.get(
                                        "match_confidence", ""
                                    ),
                                    "procedural_designation": party.get(
                                        "procedural_designation", ""
                                    ),
                                }

                                writer.writerow(record)

                                cache.execute("""
                                    INSERT OR IGNORE INTO cases
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    code,
                                    municipality,
                                    case_id,
                                    str(case_number or ""),
                                    str(case_title or ""),
                                    str(case_type or ""),
                                    date_str,
                                    date_str[:4] if date_str else "",
                                ))

                                cache.execute("""
                                    INSERT OR IGNORE INTO associations
                                    VALUES (?, ?, ?, ?, ?)
                                """, (
                                    code,
                                    case_id,
                                    pid,
                                    role,
                                    party.get(
                                        "procedural_designation", ""
                                    ),
                                ))

                                counts["party_rows"] += 1

                    cache.commit()

                    print(
                        f"Batch {batch_number}/{total_batches}: "
                        f"{counts['party_rows']:,} party-case rows",
                        flush=True,
                    )

        finally:
            conn.close()

        with case_output.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=CASE_FIELDS,
            )
            writer.writeheader()

            cursor = cache.execute("""
                SELECT
                    dor_code,
                    municipality,
                    case_id,
                    case_number,
                    case_title,
                    case_type,
                    file_date
                FROM cases
                ORDER BY municipality, file_date, case_id
            """)

            for (
                code,
                municipality,
                case_id,
                case_number,
                case_title,
                case_type,
                file_date,
            ) in cursor:

                associations = cache.execute("""
                    SELECT party_id, party_type,
                           procedural_designation
                    FROM associations
                    WHERE dor_code = ? AND case_id = ?
                """, (code, case_id)).fetchall()

                roles = {
                    role.strip()
                    for _, role, _ in associations
                    if role.strip()
                }

                role_lower = {role.casefold() for role in roles}

                has_plaintiff = "plaintiff" in role_lower
                has_defendant = "defendant" in role_lower

                procedural = any(
                    designation or role.casefold() in {
                        "trustee",
                        "garnishee",
                        "party in interest",
                    }
                    for _, role, designation in associations
                )

                other_roles = role_lower - {
                    "plaintiff",
                    "defendant",
                }

                writer.writerow({
                    "dor_code": code,
                    "municipality": municipality,
                    "case_id": case_id,
                    "case_number": case_number,
                    "case_title": case_title,
                    "case_type": case_type,
                    "file_date": file_date,
                    "filing_year": (
                        file_date[:4] if file_date else ""
                    ),
                    "municipal_party_count": len({
                        pid for pid, _, _ in associations
                    }),
                    "municipal_party_roles": "; ".join(
                        sorted(roles)
                    ),
                    "has_plaintiff": int(has_plaintiff),
                    "has_defendant": int(has_defendant),
                    "has_other_role": int(bool(other_roles)),
                    "has_procedural_party": int(procedural),
                })

                counts["municipality_cases"] += 1

        cache.close()

    print("\nExtraction complete")
    print(f"Party-case rows: {counts['party_rows']:,}")
    print(
        f"Distinct municipality-case rows: "
        f"{counts['municipality_cases']:,}"
    )
    print(f"Party output: {party_output}")
    print(f"Case output: {case_output}")


if __name__ == "__main__":
    main()
