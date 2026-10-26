# Script paths after the refactor

Built-in data paths resolve from each script's location to `fa26`, so they work
when launched from the workspace, repository, `fa26`, or another directory.
No machine-specific absolute paths are required. Dataset filenames and the
version choices below remain explicit defaults.

Paths supplied through command-line flags follow normal CLI behavior: relative
paths are relative to your current working directory; absolute paths work from
any directory. The examples below run from `fa26`.

| Script | Inputs | Outputs |
| --- | --- | --- |
| `scripts/dls/download_dls.py` | Public DLS report | `data/raw/dls/schedule_a/` |
| `scripts/dls/combine_dls.py` | `data/raw/dls/` | Finances, population, quality in `data/processed/dls/`; municipal panel in `data/analysis/` |
| `scripts/masscourts/build_municipal_registry.py` | Explicit CLI flags | Explicit `--output-dir` |
| `scripts/masscourts/extract_municipal_cases.py` | Explicit `--registry`, database environment variable | Explicit `--output-dir` (normally `data/processed/masscourts/`) |
| `scripts/masscourts/extract_case_context.py` | `validation/initial/municipal_entities_uncertain_researched.csv`, `DATABASE_URL` | `validation/case_context/municipal_entity_case_context.csv` |
| `scripts/masscourts/extract_municipal_entity_case_context.py` | Explicit `--input`, `DATABASE_URL` or `MASSCOURTS_DATABASE_URL` | `validation/case_context/municipal_entity_case_context.csv` by default, or `--output` |
| `scripts/masscourts/build_litigation_panel.py` | Extracted cases in `LITIGATION_REBUILD_DIR` (defaults to `data/processed/masscourts/`), municipal panel in `data/analysis/` | Litigation panel in `LITIGATION_REBUILD_DIR` |
| `scripts/merge_litigation_dls.py` | Municipal panel in `data/analysis/`, litigation panel in `LITIGATION_REBUILD_DIR` (defaults to `data/processed/masscourts/`) | Merged panel in `LITIGATION_REBUILD_DIR` |
| `scripts/validation/validate_municipal_entities.py` | Original registry in `versions/v33/` | `validation/initial/` |
| `scripts/validation/validate_high_impact_entities.py` | Original registry in `versions/v33/`, extracted case parties | `validation/initial/` |
| `scripts/validation/apply_municipal_validation.py` | Review CSV or existing overrides in `validation/case_context/`, original registry in `versions/v33/` | Overrides in `validation/case_context/`; annotations in `validation/initial/` |
| `scripts/validation/audit_municipal_entities.py` | `versions/v33/` and `versions/v36/` under `--base` (defaults to `data/processed/masscourts/`) | `validation/v36_audit/` by default, or `--out` |
| `scripts/test.py` | Population in `data/processed/dls/` | Displays population charts |

All `validation/` and `versions/` paths in the table are beneath
`data/processed/masscourts/`. Initial validation continues to use v33, and the
audit compares v33 with v36. Neither step automatically selects a newer version.
The two case-context extraction scripts produce different schemas under the same
default filename; choose the extractor appropriate to your workflow.

Build a registry into a new output directory:

```bash
python scripts/masscourts/build_municipal_registry.py \
  --candidates data/raw/parties_expanded_v3.csv \
  --municipalities data/analysis/municipal_panel_2000_2025.csv \
  --output-dir data/processed/masscourts/versions/rebuilt \
  --compare-dir data/processed/masscourts/versions/v33 \
  --overrides data/processed/masscourts/validation/case_context/municipal_entity_case_context_overrides.csv
```

The registry builder uses its current classification rules regardless of the
output folder name.

```bash
python scripts/validation/audit_municipal_entities.py
python scripts/masscourts/build_litigation_panel.py
python scripts/merge_litigation_dls.py
```

The workspace's `check.py` reads the merged panel from `data/analysis/` relative
to its own location. The archived `old/collect_worcester.py` writes its CSVs and
debug HTML beside itself, independent of the launch directory.

To build and merge a versioned extraction, run both steps from `fa26`:

```bash
LITIGATION_REBUILD_DIR=data/processed/masscourts/rebuild_v371 \
  python scripts/masscourts/build_litigation_panel.py
LITIGATION_REBUILD_DIR=data/processed/masscourts/rebuild_v371 \
  python scripts/merge_litigation_dls.py
```

A relative `LITIGATION_REBUILD_DIR` resolves from your current working directory.
The shared DLS panel always resolves from `fa26/data/analysis/`.
