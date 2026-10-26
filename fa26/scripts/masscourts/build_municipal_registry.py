#!/usr/bin/env python3
"""Conservative Massachusetts municipal party registry

Classifies exported MassCourtsPlus party candidates against the
351 Massachusetts municipalities.

Uses Python standard library only. Does not connect to the database.
"""

import argparse
import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = s.replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


BOARD = re.compile(
    r"\b(?:board|bd|commission|commision|committee|selectmen|"
    r"selectman|selectwoman|selectboard|planning|zoning|conservation)\b"
)

DEPT = re.compile(
    r"\b(?:police|fire|public works|dpw|inspectional|health dept|"
    r"school(?:s)? (?:dep|dept|department)|animal control|"
    r"code enforcement|sewer|water dept|building department|"
    r"highway dept|department|dept|dep)\b"
)

SEPARATE = re.compile(
    r"\b(?:housing authority|regional school|retirement board|"
    r"credit union|water district|gas (?:and )?electric|"
    r"municipal light plant|county agricultural|county school|"
    r"county government)\b"
)

PRIVATE = re.compile(
    r"\b(?:llc|inc|corporation|corp|insurance|realty|bank|"
    r"condominium|association|credit union|university|college)\b"
)

MUNICIPAL_CORPORATION = re.compile(r"\bmunicipal corporation\b")

# V3.3: Mixed federal and municipal parties
MIXED_FEDERAL_MUNICIPAL = re.compile(
    r"\b(?:united states(?: of america)?|"
    r"department of the treasury|federal government)\b"
)

# V3.3: Named individual employees
INDIVIDUAL_EMPLOYEE = re.compile(
    r"^(?:[a-z]+(?: [a-z]+){1,3})\s+"
    r"(?:employee|employed by|employee of|worker|"
    r"former employee|officer)\s+"
    r"(?:of|at|for|with)\b"
)

OFFICIAL_TITLE_LEAD = re.compile(
    r"^(?:the )?(?:police chief|chief of police|police commissioner|"
    r"fire chief|chief of fire|building inspector|"
    r"zoning enforcement officer|zoning officer)\b"
)

OFFICIAL_TITLE_ANY = re.compile(
    r"\b(?:chief of police|police chief|police commissioner|"
    r"fire chief|building inspector|zoning enforcement officer)\b"
)

DEPARTMENT_OF_PLACE = re.compile(
    r"^(?:the )?(?:department of [a-z0-9 ]+|"
    r"[a-z0-9 ]+ department|police department|fire department)"
    r"\s+of\s+(?:(?:the )?(?:city|town) of )?"
)

OFFICIAL = re.compile(
    r"\b(?:member|mbrs?|chairman|chairwoman|chairperson|"
    r"director|commissioner|chief of police|building inspector|"
    r"zoning officer|in (?:his|her|their) capacity|individually)\b"
)

PROCEDURAL = re.compile(
    r"\b(?:trustee|trustees|garnishee|party in interest|reach and apply)\b"
)

DIRECT_SUFFIX = re.compile(
    r"^(?:(?:of )?(?:mass|massachusetts|ma)|"
    r"(?:the )?(?:defendant|plaintiff|respondent|petitioner|"
    r"appellant|appellee|party in interest|trustee|trustees|garnishee))$"
)

PERSON_INTRO = re.compile(
    r"\b(?:member|mbrs?|as (?:a |an |the )?member|"
    r"in (?:his|her|their) capacity|individually|"
    r"chief of police|building inspector|zoning officer)\b"
)

INSTITUTION_START = re.compile(
    r"^(?:the )?(?:board|bd|commission|commision|committee|"
    r"select board|school committee|planning board|"
    r"zoning board|conservation commission|licensing board)\b"
)

GOV_PREFIX = re.compile(r"^(?:the )?(?:city|town) of ")


# V3.7: reviewed spelling variants, not general fuzzy matching.
# The audit decisions are provisional; these aliases establish geography,
# not whether the named party is legally a municipal entity.
V37_ALIASES = {
    "middleboro": "middleborough",
    "worceser": "worcester",
    "worcster": "worcester",
    "worceter": "worcester",
    "adamas": "adams",
    "leoaminster": "leominster",
    "westboro": "westborough",
    "foxorough": "foxborough",
    "northboro": "northborough",
    "southbrige": "southbridge",
    "northhampton": "northampton",
    "acusnet": "acushnet",
    "stroughton": "stoughton",
    "wentham": "wenham",
    "quiincy": "quincy",
    "wetport": "westport",
}

STATE_AGENCY = re.compile(
    r"\b(?:state police|massachusetts state police|state agency|"
    r"department of correction|registry of motor vehicles)\b"
)


def municipality_index(municipalities):
    aliases = {
        "no andover": "north andover",
        "n andover": "north andover",
        "no reading": "north reading",
        "n reading": "north reading",
        "e bridgewater": "east bridgewater",
        "w bridgewater": "west bridgewater",
        "n attleborough": "north attleborough",
    }

    lookup = dict(municipalities)
    aliases.update(V37_ALIASES)

    for alias, target in aliases.items():
        if target in municipalities and alias not in lookup:
            lookup[alias] = municipalities[target]

    return [
        (
            re.compile(r"(?<!\w)" + re.escape(k) + r"(?!\w)"),
            k,
            v,
        )
        for k, v in sorted(
            lookup.items(),
            key=lambda item: -len(item[0])
        )
    ]


def mentions(s, index):
    found = []

    for pattern, key, entity in index:
        for m in pattern.finditer(s):
            found.append((m.start(), m.end(), key, entity))

    found.sort(key=lambda x: (-(x[1] - x[0]), x[0]))

    chosen = []

    for entry in found:
        if not any(
            entry[0] < other[1] and entry[1] > other[0]
            for other in chosen
        ):
            chosen.append(entry)

    return chosen


# V3.6: Explicit official-capacity language; mere employment or membership
# is not sufficient for automatic inclusion.
EXPLICIT_OFFICIAL_CAPACITY = re.compile(
    r"\b(?:as (?:the |a |an )?(?:chief|commissioner|director|inspector|"
    r"custodian|chair|member|agent)|in (?:his|her|their) official capacity|"
    r"acting (?:as|in the capacity of)|on behalf of|for (?:the )?(?:city|town) of)\b"
)
NAMED_OFFICIAL_ROLE = re.compile(
    r"\b(?:chief of police|police chief|fire chief|"
    r"code enforcement officer|license commissioner|"
    r"custodian of records|building inspector|"
    r"planning board|zoning board|board of health|"
    r"inspector|commissioner|police department)\b"
)
# V3.6: Explicit personal AND official-capacity naming is not a clean
# official-capacity match. Preserve for review even when a town is known.
SOLELY_OFFICIAL_CAPACITY = re.compile(
    r"\b(?:solely|only|exclusively) in (?:his|her|their|an?) official capacit(?:y|ies)\b"
)
MIXED_PERSONAL_CAPACITY = re.compile(
    r"\b(?:individually|indiv(?:idual)?|in (?:his|her|their) "
    r"individual capacity|both individually and)\b"
)

# Institutions named as boards should not be recast as individual officials.
BOARD_INSTITUTION_LEAD = re.compile(
    r"^(?:the )?(?:(?:city|town) of [a-z ]+ )?"
    r"(?:zoning board|planning board|board of health|"
    r"school committee|conservation commission|board of appeals|"
    r"licensing board|board of selectmen|select board)\b"
)

TRUST_ENTITY = re.compile(r"\b(?:municipal affordable housing trust|housing trust fund)\b")
JOINT_DEPARTMENT = re.compile(r"\b(?:regional|joint|intermunicipal)\b")


def read_overrides(path):
    if not path:
        return {}
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    required = {"party_id", "inclusion_decision", "identified_municipality"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"Override CSV requires {sorted(required)}")
    overrides = {}
    for row in rows:
        pid = row["party_id"].strip()
        if not pid or pid in overrides:
            raise ValueError(f"Empty or duplicate override party_id: {pid!r}")
        overrides[pid] = row
    return overrides


def apply_override(result, override, municipalities):
    """Apply adjudicated party-ID decisions; review categories stay in review."""
    decision = override["inclusion_decision"].strip()
    town_name = override.get("identified_municipality", "").strip()
    town = municipalities.get(norm(town_name)) if town_name else None
    result = result.copy()
    if decision in ("include", "include_official_capacity"):
        if not town:
            raise ValueError(f"Included override has unknown municipality: {town_name!r}")
        result.update(
            dor_code=town[0], municipality=town[1],
            municipal_relationship=("official_capacity" if decision == "include_official_capacity" else "municipal_body"),
            match_status="matched", match_reason=f"case-context override: {decision}",
            match_confidence="reviewed",
        )
    elif decision in ("review_separate_entity", "review_joint_attribution", "unresolved"):
        result.update(
            dor_code="", municipality="", municipal_relationship=override.get("entity_category", ""),
            match_status="review", match_reason=f"case-context override: {decision}",
            match_confidence="low",
        )
    else:
        raise ValueError(f"Unknown override inclusion_decision: {decision}")
    return result


def classify(name, index):
    s = norm(name)

    out = dict(
        dor_code="",
        municipality="",
        municipal_relationship="",
        match_status="excluded",
        match_reason="no municipality name matched",
        match_confidence="none",
        procedural_designation="",
    )

    if not s:
        return out

    # Procedural designations are independent of municipal identity.
    if re.search(r"\b(?:trustee|trustees|garnishee)\b", s):
        out["procedural_designation"] = "trustee_or_garnishee"
    elif "party in interest" in s:
        out["procedural_designation"] = "party_in_interest"
    elif "reach and apply" in s:
        out["procedural_designation"] = "reach_and_apply"

    hits = mentions(s, index)

    identities = {
        (code, town)
        for _, _, _, (code, town) in hits
    }

    if not identities:
        return out

    if len(identities) != 1:
        out.update(
            match_status="review",
            match_reason="multiple distinct municipalities",
            match_confidence="low",
        )
        return out

    code, town = next(iter(identities))

    out.update(
        dor_code=code,
        municipality=town,
    )

    keys = sorted(
        {k for _, _, k, _ in hits},
        key=len,
        reverse=True,
    )

    municipal_expr = "(?:" + "|".join(
        re.escape(k) for k in keys
    ) + ")"

    prefix = re.match(
        r"^(?:the )?(?:city|town) of " + municipal_expr + r"\b",
        s,
    )

    suffix = s[prefix.end():].strip() if prefix else ""

    gov_phrase = bool(
        re.search(
            r"\b(?:city|town) of " + municipal_expr + r"\b",
            s,
        )
    )

    municipality_lead = any(
        s.startswith(k + " ") for k in keys
    )

    institutional_start = bool(INSTITUTION_START.match(s))

    institutional_of_place = bool(
        institutional_start
        and re.search(
            r"\bof (?:the )?(?:(?:city|town) of )?"
            + municipal_expr + r"\b",
            s,
        )
    )

    has_board = bool(BOARD.search(s))
    has_dept = bool(DEPT.search(s))

    # V3.7: a place-name alias must not convert a state agency
    # into a municipal police department.
    if STATE_AGENCY.search(s):
        out.update(
            dor_code="", municipality="", match_status="excluded",
            municipal_relationship="",
            match_reason="state agency (municipality is geographic only)",
            match_confidence="high",
        )
        return out

    # ---------------------------------------------------------
    # V3.3: Mixed federal and municipal parties
    # ---------------------------------------------------------
    if MIXED_FEDERAL_MUNICIPAL.search(s) and gov_phrase:
        out.update(
            match_status="review",
            municipal_relationship="",
            match_reason="mixed federal and municipal parties",
            match_confidence="low",
        )
        return out

    # ---------------------------------------------------------
    # V3.3: Individual municipal employees
    # ---------------------------------------------------------
    if INDIVIDUAL_EMPLOYEE.search(s):
        out.update(
            match_status="review",
            municipal_relationship="official_capacity",
            match_reason="individual municipal employee",
            match_confidence="low",
        )
        return out

    # Trusts and multi-municipality departments need special attribution.
    if TRUST_ENTITY.search(s):
        out.update(match_status="review", municipal_relationship="municipal_trust",
                   match_reason="municipal trust has separate legal identity",
                   match_confidence="low")
        return out
    if JOINT_DEPARTMENT.search(s) and has_dept:
        out.update(match_status="review", municipal_relationship="joint_department",
                   match_reason="joint department requires attribution review",
                   match_confidence="low")
        return out

    # V3.7.1: Do not broadly demote municipal board members. Explicit
    # official-capacity roles are handled by the V3.6 rules below.

    # V3.7.1: narrowly handle alias-based trailing-name ambiguity "Westboro Board of Health <person>".
    # Treat a trailing named person as ambiguous, not the board alone.
    if (has_board and any(re.search(r"\b" + re.escape(a) + r"\b", s)
                          for a in V37_ALIASES)
            and re.search(r"\bboard of health [a-z]+ [a-z]+$", s)):
        out.update(match_status="review", municipal_relationship="official_capacity",
                   match_reason="named individual appended to municipal board",
                   match_confidence="low")
        return out

    # Municipal boards named as institutions.
    if institutional_start and institutional_of_place and has_board:
        out.update(
            match_status="matched",
            municipal_relationship="board",
            match_reason="municipal board of named municipality",
            match_confidence="high",
        )
        return out


    # V3.6: named parties explicitly sued in personal and official capacities
    # require separate handling; don't silently count them as clean officials.
    if (MIXED_PERSONAL_CAPACITY.search(s)
            and not SOLELY_OFFICIAL_CAPACITY.search(s)
            and (gov_phrase or prefix)
            and NAMED_OFFICIAL_ROLE.search(s)):
        out.update(match_status="review",
                   municipal_relationship="mixed_individual_official_capacity",
                   match_reason="explicit individual and official capacities",
                   match_confidence="low")
        return out

    # Only explicit official-capacity language plus a government role and
    # a unique municipality is safe to include automatically.
    if (EXPLICIT_OFFICIAL_CAPACITY.search(s)
            and NAMED_OFFICIAL_ROLE.search(s)
            and (gov_phrase or re.search(r"\b(?:city|town) of " + municipal_expr + r"\b", s))
            and not INDIVIDUAL_EMPLOYEE.search(s)
            and not (institutional_start or BOARD_INSTITUTION_LEAD.search(s))
            and not SEPARATE.search(s)
            and not PRIVATE.search(MUNICIPAL_CORPORATION.sub(" ", s))):
        out.update(match_status="matched", municipal_relationship="official_capacity",
                   match_reason="explicit official-capacity municipal party",
                   match_confidence="medium")
        return out

    # Independent public entities should not be automatically
    # attributed to the municipality.
    if SEPARATE.search(s):
        out.update(
            match_status="review",
            municipal_relationship="separate_public_entity",
            match_reason="separate public entity",
            match_confidence="low",
        )
        return out

    # Municipal corporation is not a private corporation.
    private_check = MUNICIPAL_CORPORATION.sub(" ", s)

    if PRIVATE.search(private_check):
        out.update(
            match_status="review" if gov_phrase else "excluded",
            match_reason="private or mixed organization",
            match_confidence="low",
        )
        return out

    # Official titles and officeholders require review.
    if (
        OFFICIAL_TITLE_LEAD.search(s)
        or (
            OFFICIAL_TITLE_ANY.search(s)
            and (
                prefix
                or re.search(r"\b(?:police|fire) department\b", s)
            )
        )
    ):
        out.update(
            match_status="review",
            municipal_relationship="official_capacity",
            match_reason="official title or officeholder",
            match_confidence="low",
        )
        return out

    # Department of ... of Town/City of X.
    if DEPARTMENT_OF_PLACE.match(s) and re.search(
        r"\bof (?:(?:the )?(?:city|town) of )?"
        + municipal_expr + r"\b",
        s,
    ):
        out.update(
            match_status="matched",
            municipal_relationship="department",
            match_reason="municipal department of named municipality",
            match_confidence="high",
        )
        return out

    # Direct municipality.
    if prefix and not suffix:
        out.update(
            match_status="matched",
            municipal_relationship="direct",
            match_reason="direct municipality",
            match_confidence="high",
        )
        return out

    # Direct municipality with simple suffix.
    if prefix and (
        DIRECT_SUFFIX.fullmatch(suffix)
        or re.fullmatch(
            r"(?:mass|massachusetts|ma) "
            r"(?:trustee|defendant|plaintiff)",
            suffix,
        )
    ):
        out.update(
            match_status="matched",
            municipal_relationship="direct",
            match_reason="direct municipality with suffix",
            match_confidence="high",
        )
        return out

    representative_phrase = bool(
        re.search(
            r"\b(?:by and through|acting by and through|through)\b",
            s,
        )
    )

    person_mention = bool(PERSON_INTRO.search(s))

    official_named = bool(
        re.search(
            r"\b(?:by and through|through)\s+"
            r"(?:[A-Z][a-z]+\s+){1,3}[A-Z][a-z]+\s*,",
            name or "",
        )
    )

    # Municipality acting through its own board or department.
    if prefix and (has_board or has_dept):

        if official_named:
            out.update(
                match_status="review",
                municipal_relationship="official_capacity",
                match_reason="named municipal representative",
                match_confidence="low",
            )
            return out

        if person_mention and not representative_phrase and not has_board:
            out.update(
                match_status="review",
                municipal_relationship="official_capacity",
                match_reason="possible individual official",
                match_confidence="low",
            )
            return out

        out.update(
            match_status="matched",
            municipal_relationship="board" if has_board else "department",
            match_reason="municipality acting through institution",
            match_confidence="high",
        )
        return out

    if person_mention:
        out.update(
            match_status="review",
            municipal_relationship="official_capacity",
            match_reason="possible individual official",
            match_confidence="low",
        )
        return out

    if has_board and (
        (institutional_start and gov_phrase)
        or municipality_lead
    ):
        out.update(
            match_status="matched",
            municipal_relationship="board",
            match_reason="municipal board or commission",
            match_confidence="high" if gov_phrase else "medium",
        )
        return out

    if has_dept and (
        municipality_lead
        or (
            gov_phrase
            and s.startswith(("department ", "police ", "fire "))
        )
    ):
        out.update(
            match_status="matched",
            municipal_relationship="department",
            match_reason="municipal department",
            match_confidence="high" if gov_phrase else "medium",
        )
        return out

    if prefix:
        out.update(
            match_status="review",
            match_reason="unclassified municipal suffix",
            match_confidence="low",
        )
    else:
        out.update(
            match_status="review",
            match_reason="municipality mentioned without clear government identity",
            match_confidence="low",
        )

    return out


def load_municipalities(path):
    municipalities = {}

    with path.open(
        newline="",
        encoding="utf-8-sig",
    ) as f:

        reader = csv.DictReader(f)

        if not {"dor_code", "municipality"}.issubset(
            reader.fieldnames or []
        ):
            raise ValueError(
                "Municipal panel requires dor_code and municipality columns"
            )

        for row in reader:
            k = norm(row["municipality"])

            if k:
                municipalities[k] = (
                    row["dor_code"],
                    row["municipality"],
                )

    if len(municipalities) != 351:
        print(
            f"WARNING: {len(municipalities)} unique municipalities, "
            "expected 351",
            flush=True,
        )

    return municipalities


def read_previous(folder):
    previous = {}

    for status in ("matched", "review", "excluded"):
        path = folder / f"municipal_entities_{status}.csv"

        if not path.exists():
            raise FileNotFoundError(path)

        with path.open(
            newline="",
            encoding="utf-8-sig",
        ) as f:

            for row in csv.DictReader(f):
                pid = row["party_id"]

                if pid in previous:
                    raise ValueError(
                        f"Duplicate previous party_id: {pid}"
                    )

                previous[pid] = row

    return previous


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--candidates",
        type=Path,
        required=True,
    )

    ap.add_argument(
        "--municipalities",
        type=Path,
        required=True,
    )

    ap.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )

    ap.add_argument(
        "--compare-dir",
        type=Path,
        help="Prior classification output directory",
    )

    ap.add_argument("--overrides", type=Path,
                    help="Optional reviewed party-ID override CSV")

    args = ap.parse_args()

    municipalities = load_municipalities(args.municipalities)
    index = municipality_index(municipalities)
    overrides = read_overrides(args.overrides)

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    previous = (
        read_previous(args.compare_dir)
        if args.compare_dir
        else {}
    )

    fields = [
        "party_id",
        "party_name",
        "entity_type",
        "dor_code",
        "municipality",
        "municipal_relationship",
        "match_status",
        "match_reason",
        "match_confidence",
        "procedural_designation",
    ]

    handles = {}
    writers = {}

    counts = Counter()
    transitions = Counter()
    overrides_used = set()

    try:
        for status in ("matched", "review", "excluded"):
            path = (
                args.output_dir
                / f"municipal_entities_{status}.csv"
            )

            h = path.open(
                "w",
                newline="",
                encoding="utf-8",
            )

            handles[status] = h

            writers[status] = csv.DictWriter(
                h,
                fieldnames=fields,
            )

            writers[status].writeheader()

        audit_writer = None

        if previous:
            audit_path = (
                args.output_dir
                / "classification_changes.csv"
            )

            audit_handle = audit_path.open(
                "w",
                newline="",
                encoding="utf-8",
            )

            handles["audit"] = audit_handle

            audit_fields = [
                "party_id",
                "party_name",
                "old_status",
                "new_status",
                "old_relationship",
                "new_relationship",
                "old_municipality",
                "new_municipality",
                "old_reason",
                "new_reason",
            ]

            audit_writer = csv.DictWriter(
                audit_handle,
                fieldnames=audit_fields,
            )

            audit_writer.writeheader()

        seen = set()

        with args.candidates.open(
            newline="",
            encoding="utf-8-sig",
        ) as f:

            reader = csv.DictReader(f)

            required = {"party_id", "entity_type"}

            if (
                not required.issubset(reader.fieldnames or [])
                or not (
                    {"party_name", "name"}
                    & set(reader.fieldnames or [])
                )
            ):
                raise ValueError(
                    "Candidates require party_id, entity_type "
                    "and party_name or name"
                )

            for row in reader:
                pid = row["party_id"]

                if pid in seen:
                    raise ValueError(
                        f"Duplicate candidate party_id: {pid}. "
                        "Deduplicate SQL export first."
                    )

                seen.add(pid)

                name = (
                    row.get("party_name")
                    or row.get("name")
                    or ""
                )

                result = classify(name, index)
                if pid in overrides:
                    result = apply_override(result, overrides[pid], municipalities)
                    overrides_used.add(pid)

                output = {
                    "party_id": pid,
                    "party_name": name,
                    "entity_type": row.get("entity_type", ""),
                    **result,
                }

                status = result["match_status"]

                writers[status].writerow(output)
                counts[status] += 1

                old = previous.get(pid)

                if old:
                    transitions[
                        (old["match_status"], status)
                    ] += 1

                    old_identity = (
                        old["match_status"],
                        old.get("municipal_relationship", ""),
                        old.get("municipality", ""),
                    )

                    new_identity = (
                        status,
                        result["municipal_relationship"],
                        result["municipality"],
                    )

                    if old_identity != new_identity:
                        audit_writer.writerow({
                            "party_id": pid,
                            "party_name": name,
                            "old_status": old["match_status"],
                            "new_status": status,
                            "old_relationship": old.get(
                                "municipal_relationship", ""
                            ),
                            "new_relationship": result[
                                "municipal_relationship"
                            ],
                            "old_municipality": old.get(
                                "municipality", ""
                            ),
                            "new_municipality": result["municipality"],
                            "old_reason": old.get(
                                "match_reason", ""
                            ),
                            "new_reason": result["match_reason"],
                        })

                if sum(counts.values()) % 5000 == 0:
                    print(
                        f"Processed {sum(counts.values()):,} parties...",
                        flush=True,
                    )

    finally:
        for h in handles.values():
            h.close()

    unused = set(overrides) - overrides_used
    if unused:
        print(f"WARNING: {len(unused)} override party IDs absent from candidates")
    print(f"Reviewed overrides applied: {len(overrides_used)}")
    print("Party records:", sum(counts.values()))

    for status in ("matched", "review", "excluded"):
        print(f"  {status}: {counts[status]:,}")

    if previous:
        print("Transitions (previous -> v3.6):")

        for pair, count in sorted(transitions.items()):
            print(
                f"  {pair[0]} -> {pair[1]}: {count:,}"
            )

        print(
            "Audit:",
            args.output_dir / "classification_changes.csv",
        )

    print(
        "Review results before using matched IDs for case counts."
    )


if __name__ == "__main__":
    main()