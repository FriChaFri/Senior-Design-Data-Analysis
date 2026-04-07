# Spreadsheet-Style Data-Driven Comparison

This report copies the workbook's solution path and only adapts the inputs needed to
feed it from the gameplay data.

## Adapter Rules

- Peak wheel speed comes from the clipped surrogate-speed trace.
- Continuous torque is the mean positive inertial motor torque per motor.
- Peak current uses the workbook's separate peak-torque check.
- Battery sizing stays constant-power for 2 hours, matching the workbook.

## Key Comparison Against The Existing Repo Model

### Game1CharlesPhone at 24 V

- Spreadsheet-style expected energy: `895.34 Wh`
- Repo motion-integrated energy: `414.61 Wh`
- Energy ratio: `2.16x`
- Spreadsheet peak current: `108.82 A`
- Repo peak current: `84.15 A`
- Spreadsheet rated current: `18.65 A`
- Repo average pack current: `8.64 A`

### Game1CharlesPhone at 36 V

- Spreadsheet-style expected energy: `895.34 Wh`
- Repo motion-integrated energy: `414.61 Wh`
- Energy ratio: `2.16x`
- Spreadsheet peak current: `72.55 A`
- Repo peak current: `56.10 A`
- Spreadsheet rated current: `12.44 A`
- Repo average pack current: `5.76 A`

### Game1CharlesPhone at 48 V

- Spreadsheet-style expected energy: `895.34 Wh`
- Repo motion-integrated energy: `414.61 Wh`
- Energy ratio: `2.16x`
- Spreadsheet peak current: `54.41 A`
- Repo peak current: `42.08 A`
- Spreadsheet rated current: `9.33 A`
- Repo average pack current: `4.32 A`

### Game2CharlesPhone at 24 V

- Spreadsheet-style expected energy: `797.33 Wh`
- Repo motion-integrated energy: `371.95 Wh`
- Energy ratio: `2.14x`
- Spreadsheet peak current: `108.82 A`
- Repo peak current: `84.15 A`
- Spreadsheet rated current: `16.61 A`
- Repo average pack current: `7.75 A`

### Game2CharlesPhone at 36 V

- Spreadsheet-style expected energy: `797.33 Wh`
- Repo motion-integrated energy: `371.95 Wh`
- Energy ratio: `2.14x`
- Spreadsheet peak current: `72.55 A`
- Repo peak current: `56.10 A`
- Spreadsheet rated current: `11.07 A`
- Repo average pack current: `5.17 A`

### Game2CharlesPhone at 48 V

- Spreadsheet-style expected energy: `797.33 Wh`
- Repo motion-integrated energy: `371.95 Wh`
- Energy ratio: `2.14x`
- Spreadsheet peak current: `54.41 A`
- Repo peak current: `42.08 A`
- Spreadsheet rated current: `8.31 A`
- Repo average pack current: `3.87 A`
