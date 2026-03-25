# seniorDesign

Starter repository for processing large volumes of IMU data collected from two phones.

## Goals

- Ingest raw IMU exports from each phone
- Normalize timestamps, units, and sensor labels
- Align streams across devices
- Build repeatable preprocessing and analysis steps
- Keep raw data out of git while versioning code and metadata

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
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/inspect_dataset.py --help
pytest
```

## Next Good Steps

1. Decide the exact export format from each phone app.
2. Add one or two representative sample files outside git.
3. Implement dataset-specific parsers in `src/imu_pipeline/io.py`.
4. Add tests for timestamp parsing and axis naming.
