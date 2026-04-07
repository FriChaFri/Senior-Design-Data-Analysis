# Spec-First Gameplay Battery Analysis

- Authoritative workbook: `Needs+Specs.xlsx`
- Hardest gameplay-sizing session: `Game1CharlesPhone`
- Worst-case 2-hour energy basis: `413.28 Wh`
- Primary design voltage shown below: `48 V`

## Collision-Trimmed Gameplay Basis

- Baseline cleaned files in `data/processed/clean_games` remain unchanged.
- Gameplay sizing files are derived in `data/processed/clean_games_gameplay`.
- Collision windows removed for `Game1CharlesPhone`: `3`

## Spec Coverage

| Spec | Status | Metric | Target | Observed / modeled | Notes |
| --- | --- | --- | --- | --- | --- |
| F | partial-pass | Peak clipped gameplay acceleration | >= 2.85 m/s^2 average from rest over first 5 m | 2.85 m/s^2 | Current IMU workflow demonstrates the target acceleration magnitude is present in gameplay, but it does not reconstruct a standardized rest-to-5 m sprint. Treat this as lower-bound evidence. |
| G | modeled-pass | Rated motor output speed | >= 11.0 mph | rated=13.11 mph; observed_trace_cap=11.00 mph | Rated speed comes from the selected motor/gearing model. Observed gameplay speed is capped by the analysis v_max setting, so it is not independent proof. |
| H | not-evaluated | Turning-rate evidence | >= 200 deg/s within 0.50 s | Not currently derived from the existing IMU pipeline | The current repo infers forward motion well enough for longitudinal sizing, but it does not yet compute court-valid yaw-rate compliance for this spec. |
| O | design-input | 2-hour endurance requirement | Operate for >= 2.0 h | 413.28 Wh worst-case energy, 10.76 Ah at 48 V | This row translates the hardest non-collision gameplay trace into a 2-hour battery requirement. It is a sizing target, not a pass/fail result against a built battery pack. |

## Endurance Translation

| Voltage | Worst-case energy (Wh) | Lithium 80% Ah | Lead-acid 50% Ah | Peak current (A) |
| --- | --- | --- | --- | --- |
| 24 | 413.28 | 21.53 | 34.44 | 84.15 |
| 36 | 413.28 | 14.35 | 22.96 | 56.10 |
| 48 | 413.28 | 10.76 | 17.22 | 42.08 |
| 60 | 413.28 | 8.61 | 13.78 | 33.66 |
| 72 | 413.28 | 7.18 | 11.48 | 28.05 |