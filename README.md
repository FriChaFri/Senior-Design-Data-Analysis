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
reconstructed file matches the original bytes. The chunk store should only hold
source datasets that are too large to push directly. Generated processed
outputs are rebuilt locally and ignored by git.

## Battery Sizing Workflow

Run the official end-to-end battery sizing analysis from the raw gameplay CSVs.
The script rebuilds missing chunked raw files, regenerates
`data/processed/clean_games/`, cleans the gameplay trace in place, and then
sizes the battery from the cleaned gameplay demand:

```bash
source .venv/bin/activate
python scripts/run_battery_sizing.py
```

This writes the authoritative gameplay-driven battery outputs:

- `data/processed/battery_sizing/scenario_summary.csv`
- `data/processed/battery_sizing/scenario_summary.json`
- `data/processed/battery_sizing/timeseries/*.parquet`
- `data/processed/battery_sizing/plots/*.png`

These outputs are local build artifacts. They are intentionally ignored by git
so the repository keeps raw inputs plus reproducible scripts as the source of
truth.

The model uses the processed IMU trace to build:

```text
trimmed gameplay CSV -> collision interpolation + acceleration clipping + speed cap
-> planar acceleration + yaw rate -> surrogate planar velocity
-> wheel speeds/turn demand -> traction force -> wheel torque
-> motor torque/current -> battery power -> integrated battery energy
```

The official summary is reported per `game x voltage x battery chemistry` for
the selected `16:1` drivetrain assumption. Gameplay energy remains the same
across voltages, while pack current and required `Ah` change with voltage.

The default assumptions are intentionally simple and editable near the top of
`scripts/run_battery_sizing.py`. In this workflow, the project specs are used
to bound the gameplay trace during cleanup, not to produce a separate final
battery answer.

For reference-only comparison outputs, you can still derive a collision-trimmed
gameplay-sizing dataset and generate a spec-first report tied to
`Needs+Specs.xlsx`:

```bash
source .venv/bin/activate
python scripts/build_gameplay_sizing_dataset.py
python scripts/run_spec_driven_analysis.py
```

These scripts also rebuild missing chunked raw files and regenerate
`data/processed/clean_games/` before writing the derived gameplay-sizing files
to `data/processed/clean_games_gameplay/`. They are useful for audit and ideal
comparison, but they are not the repository's authoritative battery-capacity
result.

## Report Package

Build a self-contained LaTeX report package for the official gameplay-driven
battery workflow:

```bash
source .venv/bin/activate
python scripts/build_official_battery_report.py
```

This writes a tracked report package under
`reports/official_gameplay_battery_report/` containing:

- `main.tex`
- `figures/*.png`
- `tables/*.tex`
- `artifacts/*.csv` and `artifacts/*.json`

The folder is designed to be copied into Overleaf directly. The report uses the
official gameplay-driven battery-sizing outputs only and states the current
verification findings from that workflow.

## Next Good Steps

1. Decide the exact export format from each phone app.
2. Add one or two representative sample files outside git.
3. Implement dataset-specific parsers in `src/imu_pipeline/io.py`.
4. Add tests for timestamp parsing and axis naming.
