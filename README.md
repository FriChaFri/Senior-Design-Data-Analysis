# seniorDesign

Starter repository for processing large volumes of IMU data collected from two phones.

## Goals

- Ingest raw IMU exports from each phone
- Normalize timestamps, units, and sensor labels
- Align streams across devices
- Build repeatable preprocessing and analysis steps
- Keep large data GitHub-safe by chunking files that exceed the per-file upload limit
- Estimate wheelchair battery requirements from processed gameplay IMU traces

## Project Layout

```text
.
├── data/
│   ├── raw/         # original exports from each phone
│   ├── interim/     # cleaned but not fully modeled data
│   └── processed/   # analysis-ready outputs
├── notebooks/       # exploration and validation
├── scripts/         # runnable entrypoints
├── src/imu_pipeline/
│   ├── io.py        # loading and path helpers
│   └── schema.py    # shared column names and expectations
├── tests/
├── pyproject.toml
└── README.md
```

## Suggested Raw Data Convention

Keep one folder per collection session, and separate each phone inside it:

```text
data/raw/
  2026-03-25-walk-test/
    phone_a/
    phone_b/
```

That makes it easier to pair recordings and trace provenance later.

## Quick Start

```bash
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/inspect_dataset.py --help
pytest
```

## Large Data Workflow

When a dataset is too large for a normal GitHub push, split it into tracked chunk
files and rebuild it locally when needed:

```bash
source .venv/bin/activate
python scripts/chunk_large_data.py chunk data/raw/Game1CharlesPhone.csv
python scripts/chunk_large_data.py rebuild data/raw/Game1CharlesPhone.csv
```

Chunk metadata is stored in `data/chunked/manifest.json`, and chunk files live
under `data/chunked/`. The rebuild command verifies file size and SHA256 so the
reconstructed file matches the original bytes.

## Battery Sizing Workflow

Run the end-to-end battery sizing analysis from the cleaned gameplay CSVs:

```bash
source .venv/bin/activate
python scripts/run_battery_sizing.py
```

This writes:

- `data/processed/battery_sizing/scenario_summary.csv`
- `data/processed/battery_sizing/scenario_summary.json`
- `data/processed/battery_sizing/timeseries/*.parquet`
- `data/processed/battery_sizing/plots/*.png`

The model uses the processed IMU trace to build:

```text
impact-masked planar acceleration + yaw rate -> surrogate planar velocity
-> wheel speeds/turn demand -> traction force -> wheel torque
-> motor torque/current -> battery power -> integrated battery energy
```

The default v1 assumptions are intentionally simple and editable near the top of
`scripts/run_battery_sizing.py`.

To derive a collision-trimmed gameplay-sizing dataset from the existing cleaned
files and generate a spec-first report tied to `Needs+Specs.xlsx`:

```bash
source .venv/bin/activate
python scripts/build_gameplay_sizing_dataset.py
python scripts/run_spec_driven_analysis.py
```

This preserves `data/processed/clean_games/` as the baseline cleaned dataset and
writes the derived gameplay-sizing files to `data/processed/clean_games_gameplay/`.

## Next Good Steps

1. Decide the exact export format from each phone app.
2. Add one or two representative sample files outside git.
3. Implement dataset-specific parsers in `src/imu_pipeline/io.py`.
4. Add tests for timestamp parsing and axis naming.
